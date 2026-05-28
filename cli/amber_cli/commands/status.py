"""amber status — show service health and registered agents."""

import click


@click.command()
@click.option("--env", default="dev", help="Deployment environment")
def status(env: str) -> None:
    """Show service health and registered agents."""
    click.echo(f"Status for {env}:")

    # TODO: implement
    # 1. Check ECS service health
    # 2. Query /health endpoint for registered agents
    # 3. Check CloudFront / dashboard URL
    # 4. Show last deployment time

    click.echo("  (not yet implemented)")
