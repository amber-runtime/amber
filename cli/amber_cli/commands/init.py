"""amber init — scaffold a new Amber agent project."""

import os

import click


@click.command()
@click.option("--name", prompt="Project name", help="Name of your agent project")
@click.option("--directory", default=".", help="Directory to initialize")
def init(name: str, directory: str) -> None:
    """Initialize a new Amber agent project."""
    target = os.path.abspath(directory)
    config_path = os.path.join(target, "amber.yaml")

    if os.path.exists(config_path):
        click.echo(f"Already initialized: {config_path}")
        return

    # TODO: detect existing agents from decorators in the codebase
    config_content = f"""# Amber Runtime configuration
# https://github.com/amber-runtime/playground

name: {name}

# Agents are auto-detected from @agent decorators in your code.
# Override here if needed:
# agents:
#   - my-agent

# Optional: infrastructure settings (sensible defaults applied)
# region: us-east-1
# environment: dev
# dashboard: true
"""

    os.makedirs(target, exist_ok=True)
    with open(config_path, "w") as f:
        f.write(config_content)

    click.echo(f"Created {config_path}")
    click.echo("Next: amber deploy")
