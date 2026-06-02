"""amber auth — configure AWS access for deploys."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console

from amber_cli.aws_auth import AWSAuthError, print_auth_error, verify_identity
from amber_cli.config_loader import find_config_path, load_config

console = Console()


def _run_aws(args: list[str], *, interactive: bool = False, input_text: str | None = None) -> None:
    if shutil.which("aws") is None:
        console.print("[red]AWS CLI is not installed or not on PATH.[/red]")
        console.print("Install it from https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html")
        raise SystemExit(1)

    cmd = ["aws", *args]
    if interactive:
        result = subprocess.run(cmd)
    else:
        result = subprocess.run(cmd, input=input_text, text=True, capture_output=True)
        if result.stdout:
            console.print(result.stdout.rstrip())
        if result.stderr:
            console.print(result.stderr.rstrip())

    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _require_config_path() -> Path:
    config_path = find_config_path()
    if not config_path:
        console.print("[red]No amber.yaml found. Run 'amber init' first.[/red]")
        raise SystemExit(1)
    return Path(config_path)


def _update_amber_yaml(config_path: Path, profile: str, region: str) -> None:
    text = config_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    found = {"profile": False, "region": False}
    updated: list[str] = []

    for line in lines:
        if re.match(r"^\s*#?\s*profile\s*:", line):
            updated.append(f"profile: {profile}")
            found["profile"] = True
        elif re.match(r"^\s*#?\s*region\s*:", line):
            updated.append(f"region: {region}")
            found["region"] = True
        else:
            updated.append(line)

    if not found["region"]:
        updated.append(f"region: {region}")
    if not found["profile"]:
        updated.append(f"profile: {profile}")

    trailing_newline = "\n" if text.endswith("\n") else ""
    config_path.write_text("\n".join(updated) + trailing_newline, encoding="utf-8")


def _save_verified_profile(profile: str, region: str) -> None:
    config_path = _require_config_path()
    try:
        identity = verify_identity(profile, region)
    except AWSAuthError as exc:
        print_auth_error(console, exc, "amber auth setup")
        raise SystemExit(1) from exc

    _update_amber_yaml(config_path, profile, region)
    console.print()
    console.print("[green]AWS auth is ready.[/green]")
    console.print(f"  Account: {identity.account}")
    console.print(f"  ARN:     {identity.arn}")
    console.print(f"  Region:  {region}")
    console.print(f"  Profile: {profile}")
    console.print()
    console.print("Next:")
    console.print("  amber deploy")


def _prompt_profile(default: str) -> str:
    return click.prompt("AWS profile name", default=default).strip()


def _prompt_region(default: str) -> str:
    return click.prompt("AWS region", default=default).strip()


def _setup_sso(default_region: str, default_profile: str, profile_option: str, region_option: str) -> None:
    profile = profile_option or _prompt_profile(default_profile)
    region = region_option or _prompt_region(default_region)
    console.print()
    console.print("[bold]Configuring AWS SSO / IAM Identity Center[/bold]")
    console.print("Amber will use the AWS CLI's SSO wizard and then verify the profile.")
    _run_aws(["configure", "sso", "--profile", profile], interactive=True)
    _save_verified_profile(profile, region)


@click.group()
def auth() -> None:
    """Configure and check AWS access."""
    pass


@auth.command("setup")
@click.option("--profile", default="", help="AWS profile to configure")
@click.option("--region", default="", help="AWS region to save in amber.yaml")
def setup(profile: str, region: str) -> None:
    """Configure AWS SSO access for Amber deploys."""
    cfg = load_config()
    if not cfg.name:
        console.print("[red]No amber.yaml found. Run 'amber init' first.[/red]")
        raise SystemExit(1)

    default_region = region or cfg.region or "us-east-1"
    default_profile = f"amber-{cfg.environment}" if cfg.environment in {"dev", "prod"} else "amber"
    _setup_sso(default_region, default_profile, profile, region)


@auth.command("login")
def login() -> None:
    """Refresh the saved AWS SSO session."""
    cfg = load_config()
    if not cfg.name:
        console.print("[red]No amber.yaml found. Run 'amber init' first.[/red]")
        raise SystemExit(1)
    if not cfg.profile:
        console.print("[red]No AWS profile is configured in amber.yaml.[/red]")
        console.print("Run `amber auth setup` first.")
        raise SystemExit(1)

    _run_aws(["sso", "login", "--profile", cfg.profile], interactive=True)
    _save_verified_profile(cfg.profile, cfg.region)


@auth.command("check")
@click.option("--profile", default="", help="AWS profile to check")
@click.option("--region", default="", help="AWS region to check")
def check(profile: str, region: str) -> None:
    """Verify the configured AWS profile."""
    cfg = load_config()
    if not cfg.name:
        console.print("[red]No amber.yaml found. Run 'amber init' first.[/red]")
        raise SystemExit(1)

    profile = profile or cfg.profile
    region = region or cfg.region or "us-east-1"
    try:
        identity = verify_identity(profile, region)
    except AWSAuthError as exc:
        print_auth_error(console, exc, "amber auth check")
        raise SystemExit(1) from exc

    console.print("[green]AWS auth is valid.[/green]")
    console.print(f"  Account: {identity.account}")
    console.print(f"  ARN:     {identity.arn}")
    console.print(f"  Region:  {region}")
    console.print(f"  Profile: {profile or '(default)'}")
