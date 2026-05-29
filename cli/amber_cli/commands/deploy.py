"""amber deploy — build and deploy agents to the cloud."""

import base64
import json
import os
import subprocess
import time

import boto3
import click
from rich.console import Console

from amber_cli.config_loader import find_config_path, load_config

console = Console()


def _run(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess, capturing output."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _terraform_output(tf_dir: str) -> dict:
    """Read terraform output as JSON."""
    result = _run(["terraform", "output", "-json"], cwd=tf_dir)
    raw = json.loads(result.stdout)
    return {k: v["value"] for k, v in raw.items()}


def _get_account_id() -> str:
    sts = boto3.client("sts")
    return sts.get_caller_identity()["Account"]


def _ecr_login(account_id: str, region: str) -> None:
    """Authenticate Docker with ECR."""
    ecr = boto3.client("ecr", region_name=region)
    token = ecr.get_authorization_token()
    decoded = base64.b64decode(token["authorizationData"][0]["authorizationToken"])
    password = decoded.decode().split(":")[1]
    registry = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
    subprocess.run(
        ["docker", "login", "--username", "AWS", "--password-stdin", registry],
        input=password,
        check=True,
        capture_output=True,
        text=True,
    )


def _docker_build(dockerfile: str, tag: str, context: str) -> subprocess.CompletedProcess:
    """Build a Docker image."""
    return subprocess.run(
        [
            "docker", "build",
            "--platform", "linux/amd64",
            "-f", dockerfile,
            "-t", f"{tag}:latest",
            context,
        ],
        check=True,
    )


def _docker_push(tag: str) -> subprocess.CompletedProcess:
    """Push a Docker image."""
    return subprocess.run(
        ["docker", "push", f"{tag}:latest"],
        check=True,
        capture_output=True,
        text=True,
    )


def _build_and_push_images(
    services: list[str],
    account_id: str,
    region: str,
    prefix: str,
    repo_root: str,
) -> None:
    """Build and push Docker images for the given services."""
    ecr_base = f"{account_id}.dkr.ecr.{region}.amazonaws.com"

    for svc in services:
        ecr_repo = f"{ecr_base}/{prefix}-{svc}"
        dockerfile = os.path.join(repo_root, "infra", "docker", f"Dockerfile.{svc}")

        if not os.path.exists(dockerfile):
            console.print(f"[red]Dockerfile not found: {dockerfile}[/red]")
            raise SystemExit(1)

        console.print(f"  [bold]Building {svc}...[/bold]")
        _docker_build(dockerfile, ecr_repo, repo_root)

        console.print(f"  [bold]Pushing {svc}...[/bold]")
        _docker_push(ecr_repo)
        console.print(f"  [green]  {svc}: {ecr_repo}:latest[/green]")


def _build_frontend(repo_root: str) -> bool:
    """Build the React dashboard. Returns True on success."""
    dashboard_dir = os.path.join(repo_root, "dashboard")

    result = _run(["npm", "ci"], cwd=dashboard_dir)
    if result.returncode != 0:
        console.print(f"[red]npm ci failed:[/red]\n{result.stderr}")
        return False

    result = _run(["npm", "run", "build"], cwd=dashboard_dir)
    if result.returncode != 0:
        console.print(f"[red]Dashboard build failed:[/red]\n{result.stderr}")
        return False

    return True


def _deploy_frontend(bucket: str, dist_id: str, repo_root: str, region: str) -> None:
    """Sync dashboard build to S3 and invalidate CloudFront."""
    dist_dir = os.path.join(repo_root, "dashboard", "dist")
    s3 = boto3.client("s3", region_name=region)

    CONTENT_TYPES = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }

    for root, _, files in os.walk(dist_dir):
        for fname in files:
            local_path = os.path.join(root, fname)
            key = os.path.relpath(local_path, dist_dir)
            ext = os.path.splitext(fname)[1].lower()
            content_type = CONTENT_TYPES.get(ext)
            extra_args = {"ContentType": content_type} if content_type else {}
            s3.upload_file(local_path, bucket, key, ExtraArgs=extra_args)
            console.print(f"  uploaded: {key}")

    if dist_id:
        cf = boto3.client("cloudfront", region_name=region)
        cf.create_invalidation(
            DistributionId=dist_id,
            InvalidationBatch={
                "Paths": {"Quantity": 1, "Items": ["/*"]},
                "CallerReference": f"amber-cli-{int(time.time())}",
            },
        )
        console.print("  [green]CloudFront cache invalidated[/green]")


def _restart_ecs(cluster: str, services: list[str], region: str) -> None:
    """Force new deployment on ECS services."""
    ecs = boto3.client("ecs", region_name=region)
    for svc in services:
        ecs.update_service(
            cluster=cluster,
            service=svc,
            forceNewDeployment=True,
        )
        console.print(f"  restarted: {svc}")


