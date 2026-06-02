"""amber auth — configure AWS access for deploys."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console

from amber_cli.assets import asset_path
from amber_cli.aws_auth import AWSAuthError, print_auth_error, verify_identity
from amber_cli.config_loader import find_config_path, load_config

console = Console()

CLOUDFORMATION_URL = "https://console.aws.amazon.com/cloudformation/home#/stacks/create/template"


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


def _setup_sso(default_region: str, profile_option: str, region_option: str) -> None:
    profile = profile_option or _prompt_profile("amber")
    region = region_option or _prompt_region(default_region)
    console.print()
    console.print("[bold]Configuring AWS SSO / IAM Identity Center[/bold]")
    console.print("Amber will use the AWS CLI's SSO wizard, then verify the profile.")
    _run_aws(["configure", "sso", "--profile", profile], interactive=True)
    _run_aws(["sso", "login", "--profile", profile], interactive=True)
    _save_verified_profile(profile, region)


def _setup_cloudformation(default_region: str, profile_option: str, region_option: str) -> None:
    profile = profile_option or _prompt_profile("amber")
    region = region_option or _prompt_region(default_region)
    console.print()
    console.print("[bold]Create an Amber deploy identity in AWS[/bold]")
    console.print("Use this path if you can sign into the AWS Console as an admin.")
    console.print("Launch the CloudFormation stack, then paste the access key outputs here.")
    console.print()
    console.print(f"  Launch CloudFormation: {CLOUDFORMATION_URL}")
    console.print(f"  Template:              {asset_path('bootstrap', 'amber-bootstrap.yaml')}")
    console.print()
    access_key = click.prompt("AccessKeyId from stack outputs").strip()
    secret_key = click.prompt("SecretAccessKey from stack outputs", hide_input=True).strip()

    _run_aws(["configure", "set", "aws_access_key_id", access_key, "--profile", profile])
    _run_aws(["configure", "set", "aws_secret_access_key", secret_key, "--profile", profile])
    _run_aws(["configure", "set", "region", region, "--profile", profile])
    _save_verified_profile(profile, region)


@click.group()
def auth() -> None:
    """Configure and check AWS access."""
    pass


@auth.command("setup")
@click.option("--profile", default="", help="AWS profile to configure")
@click.option("--region", default="", help="AWS region to save in amber.yaml")
def setup(profile: str, region: str) -> None:
    """Interactively configure AWS access for Amber deploys."""
    cfg = load_config()
    if not cfg.name:
        console.print("[red]No amber.yaml found. Run 'amber init' first.[/red]")
        raise SystemExit(1)

    default_region = region or cfg.region or "us-east-1"
    console.print("[bold]How do you access AWS?[/bold]")
    console.print("  1. Use AWS SSO / IAM Identity Center")
    console.print("  2. Create an Amber deploy profile with the CloudFormation helper")
    choice = click.prompt("Choose an option", type=click.Choice(["1", "2"]), default="1")

    if choice == "1":
        _setup_sso(default_region, profile, region)
    else:
        _setup_cloudformation(default_region, profile, region)


@auth.command("login")
def login() -> None:
    """Refresh the saved AWS SSO session."""
    cfg = load_config()
    if not cfg.name:
        console.print("[red]No amber.yaml found. Run 'amber init' first.[/red]")
        raise SystemExit(1)
    if not cfg.profile:
        console.print("[red]No AWS profile is configured in amber.yaml.[/red]")
        console.print("Run `amber auth setup` and choose AWS SSO first.")
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
