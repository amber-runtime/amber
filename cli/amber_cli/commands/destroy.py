"""amber destroy - tear down deployed AWS resources."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click
from rich.console import Console

from amber_cli.aws_auth import AWSAuthError, print_auth_error, require_identity
from amber_cli.config_loader import find_config_path, load_config

console = Console()


def _run_with_status(
    cmd: list[str],
    cwd: Path,
    message: str,
) -> subprocess.CompletedProcess:
    with console.status(message):
        return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def _terraform_init(tf_dir: Path) -> None:
    result = _run_with_status(["terraform", "init"], tf_dir, "  Initializing Terraform...")
    if result.returncode != 0:
        detail = result.stderr or result.stdout
        console.print(f"[red]Terraform init failed:[/red]\n{detail}")
        raise SystemExit(1)


def _terraform_destroy(tf_dir: Path) -> None:
    result = _run_with_status(
        ["terraform", "destroy", "-auto-approve"],
        tf_dir,
        "  Destroying AWS resources...",
    )
    if result.returncode != 0:
        detail = result.stderr or result.stdout
        console.print(f"[red]Terraform destroy failed:[/red]\n{detail}")
        raise SystemExit(1)


@click.command()
@click.option("--env", default="", help="Deployment environment override")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option(
    "--allow-prod-data-loss",
    is_flag=True,
    help="Allow destroying a prod stack for testing/cleanup.",
)
def destroy(env: str, yes: bool, allow_prod_data_loss: bool) -> None:
    """Destroy AWS resources created by amber deploy."""
    cfg = load_config()
    if env:
        cfg.environment = env

    config_path = find_config_path()
    if not config_path or not cfg.name:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)

    repo_root = Path(config_path).resolve().parent
    tf_dir = repo_root / ".amber" / "terraform"
    tf_state = tf_dir / "terraform.tfstate"
    region = cfg.region

    if not tf_dir.is_dir() or not tf_state.exists():
        console.print("[red]No Amber deploy state found. Has `amber deploy` run?[/red]")
        raise SystemExit(1)

    if cfg.profile:
        os.environ["AWS_PROFILE"] = cfg.profile
    os.environ["AWS_REGION"] = region
    os.environ["AWS_DEFAULT_REGION"] = region

    try:
        _, identity = require_identity(cfg.profile, region)
    except AWSAuthError as exc:
        print_auth_error(console, exc, "amber destroy")
        raise SystemExit(1) from exc

    console.print(f"[bold]Amber destroy[/bold] - {cfg.name} ({cfg.environment})")
    console.print(f"  AWS account: {identity.account}")
    console.print(f"  AWS profile: {cfg.profile or '(default)'}")
    console.print(f"  Region: {region}")
    console.print(f"  Terraform: {tf_dir}")
    console.print()

    if cfg.environment == "prod" and not allow_prod_data_loss:
        console.print("[red]Refusing to destroy prod without --allow-prod-data-loss.[/red]")
        console.print(
            "Prod uses safer defaults for buckets, secrets, and database deletion. "
            "For test cleanup, rerun with `amber destroy --allow-prod-data-loss`."
        )
        raise SystemExit(1)

    if not yes:
        if cfg.environment == "prod":
            expected = f"{cfg.name}-{cfg.environment}"
            typed = click.prompt(f"Type {expected} to destroy this prod stack", default="")
            if typed != expected:
                console.print("[yellow]Destroy cancelled.[/yellow]")
                raise SystemExit(1)
        else:
            confirmed = click.confirm("Destroy these AWS resources?", default=False)
            if not confirmed:
                console.print("[yellow]Destroy cancelled.[/yellow]")
                raise SystemExit(1)

    _terraform_init(tf_dir)
    _terraform_destroy(tf_dir)

    console.print("[green]Cloud resources destroyed.[/green]")
    console.print("Local config kept: amber.yaml")
    console.print("To fully reset local Amber config: rm amber.yaml && rm -rf .amber")
