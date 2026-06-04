"""amber destroy - tear down deployed AWS resources."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click
from botocore.exceptions import ClientError
from rich.console import Console

from amber_cli.aws_auth import AWSAuthError, print_auth_error, require_identity
from amber_cli.config_loader import find_config_path, load_config

console = Console()

PROD_DESTROY_TERRAFORM_ARGS = [
    "-var=db_deletion_protection=false",
    "-var=frontend_bucket_force_destroy=true",
    "-var=secrets_force_destroy=true",
    "-var=db_skip_final_snapshot=true",
    "-var=db_delete_automated_backups=true",
]

PROD_DATA_LOSS_WARNING = (
    "This will permanently delete the prod database without a final snapshot, "
    "delete automated backups, purge secrets immediately, and empty versioned "
    "frontend buckets."
)


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


def _terraform_destroy(tf_dir: Path, extra_args: list[str] | None = None) -> None:
    result = _run_with_status(
        ["terraform", "destroy", "-auto-approve", *(extra_args or [])],
        tf_dir,
        "  Destroying AWS resources...",
    )
    if result.returncode != 0:
        detail = result.stderr or result.stdout
        console.print(f"[red]Terraform destroy failed:[/red]\n{detail}")
        raise SystemExit(1)


def _disable_rds_deletion_protection(session, region: str, db_identifier: str) -> None:
    rds = session.client("rds", region_name=region)
    try:
        rds.modify_db_instance(
            DBInstanceIdentifier=db_identifier,
            DeletionProtection=False,
            ApplyImmediately=True,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "DBInstanceNotFound":
            console.print(
                f"[dim]RDS instance {db_identifier} is already gone; continuing.[/dim]"
            )
            return
        raise

    console.print(f"  Disabled RDS deletion protection: {db_identifier}")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(DBInstanceIdentifier=db_identifier)


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
        session, identity = require_identity(cfg.profile, region)
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

    prod_force_destroy = cfg.environment == "prod" and allow_prod_data_loss
    if cfg.environment == "prod":
        console.print(f"[bold red]{PROD_DATA_LOSS_WARNING}[/bold red]")
        console.print()
        expected = f"{cfg.name}-{cfg.environment}"
        typed = click.prompt(f"Type {expected} to destroy this prod stack", default="")
        if typed != expected:
            console.print("[yellow]Destroy cancelled.[/yellow]")
            raise SystemExit(1)
    elif not yes:
        confirmed = click.confirm("Destroy these AWS resources?", default=False)
        if not confirmed:
            console.print("[yellow]Destroy cancelled.[/yellow]")
            raise SystemExit(1)

    _terraform_init(tf_dir)
    destroy_args = PROD_DESTROY_TERRAFORM_ARGS if prod_force_destroy else []
    if prod_force_destroy:
        _disable_rds_deletion_protection(session, region, cfg.prefix)
    _terraform_destroy(tf_dir, destroy_args)

    console.print("[green]Cloud resources destroyed.[/green]")
    console.print("Local config kept: amber.yaml")
    console.print("To fully reset local Amber config: rm amber.yaml && rm -rf .amber")
