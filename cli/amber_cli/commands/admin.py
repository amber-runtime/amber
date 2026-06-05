"""amber admin — manage Amber dashboard operator access."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click
from botocore.exceptions import ClientError
from rich.console import Console

from amber_cli import dashboard_api, dashboard_auth
from amber_cli.aws_auth import AWSAuthError, print_auth_error, require_identity
from amber_cli.config_loader import find_config_path, load_config

console = Console()


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def _terraform_output(tf_dir: Path) -> dict[str, object]:
    result = _run(["terraform", "output", "-json"], cwd=tf_dir)
    raw = json.loads(result.stdout)
    return {k: v["value"] for k, v in raw.items()}


def _require_config_path() -> str:
    config_path = find_config_path()
    if not load_config().name or not config_path:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)
    return config_path


@click.group()
def admin() -> None:
    """Manage Cognito users for Amber dashboard access."""


@admin.command("login")
@click.option("--no-browser", is_flag=True, help="Print the login URL instead of opening a browser")
def login(no_browser: bool) -> None:
    """Sign in to the Amber dashboard for CLI workflow commands."""
    config_path = _require_config_path()
    try:
        api_base = dashboard_api.resolve_api_base(config_path)
    except dashboard_api.DashboardAPIError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc

    console.print("Opening browser for Cognito login...")
    try:
        dashboard_auth.login(api_base, open_browser=not no_browser)
    except dashboard_auth.DashboardAuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    console.print("[green]Logged in.[/green] Try: amber workflows list")


@admin.command("logout")
def logout() -> None:
    """Clear the cached CLI dashboard session."""
    removed = dashboard_auth.clear_session()
    if removed:
        console.print("[green]Logged out.[/green] Cleared cached dashboard session.")
    else:
        console.print("No cached dashboard session found.")


@admin.command("create-user")
@click.option("--email", required=True, help="Email address for the dashboard admin user")
@click.option("--resend", is_flag=True, help="Resend the Cognito invite for an existing user")
def create_user(email: str, resend: bool) -> None:
    """Create a Cognito user who can sign in to the Amber dashboard."""
    cfg = load_config()
    if not cfg.name:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)

    config_path = find_config_path()
    if not config_path:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)

    repo_root = Path(config_path).resolve().parent
    tf_dir = repo_root / ".amber" / "terraform"
    try:
        tf_out = _terraform_output(tf_dir)
    except Exception as exc:
        console.print("[red]Could not read .amber terraform outputs. Has amber deploy run?[/red]")
        raise SystemExit(1) from exc

    user_pool_id = str(tf_out.get("cognito_user_pool_id") or "")
    region = str(tf_out.get("cognito_region") or cfg.region)
    if not user_pool_id:
        console.print("[red]Terraform outputs do not include cognito_user_pool_id. Run amber deploy.[/red]")
        raise SystemExit(1)

    try:
        session, _ = require_identity(cfg.profile, region)
    except AWSAuthError as exc:
        print_auth_error(console, exc, "amber admin create-user --email " + email)
        raise SystemExit(1) from exc

    client = session.client("cognito-idp", region_name=region)
    create_kwargs = {
        "UserPoolId": user_pool_id,
        "Username": email,
        "UserAttributes": [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
        "DesiredDeliveryMediums": ["EMAIL"],
    }
    if resend:
        create_kwargs["MessageAction"] = "RESEND"

    try:
        client.admin_create_user(**create_kwargs)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UsernameExistsException":
            console.print(f"[yellow]Dashboard admin user already exists:[/yellow] {email}")
            console.print(f"To resend the invite: amber admin create-user --resend --email {email}")
            return
        raise

    if resend:
        console.print(f"[green]Resent dashboard admin invite:[/green] {email}")
    else:
        console.print(f"[green]Created dashboard admin user:[/green] {email}")
    console.print("Cognito is sending a temporary password email.")
    console.print("Use that email and temporary password at /admin/.")
    console.print("First login may require choosing a new password.")
