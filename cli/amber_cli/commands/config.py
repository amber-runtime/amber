"""amber config — manage secrets and configuration."""

import click


@click.group()
def config() -> None:
    """Manage secrets and configuration."""
    pass


@config.command("list")
def config_list() -> None:
    """Show current configuration and secrets status."""
    # TODO: read amber.yaml, check SSM/Secrets Manager values
    click.echo("Configuration:")
    click.echo("  (not yet implemented)")


@config.command("set")
@click.argument("key")
@click.option("--value", prompt=True, hide_input=True, help="Secret value")
def config_set(key: str, value: str) -> None:
    """Set a secret or configuration value."""
    # TODO: figure out SSM vs Secrets Manager based on key
    # Known keys: openai-api-key, dbos-conductor-key
    click.echo(f"Setting {key}... (not yet implemented)")
