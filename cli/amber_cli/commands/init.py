"""amber init — scaffold a new Amber agent project."""

import os

import click

from amber_cli.config_loader import find_config_path


@click.command()
@click.option("--name", help="Project name (default: directory name)")
@click.option("--directory", default=".", help="Directory to initialize")
def init(name: str, directory: str) -> None:
    """Initialize a new Amber agent project."""
    target = os.path.abspath(directory)
    config_path = os.path.join(target, "amber.yaml")

    if find_config_path(target):
        click.echo(f"Already initialized: {config_path}")
        return

    if not name:
        name = os.path.basename(target)

    config_content = f"""# Amber Runtime configuration
# https://github.com/amber-runtime/playground

name: {name}

# Explicit application entrypoints.
# app is the ASGI app served by ECS; worker is the AgentRuntime consumed by the
# queue worker process.
app: my_app.main:app
worker: my_app.main:agent_runtime
path_prefix: /api

# Optional: infrastructure settings (sensible defaults applied)
# region: us-east-1
# environment: dev
# profile: amber
# dashboard: true
"""

    os.makedirs(target, exist_ok=True)
    with open(config_path, "w") as f:
        f.write(config_content)

    gitignore_path = os.path.join(target, ".gitignore")
    existing = ""
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            existing = f.read()
    if ".amber/" not in existing.splitlines():
        with open(gitignore_path, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(".amber/\n")

    click.echo(f"Created {config_path}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Edit app/worker in amber.yaml")
    click.echo("  2. Bootstrap AWS credentials if needed")
    click.echo("  3. Set your API key:  amber config set openai-api-key")
    click.echo("  4. Deploy:            amber deploy")
