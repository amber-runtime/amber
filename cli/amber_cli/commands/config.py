"""amber config — manage secrets and configuration."""

import json
import subprocess
from pathlib import Path

import click
from rich.console import Console

from amber_cli.aws_auth import AWSAuthError, create_session, print_auth_error, verify_identity
from amber_cli.config_loader import find_config_path, load_config, resolve_secret_path, SECRET_REGISTRY

console = Console()

SERVICE_OUTPUT_KEYS = [
    "dashboard_api_service_name",
    "customer_app_service_name",
    "customer_worker_service_name",
]


def _session(cfg):
    return create_session(cfg.profile, cfg.region)


def _require_auth(cfg, retry_command: str) -> None:
    try:
        verify_identity(cfg.profile, cfg.region)
    except AWSAuthError as exc:
        print_auth_error(console, exc, retry_command)
        raise SystemExit(1) from exc


def _get_ssm_client(cfg):
    return _session(cfg).client("ssm", region_name=cfg.region)


def _get_sm_client(cfg):
    return _session(cfg).client("secretsmanager", region_name=cfg.region)


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def _terraform_output(tf_dir: Path) -> dict[str, object]:
    result = _run(["terraform", "output", "-json"], cwd=tf_dir)
    raw = json.loads(result.stdout)
    return {k: v["value"] for k, v in raw.items()}


def _deployed_ecs_stack_exists(cfg) -> bool:
    config_path = find_config_path()
    if not config_path:
        return False

    repo_root = Path(config_path).resolve().parent
    tf_dir = repo_root / ".amber" / "terraform"
    if not tf_dir.is_dir():
        return False

    try:
        tf_out = _terraform_output(tf_dir)
        cluster = str(tf_out.get("ecs_cluster_name") or "")
        service_names = [str(tf_out.get(key) or "") for key in SERVICE_OUTPUT_KEYS]
        if not cluster or any(not name for name in service_names):
            return False

        ecs = _session(cfg).client("ecs", region_name=cfg.region)
        response = ecs.describe_services(cluster=cluster, services=service_names)
    except Exception:
        return False

    failures = response.get("failures", [])
    services = response.get("services", [])
    active_names = {
        service.get("serviceName")
        for service in services
        if service.get("status") == "ACTIVE"
    }
    return not failures and set(service_names).issubset(active_names)


def _print_secret_next_step(cfg) -> None:
    if _deployed_ecs_stack_exists(cfg):
        click.echo("Secret saved. Restart services to pick up the change: amber deploy --no-build")
    else:
        click.echo("Secret saved. Continue the first deploy with: amber deploy")


@click.group()
def config() -> None:
    """Manage secrets and configuration."""
    pass


@config.command("list")
def config_list() -> None:
    """Show current configuration and secrets status."""
    cfg = load_config()

    if not cfg.name:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        return

    click.echo(f"Project: {cfg.name}")
    click.echo(f"Region:  {cfg.region}")
    click.echo(f"Env:     {cfg.environment}")
    click.echo()

    _require_auth(cfg, "amber config list")
    ssm = _get_ssm_client(cfg)
    sm = _get_sm_client(cfg)

    click.echo("Secrets:")
    for key, meta in SECRET_REGISTRY.items():
        readonly = meta.get("readonly", False)
        desc = meta["description"]
        tag = " (read-only)" if readonly else ""

        try:
            if meta["type"] == "ssm":
                path = meta["path"].format(
                    ssm_base=cfg.ssm_base,
                    secrets_prefix=cfg.secrets_prefix,
                )
                resp = ssm.get_parameter(Name=path, WithDecryption=False)
                click.echo(f"  {key}: set{tag}")
            elif meta["type"] == "secretsmanager":
                path = meta["path"].format(
                    ssm_base=cfg.ssm_base,
                    secrets_prefix=cfg.secrets_prefix,
                )
                sm.describe_secret(SecretId=path)
                click.echo(f"  {key}: set{tag}")
        except ssm.exceptions.ParameterNotFound:
            click.echo(f"  {key}: NOT SET - {desc}")
        except sm.exceptions.ResourceNotFoundException:
            click.echo(f"  {key}: NOT SET - {desc}")
        except Exception as e:
            click.echo(f"  {key}: error - {e}")


@config.command("set")
@click.argument("key")
def config_set(key: str) -> None:
    """Set a secret value.

    Known keys: openai-api-key
    """
    cfg = load_config()
    if not cfg.name:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        return

    try:
        entry = resolve_secret_path(key, cfg)
    except ValueError as e:
        click.echo(str(e))
        raise SystemExit(1)

    if entry.get("readonly"):
        click.echo(f"{key} is read-only (managed by AWS).")
        raise SystemExit(1)

    _require_auth(cfg, f"amber config set {key}")
    value = click.prompt(f"Enter value for {key}", hide_input=True)
    if not value:
        click.echo("Empty value, aborting.")
        raise SystemExit(1)

    if entry["type"] == "ssm":
        ssm = _get_ssm_client(cfg)
        ssm.put_parameter(
            Name=entry["path"],
            Value=value,
            Type="SecureString",
            Overwrite=True,
        )
        click.echo(f"Set {key} in SSM: {entry['path']}")
    elif entry["type"] == "secretsmanager":
        sm = _get_sm_client(cfg)
        try:
            sm.put_secret_value(
                SecretId=entry["path"],
                SecretString=value,
            )
            click.echo(f"Set {key} in Secrets Manager: {entry['path']}")
        except sm.exceptions.ResourceNotFoundException:
            click.echo(f"Secret {entry['path']} not found. Create it in AWS first.")
            raise SystemExit(1)

    _print_secret_next_step(cfg)