def _find_cloudfront_dist_id(domain: str, region: str) -> str:
    """Look up CloudFront distribution ID from domain name."""
    cf = boto3.client("cloudfront", region_name=region)
    for d in cf.list_distributions().get("DistributionList", {}).get("Items", []):
        if d.get("DomainName") == domain:
            return d["Id"]
    return ""


@click.command()
@click.option("--env", default="dev", help="Deployment environment")
@click.option("--no-build", is_flag=True, help="Skip Docker build (use existing images)")
@click.option("--no-infra", is_flag=True, help="Skip terraform apply")
@click.option("--no-frontend", is_flag=True, help="Skip frontend build and deploy")
@click.option("--service", multiple=True, help="Specific service(s) to build (default: all)")
def deploy(env: str, no_build: bool, no_infra: bool, no_frontend: bool, service: tuple) -> None:
    """Build and deploy your agents to the cloud."""
    cfg = load_config()
    if not cfg.name:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)

    # Find repo root via git
    result = _run(["git", "rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0:
        click.echo("Not in a git repository.")
        raise SystemExit(1)
    repo_root = result.stdout.strip()

    tf_dir = os.path.join(repo_root, "infra", "terraform")
    prefix = cfg.prefix
    region = cfg.region
    account_id = _get_account_id()

    console.print(f"[bold]Amber deploy[/bold] — {cfg.name} ({env})")
    console.print(f"  AWS account: {account_id}")
    console.print(f"  Region: {region}")
    console.print(f"  Prefix: {prefix}")
    console.print()

    # ── Step 1: Terraform ─────────────────────────────────────────────────────
    if not no_infra:
        console.print("[bold cyan]Step 1/4: Terraform[/bold cyan]")
        _run(["terraform", "init", "-upgrade"], cwd=tf_dir)
        result = _run(
            ["terraform", "apply", "-auto-approve"],
            cwd=tf_dir,
            check=False,
        )
        if result.returncode != 0:
            console.print(f"[red]Terraform apply failed:[/red]\n{result.stderr}")
            raise SystemExit(1)
        console.print("[green]  Infrastructure up to date[/green]")
        console.print()
    else:
        console.print("[dim]  Skipping terraform (--no-infra)[/dim]")

    # Read terraform outputs
    tf_out = _terraform_output(tf_dir)
    cloudfront_domain = tf_out.get("cloudfront_domain", "")
    bucket = tf_out.get("frontend_bucket_name", f"{prefix}-frontend")

    # Update .env.production with the current CloudFront domain
    if cloudfront_domain and not no_frontend:
        env_file = os.path.join(repo_root, "dashboard", ".env.production")
        if os.path.exists(env_file):
            with open(env_file) as f:
                content = f.read()
            # Replace any cloudfront.net domain with the current one
            import re
            updated = re.sub(
                r"https://[a-z0-9]+\.cloudfront\.net",
                f"https://{cloudfront_domain}",
                content,
            )
            if updated != content:
                with open(env_file, "w") as f:
                    f.write(updated)
                console.print(f"  Updated .env.production → {cloudfront_domain}")

    # ── Step 2: Docker build + push ────────────────────────────────────────────
    if not no_build:
        console.print("[bold cyan]Step 2/4: Building Docker images[/bold cyan]")
        services_to_build = list(service) if service else ["dashboard-api", "customer-app", "customer-worker"]
        _ecr_login(account_id, region)
        _build_and_push_images(services_to_build, account_id, region, prefix, repo_root)
        console.print()
    else:
        console.print("[dim]  Skipping Docker build (--no-build)[/dim]")

    # ── Step 3: Restart ECS ────────────────────────────────────────────────────
    console.print("[bold cyan]Step 3/4: Restarting ECS services[/bold cyan]")
    cluster = prefix
    ecs_services = [
        f"{prefix}-dashboard-api",
        f"{prefix}-customer-app",
        f"{prefix}-customer-worker",
    ]
    _restart_ecs(cluster, ecs_services, region)
    console.print()

    # ── Step 4: Deploy frontend ────────────────────────────────────────────────
    if not no_frontend:
        console.print("[bold cyan]Step 4/4: Deploying frontend[/bold cyan]")
        dist_id = _find_cloudfront_dist_id(cloudfront_domain, region)
        if _build_frontend(repo_root):
            _deploy_frontend(bucket, dist_id, repo_root, region)
            console.print("[green]  Frontend deployed[/green]")
        else:
            console.print("[yellow]  Frontend build failed — backend services still updated[/yellow]")
        console.print()
    else:
        console.print("[dim]  Skipping frontend (--no-frontend)[/dim]")

    # ── Summary ────────────────────────────────────────────────────────────────
    console.print("[bold green]Deploy complete![/bold green]")
    if cloudfront_domain:
        console.print(f"  URL:       https://{cloudfront_domain}")
        console.print(f"  Dashboard: https://{cloudfront_domain}/")
        console.print(f"  Demo:      https://{cloudfront_domain}/demo/")
        console.print(f"  API:       https://{cloudfront_domain}/api/")
