"""amber deploy - build and deploy agents to AWS."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import click
from botocore.exceptions import ClientError
from rich.console import Console

from amber_cli.assets import asset_path
from amber_cli.aws_auth import AWSAuthError, is_auth_client_error, print_auth_error, require_identity
from amber_cli.config_loader import find_config_path, load_config, validate_deploy_config

console = Console()

SERVICE_TO_ECR_OUTPUT = {
    "dashboard-api": "ecr_dashboard_api_url",
    "customer-app": "ecr_customer_app_url",
    "customer-worker": "ecr_customer_worker_url",
}

SERVICE_TO_DOCKERFILE = {
    "dashboard-api": "Dockerfile.dashboard-api",
    "customer-app": "Dockerfile.customer-app",
    "customer-worker": "Dockerfile.customer-worker",
}

SERVICE_TO_CONTEXT = {
    "dashboard-api": "dashboard-api",
    "customer-app": "customer-app",
    "customer-worker": "customer-worker",
}

def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def _run_with_status(
    cmd: list[str],
    cwd: Path | None,
    message: str,
) -> subprocess.CompletedProcess:
    with console.status(message):
        return _run(cmd, cwd=cwd, check=False)


def _terraform_output(tf_dir: Path) -> dict:
    result = _run(["terraform", "output", "-json"], cwd=tf_dir)
    raw = json.loads(result.stdout)
    return {k: v["value"] for k, v in raw.items()}


def _ecr_outputs_from_config(cfg, account_id: str, region: str) -> dict[str, str]:
    base = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
    prefix = cfg.prefix
    return {
        "ecr_dashboard_api_url": f"{base}/{prefix}-dashboard-api",
        "ecr_customer_app_url": f"{base}/{prefix}-customer-app",
        "ecr_customer_worker_url": f"{base}/{prefix}-customer-worker",
    }


def _handle_aws_error(exc: ClientError) -> None:
    code = exc.response.get("Error", {}).get("Code", "")
    if is_auth_client_error(exc):
        print_auth_error(console, AWSAuthError(str(exc)), "amber deploy")
        raise SystemExit(1) from exc
    if "AccessDenied" in code or "Unauthorized" in code:
        console.print(
            "[red]AWS denied a deploy action. Re-launch or update the manual Amber IAM helper stack "
            "so the deploy identity has the required permissions.[/red]"
        )
        raise SystemExit(1) from exc
    raise exc


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path, ignore: shutil.IgnorePattern | None = None) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def _ensure_gitignore(repo_root: Path) -> None:
    gitignore = repo_root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".amber/" in existing.splitlines():
        return
    with gitignore.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(".amber/\n")


def _sync_terraform(tf_dir: Path) -> None:
    tf_dir.mkdir(parents=True, exist_ok=True)
    for src in asset_path("terraform").glob("*.tf"):
        _copy_file(src, tf_dir / src.name)


def _write_tfvars(tf_dir: Path, cfg, image_tag: str) -> None:
    project_name = cfg.project_prefix or cfg.name
    content = "\n".join(
        [
            f'project_name = "{project_name}"',
            f'environment = "{cfg.environment}"',
            f'region = "{cfg.region}"',
            f'image_tag = "{image_tag}"',
            f'asgi_app = "{cfg.app}"',
            f'worker_target = "{cfg.worker}"',
            f'path_prefix = "{cfg.path_prefix}"',
            "",
        ]
    )
    (tf_dir / "terraform.tfvars").write_text(content, encoding="utf-8")


def _find_sdk_wheel() -> Path:
    wheels = sorted(asset_path("sdk").glob("*.whl"))
    if len(wheels) != 1:
        console.print(
            f"[red]Expected exactly one bundled SDK wheel in CLI assets, found {len(wheels)}.[/red]"
        )
        console.print("Run `python cli/scripts/prepare_assets.py` before building/installing the CLI.")
        raise SystemExit(1)
    return wheels[0]


def _copy_customer_repo(repo_root: Path, dst: Path) -> None:
    ignore = shutil.ignore_patterns(
        ".amber",
        ".git",
        ".venv",
        "__pycache__",
        "*.pyc",
        "node_modules",
        "dist",
        ".pytest_cache",
        ".terraform",
        "*.tfstate",
        "*.tfvars",
    )
    _copy_tree(repo_root, dst, ignore=ignore)


def _assemble_customer_context(repo_root: Path, build_root: Path, service: str, wheel: Path) -> Path:
    context = build_root / SERVICE_TO_CONTEXT[service]
    if context.exists():
        shutil.rmtree(context)
    context.mkdir(parents=True)
    _copy_customer_repo(repo_root, context / "app")
    (context / "wheels").mkdir()
    _copy_file(wheel, context / "wheels" / wheel.name)
    docker_assets = asset_path("docker")
    _copy_file(docker_assets / SERVICE_TO_DOCKERFILE[service], context / "Dockerfile")
    _copy_file(docker_assets / ".dockerignore", context / ".dockerignore")
    entrypoint = "strip_prefix.py" if service == "customer-app" else "run_worker.py"
    _copy_file(docker_assets / entrypoint, context / entrypoint)
    return context


def _assemble_dashboard_context(build_root: Path, wheel: Path) -> Path:
    context = build_root / "dashboard-api"
    if context.exists():
        shutil.rmtree(context)
    context.mkdir(parents=True)
    _copy_tree(asset_path("control_plane"), context / "control_plane")
    (context / "wheels").mkdir()
    _copy_file(wheel, context / "wheels" / wheel.name)
    docker_assets = asset_path("docker")
    _copy_file(docker_assets / "Dockerfile.dashboard-api", context / "Dockerfile")
    _copy_file(docker_assets / ".dockerignore", context / ".dockerignore")
    _copy_file(docker_assets / "strip_prefix.py", context / "strip_prefix.py")
    return context


def _assemble_build_contexts(repo_root: Path, amber_dir: Path, services: list[str]) -> dict[str, Path]:
    build_root = amber_dir / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    wheel = _find_sdk_wheel()
    contexts: dict[str, Path] = {}
    for service in services:
        if service == "dashboard-api":
            contexts[service] = _assemble_dashboard_context(build_root, wheel)
        elif service in {"customer-app", "customer-worker"}:
            contexts[service] = _assemble_customer_context(repo_root, build_root, service, wheel)
        else:
            console.print(f"[red]Unknown service {service!r}.[/red]")
            raise SystemExit(1)
    return contexts


def _ecr_login(session, account_id: str, region: str) -> None:
    try:
        token = session.client("ecr", region_name=region).get_authorization_token()
    except ClientError as exc:
        _handle_aws_error(exc)
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


def _docker_build(context: Path, tag: str) -> None:
    subprocess.run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "-f",
            str(context / "Dockerfile"),
            "-t",
            tag,
            str(context),
        ],
        check=True,
    )


def _docker_push(tag: str) -> None:
    subprocess.run(["docker", "push", tag], check=True)


def _terraform_init(tf_dir: Path) -> None:
    result = _run_with_status(["terraform", "init"], tf_dir, "  Initializing Terraform...")
    if result.returncode != 0:
        detail = result.stderr or result.stdout
        console.print(f"[red]Terraform init failed:[/red]\n{detail}")
        raise SystemExit(1)


def _terraform_apply(
    tf_dir: Path,
    image_tag: str,
    targets: list[str] | None = None,
    status_message: str = "  Applying Terraform...",
) -> None:
    cmd = ["terraform", "apply", "-auto-approve", f"-var=image_tag={image_tag}"]
    for target in targets or []:
        cmd.extend(["-target", target])
    result = _run_with_status(cmd, tf_dir, status_message)
    if result.returncode != 0:
        detail = result.stderr or result.stdout
        console.print(f"[red]Terraform apply failed:[/red]\n{detail}")
        raise SystemExit(1)


def _sync_frontend(session, bucket: str, dist_id: str, region: str) -> None:
    dist_dir = asset_path("frontend", "dist")
    if not dist_dir.exists():
        console.print("[red]Bundled frontend dist is missing. Run prepare_assets.py first.[/red]")
        raise SystemExit(1)

    s3 = session.client("s3", region_name=region)
    content_types = {
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

    seen: set[str] = set()
    with console.status("  Syncing frontend assets..."):
        for root, _, files in os.walk(dist_dir):
            for fname in files:
                local_path = Path(root) / fname
                key = str(local_path.relative_to(dist_dir))
                seen.add(key)
                ext = local_path.suffix.lower()
                extra_args = {"ContentType": content_types[ext]} if ext in content_types else {}
                try:
                    s3.upload_file(str(local_path), bucket, key, ExtraArgs=extra_args)
                except ClientError as exc:
                    _handle_aws_error(exc)
                console.print(f"  uploaded: {key}")

    try:
        with console.status("  Removing stale frontend assets..."):
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                stale = [
                    {"Key": obj["Key"]}
                    for obj in page.get("Contents", [])
                    if obj["Key"] not in seen
                ]
                if stale:
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": stale})
    except ClientError as exc:
        _handle_aws_error(exc)

    if dist_id:
        try:
            with console.status("  Invalidating CloudFront cache..."):
                session.client("cloudfront", region_name=region).create_invalidation(
                    DistributionId=dist_id,
                    InvalidationBatch={
                        "Paths": {"Quantity": 1, "Items": ["/*"]},
                        "CallerReference": f"amber-cli-{int(time.time())}",
                    },
                )
        except ClientError as exc:
            _handle_aws_error(exc)
        console.print("  [green]CloudFront cache invalidated[/green]")


def _restart_ecs(session, cluster: str, services: list[str], region: str) -> None:
    ecs = session.client("ecs", region_name=region)
    for service in services:
        try:
            ecs.update_service(cluster=cluster, service=service, forceNewDeployment=True)
        except ClientError as exc:
            _handle_aws_error(exc)
        console.print(f"  restarted: {service}")


def _image_tag(repo_root: Path) -> str:
    result = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return str(int(time.time()))


@click.command()
@click.option("--env", default="", help="Deployment environment override")
@click.option("--no-build", is_flag=True, help="Skip Docker build (use existing images)")
@click.option("--no-infra", is_flag=True, help="Skip terraform apply")
@click.option("--no-frontend", is_flag=True, help="Skip frontend deploy")
@click.option("--service", multiple=True, help="Specific service(s) to build (default: all)")
def deploy(env: str, no_build: bool, no_infra: bool, no_frontend: bool, service: tuple[str, ...]) -> None:
    """Build and deploy your agents to AWS."""
    cfg = load_config()
    errors = validate_deploy_config(cfg)
    if errors:
        console.print("[red]Invalid amber.yaml:[/red]")
        for error in errors:
            console.print(f"  - {error}")
        raise SystemExit(1)
    if env:
        cfg.environment = env

    config_path = find_config_path()
    if not config_path:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)
    repo_root = Path(config_path).resolve().parent
    amber_dir = repo_root / ".amber"
    tf_dir = amber_dir / "terraform"
    region = cfg.region
    image_tag = _image_tag(repo_root)
    if cfg.profile:
        os.environ["AWS_PROFILE"] = cfg.profile
    os.environ["AWS_REGION"] = region
    os.environ["AWS_DEFAULT_REGION"] = region

    try:
        session, identity = require_identity(cfg.profile, region)
    except AWSAuthError as exc:
        print_auth_error(console, exc, "amber deploy")
        raise SystemExit(1) from exc
    account_id = identity.account

    _ensure_gitignore(repo_root)
    _sync_terraform(tf_dir)
    _write_tfvars(tf_dir, cfg, image_tag)

    console.print(f"[bold]Amber deploy[/bold] - {cfg.name} ({cfg.environment})")
    console.print(f"  AWS account: {account_id}")
    console.print(f"  Region: {region}")
    console.print(f"  Repo: {repo_root}")
    console.print(f"  Image tag: {image_tag}")
    console.print()

    services_to_build = list(service) if service else ["dashboard-api", "customer-app", "customer-worker"]
    unknown = sorted(set(services_to_build) - set(SERVICE_TO_ECR_OUTPUT))
    if unknown:
        console.print(f"[red]Unknown service(s): {', '.join(unknown)}[/red]")
        raise SystemExit(1)

    if not no_infra:
        console.print("[bold cyan]Step 1/5: Preparing Terraform and ECR[/bold cyan]")
        _terraform_init(tf_dir)
        _terraform_apply(
            tf_dir,
            image_tag,
            targets=[
                "aws_ecr_repository.dashboard_api",
                "aws_ecr_repository.customer_app",
                "aws_ecr_repository.customer_worker",
            ],
            status_message="  Preparing ECR repositories...",
        )
        console.print("[green]  ECR repositories ready[/green]")
        console.print()
    else:
        console.print("[dim]  Skipping ECR bootstrap (--no-infra)[/dim]")

    if no_infra:
        tf_out = _terraform_output(tf_dir)
    else:
        tf_out = _ecr_outputs_from_config(cfg, account_id, region)

    if not no_build:
        console.print("[bold cyan]Step 2/5: Building Docker images[/bold cyan]")
        contexts = _assemble_build_contexts(repo_root, amber_dir, services_to_build)
        _ecr_login(session, account_id, region)
        for service_name, context in contexts.items():
            image = f"{tf_out[SERVICE_TO_ECR_OUTPUT[service_name]]}:{image_tag}"
            console.print(f"  [bold]Building {service_name}...[/bold]")
            _docker_build(context, image)
            console.print(f"  [bold]Pushing {service_name}...[/bold]")
            _docker_push(image)
            console.print(f"  [green]{service_name}: {image}[/green]")
        console.print()
    else:
        console.print("[dim]  Skipping Docker build (--no-build)[/dim]")

    if not no_infra:
        console.print("[bold cyan]Step 3/5: Applying full infrastructure[/bold cyan]")
        _terraform_apply(tf_dir, image_tag, status_message="  Applying AWS infrastructure...")
        tf_out = _terraform_output(tf_dir)
        console.print("[green]  Infrastructure deployed[/green]")
        console.print()
    else:
        console.print("[bold cyan]Step 3/5: Restarting ECS services[/bold cyan]")
        _restart_ecs(
            session,
            tf_out["ecs_cluster_name"],
            [
                tf_out["dashboard_api_service_name"],
                tf_out["customer_app_service_name"],
                tf_out["customer_worker_service_name"],
            ],
            region,
        )
        console.print()

    if not no_frontend:
        console.print("[bold cyan]Step 4/5: Deploying frontend[/bold cyan]")
        _sync_frontend(
            session,
            tf_out["frontend_bucket_name"],
            tf_out.get("cloudfront_distribution_id", ""),
            region,
        )
        console.print("[green]  Frontend deployed[/green]")
        console.print()
    else:
        console.print("[dim]  Skipping frontend (--no-frontend)[/dim]")

    console.print("[bold cyan]Step 5/5: Summary[/bold cyan]")
    cloudfront_domain = tf_out.get("cloudfront_domain", "")
    console.print("[bold green]Deploy complete![/bold green]")
    if cloudfront_domain:
        console.print(f"  URL:       https://{cloudfront_domain}")
        console.print(f"  Dashboard: https://{cloudfront_domain}/")
        console.print(f"  API:       https://{cloudfront_domain}{cfg.path_prefix}/")
