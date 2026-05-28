"""Amber CLI — deploy and manage durable AI agents."""

import click

from amber_cli.commands import deploy, init, config, status


@click.group()
@click.version_option(version="0.1.0", prog_name="amber")
def cli():
    """Amber Runtime CLI — deploy and manage durable AI agents."""
    pass


cli.add_command(init.init)
cli.add_command(deploy.deploy)
cli.add_command(config.config)
cli.add_command(status.status)
