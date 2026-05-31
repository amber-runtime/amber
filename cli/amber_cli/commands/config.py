"""amber config — manage secrets and configuration."""

import boto3
import click

from amber_cli.config_loader import load_config, resolve_secret_path, SECRET_REGISTRY


def _get_ssm_client(region: str):
    return boto3.client("ssm", region_name=region)


def _get_sm_client(region: str):
    return boto3.client("secretsmanager", region_name=region)


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

    ssm = _get_ssm_client(cfg.region)
    sm = _get_sm_client(cfg.region)

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

    value = click.prompt(f"Enter value for {key}", hide_input=True)
    if not value:
        click.echo("Empty value, aborting.")
        raise SystemExit(1)

    if entry["type"] == "ssm":
        ssm = _get_ssm_client(cfg.region)
        ssm.put_parameter(
            Name=entry["path"],
            Value=value,
            Type="SecureString",
            Overwrite=True,
        )
        click.echo(f"Set {key} in SSM: {entry['path']}")
    elif entry["type"] == "secretsmanager":
        sm = _get_sm_client(cfg.region)
        try:
            sm.put_secret_value(
                SecretId=entry["path"],
                SecretString=value,
            )
            click.echo(f"Set {key} in Secrets Manager: {entry['path']}")
        except sm.exceptions.ResourceNotFoundException:
            click.echo(f"Secret {entry['path']} not found. Create it in AWS first.")
            raise SystemExit(1)

    click.echo("Restart services to pick up the change: amber deploy --no-build")
