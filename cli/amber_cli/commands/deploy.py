"""amber deploy — build and deploy agents to the cloud."""

import click


@click.command()
@click.option("--env", default="dev", help="Deployment environment")
@click.option("--no-build", is_flag=True, help="Skip Docker build (use existing image)")
@click.option("--no-infra", is_flag=True, help="Skip terraform (use existing infra)")
def deploy(env: str, no_build: bool, no_infra: bool) -> None:
    """Build and deploy your agents to the cloud."""
    click.echo(f"Deploying to {env}...")

    # TODO: implement the pipeline
    # 1. Load amber.yaml
    # 2. Detect agents from decorators
    # 3. Build Docker image(s) if needed
    # 4. Push to ECR
    # 5. terraform apply if needed
    # 6. Restart ECS services
    # 7. Deploy dashboard frontend
    # 8. Print URL

    click.echo("Not yet implemented — coming soon")
