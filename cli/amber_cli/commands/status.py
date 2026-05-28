"""amber status — show service health and registered agents."""

import json
import os
import subprocess

import boto3
import click
from rich.console import Console
from rich.table import Table

from amber_cli.config_loader import load_config

console = Console()


def _run(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def _terraform_output(tf_dir: str) -> dict:
    result = _run(["terraform", "output", "-json"], cwd=tf_dir)
    raw = json.loads(result.stdout)
    return {k: v["value"] for k, v in raw.items()}


@click.command()
@click.option("--env", default="dev", help="Deployment environment")
def status(env: str) -> None:
    """Show service health and registered agents."""
    cfg = load_config()
    if not cfg.name:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)

    result = _run(["git", "rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0:
        click.echo("Not in a git repository.")
        raise SystemExit(1)
    repo_root = result.stdout.strip()

    tf_dir = os.path.join(repo_root, "infra", "terraform")
    prefix = cfg.prefix
    region = cfg.region

    # Header
    console.print(f"[bold]Amber status[/bold] — {cfg.name} ({env})")
    console.print(f"  Region: {region}  Prefix: {prefix}")
    console.print()

    # Terraform outputs
    try:
        tf_out = _terraform_output(tf_dir)
        cloudfront_domain = tf_out.get("cloudfront_domain", "")
        alb_dns = tf_out.get("alb_dns_name", "")
    except Exception:
        console.print("[red]  Could not read terraform outputs. Has the infrastructure been deployed?[/red]")
        raise SystemExit(1)

    # ── ECS Services ──────────────────────────────────────────────────────────
    console.print("[bold cyan]ECS Services[/bold cyan]")
    ecs = boto3.client("ecs", region_name=region)
    cluster = prefix
    service_names = [f"{prefix}-dashboard-api", f"{prefix}-customer-app"]

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
            status = deployments[0]["status"] if deployments else "UNKNOWN"

            if running == desired and desired > 0:
                status_str = f"[green]{status}[/green]"
            elif running < desired:
                status_str = f"[yellow]{status} ({running}/{desired})[/yellow]"
            else:
                status_str = status

            table.add_row(svc_name, str(desired), str(running), str(pending), status_str)
        except Exception:
            table.add_row(svc_name, "-", "-", "-", "[red]not found[/red]")

    console.print(table)
    console.print()

    # ── Health Checks ─────────────────────────────────────────────────────────
    console.print("[bold cyan]Health Checks[/bold cyan]")
    base_url = f"https://{cloudfront_domain}" if cloudfront_domain else f"http://{alb_dns}"

    checks = [
        ("Dashboard API", f"{base_url}/dashboard/workflows"),
        ("Customer App", f"{base_url}/demo/health"),
        ("Frontend", f"{base_url}/"),
    ]

    health_table = Table(show_header=True, header_style="bold")
    health_table.add_column("Service")
    health_table.add_column("URL")
    health_table.add_column("Status")

    for name, url in checks:
        try:
            resp = _run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10", url], check=False)
            code = resp.stdout.strip()
            if code == "200":
                health_table.add_row(name, url, f"[green]{code}[/green]")
            elif code:
                health_table.add_row(name, url, f"[yellow]{code}[/yellow]")
            else:
                health_table.add_row(name, url, "[red]no response[/red]")
        except Exception:
            health_table.add_row(name, url, "[red]error[/red]")

    console.print(health_table)
    console.print()

    # ── Registered Agents ─────────────────────────────────────────────────────
    console.print("[bold cyan]Registered Agents[/bold cyan]")
    try:
        health_url = f"{base_url}/demo/health"
        resp = _run(["curl", "-s", "--max-time", "10", health_url], check=False)
        data = json.loads(resp.stdout)
        agents = data.get("registered_agents", [])
        if agents:
            for agent in agents:
                console.print(f"  {agent}")
        else:
            console.print("  (no agents registered)")
    except Exception:
        console.print("  [yellow]Could not fetch agents — service may still be starting[/yellow]")

    console.print()

    # ── URLs ───────────────────────────────────────────────────────────────────
    if cloudfront_domain:
        console.print(f"[bold]URLs[/bold]")
        console.print(f"  Dashboard: https://{cloudfront_domain}/")
        console.print(f"  Demo:      https://{cloudfront_domain}/demo/")
        console.print(f"  API:       https://{cloudfront_domain}/api/")
