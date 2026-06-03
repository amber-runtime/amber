"""amber status — show deployed service health."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from amber_cli.admin_access import print_admin_access_status
from amber_cli.aws_auth import AWSAuthError, print_auth_error, require_identity
from amber_cli.config_loader import SECRET_REGISTRY, find_config_path, load_config
from amber_cli.routes import public_urls

console = Console()


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def _terraform_output(tf_dir: Path) -> dict:
    result = _run(["terraform", "output", "-json"], cwd=tf_dir)
    raw = json.loads(result.stdout)
    return {k: v["value"] for k, v in raw.items()}


@click.command()
@click.option("--env", default="", help="Deployment environment override")
def status(env: str) -> None:
    """Show service health and URLs."""
    cfg = load_config()
    if not cfg.name:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)
    if env:
        cfg.environment = env

    config_path = find_config_path()
    if not config_path:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)
    repo_root = Path(config_path).resolve().parent
    tf_dir = repo_root / ".amber" / "terraform"
    region = cfg.region

    console.print(f"[bold]Amber status[/bold] — {cfg.name} ({cfg.environment})")
    console.print(f"  Region: {region}  Prefix: {cfg.prefix}")
    console.print()

    try:
        tf_out = _terraform_output(tf_dir)
        cloudfront_domain = tf_out.get("cloudfront_domain", "")
        alb_dns = tf_out.get("alb_dns_name", "")
    except Exception:
        console.print("[red]  Could not read .amber terraform outputs. Has amber deploy run?[/red]")
        raise SystemExit(1)

    try:
        session, _ = require_identity(cfg.profile, region)
    except AWSAuthError as exc:
        print_auth_error(console, exc, "amber status")
        raise SystemExit(1) from exc

    console.print("[bold cyan]ECS Services[/bold cyan]")
    ecs = session.client("ecs", region_name=region)
    cluster = tf_out["ecs_cluster_name"]
    service_names = [
        tf_out["dashboard_api_service_name"],
        tf_out["customer_app_service_name"],
        tf_out["customer_worker_service_name"],
    ]

    table = Table(show_header=True, header_style="bold")
    table.add_column("Service")
    table.add_column("Desired")
    table.add_column("Running")
    table.add_column("Pending")
    table.add_column("Status")

    for svc_name in service_names:
        try:
            resp = ecs.describe_services(cluster=cluster, services=[svc_name])
            svc = resp["services"][0]
            running = svc["runningCount"]
            desired = svc["desiredCount"]
            pending = svc["pendingCount"]
            deployments = svc.get("deployments", [])
            status_text = deployments[0]["status"] if deployments else "UNKNOWN"
            if running == desired and desired > 0:
                status_str = f"[green]{status_text}[/green]"
            elif running < desired:
                status_str = f"[yellow]{status_text} ({running}/{desired})[/yellow]"
            else:
                status_str = status_text
            table.add_row(svc_name, str(desired), str(running), str(pending), status_str)
        except Exception:
            table.add_row(svc_name, "-", "-", "-", "[red]not found[/red]")

    console.print(table)
    console.print()

    console.print("[bold cyan]Health Checks[/bold cyan]")
    base_url = f"https://{cloudfront_domain}" if cloudfront_domain else f"http://{alb_dns}"
    urls = public_urls(cloudfront_domain) if cloudfront_domain else {}
    checks = [
        ("Customer app", f"{base_url}/health"),
        ("Amber admin", urls.get("amber_admin", f"{base_url}/admin/")),
        ("Amber admin API", urls.get("admin_api_health", f"{base_url}/admin/api/health")),
    ]

    health_table = Table(show_header=True, header_style="bold")
    health_table.add_column("Service")
    health_table.add_column("URL")
    health_table.add_column("Status")

    for name, url in checks:
        resp = _run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10", url],
            check=False,
        )
        code = resp.stdout.strip()
        if code == "200":
            health_table.add_row(name, url, f"[green]{code}[/green]")
        elif code:
            health_table.add_row(name, url, f"[yellow]{code}[/yellow]")
        else:
            health_table.add_row(name, url, "[red]no response[/red]")

    console.print(health_table)
    console.print()

    console.print("[bold cyan]Secrets[/bold cyan]")
    ssm = session.client("ssm", region_name=region)
    for key, meta in SECRET_REGISTRY.items():
        if meta.get("readonly"):
            continue
        try:
            path = meta["path"].format(ssm_base=cfg.ssm_base, secrets_prefix=cfg.secrets_prefix)
            resp = ssm.get_parameter(Name=path, WithDecryption=True)
            value = resp["Parameter"]["Value"]
            if "placeholder" in value.lower() or "set-me" in value.lower():
                console.print(f"  [yellow]{key}: PLACEHOLDER — run 'amber config set {key}'[/yellow]")
            else:
                console.print(f"  [green]{key}: set[/green]")
        except ssm.exceptions.ParameterNotFound:
            console.print(f"  [red]{key}: NOT SET — run 'amber config set {key}'[/red]")
        except Exception as exc:
            console.print(f"  {key}: error — {exc}")

    console.print()
    console.print("[bold cyan]Admin Access[/bold cyan]")
    print_admin_access_status(console, session, tf_out, region)

    if cloudfront_domain:
        console.print()
        console.print("[bold]URLs[/bold]")
        console.print(f"  Customer app:      {urls['customer_app']}")
        console.print(f"  Amber admin:       {urls['amber_admin']}")
        console.print(f"  Admin API health:  {urls['admin_api_health']}")
