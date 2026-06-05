"""Amber CLI — deploy and manage durable AI agents."""

import click

from amber_cli.commands import admin, auth, config, deploy, destroy, init, status, workflows


@click.group()
@click.version_option(version="0.1.1", prog_name="amber")
def cli():
    """Amber Runtime CLI — deploy and manage durable AI agents."""
    pass


cli.add_command(init.init)
cli.add_command(auth.auth)
cli.add_command(admin.admin)
cli.add_command(deploy.deploy)
cli.add_command(destroy.destroy)
cli.add_command(config.config)
cli.add_command(status.status)
cli.add_command(workflows.workflows)
