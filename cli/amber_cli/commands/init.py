"""amber init — scaffold a new Amber agent project."""

import os
from pathlib import Path

import click

from amber_cli.config_loader import find_config_path
from amber_cli.discovery import (
    AppCandidate,
    FrontendCandidate,
    discover_app_candidates,
    discover_frontend_candidates,
)

AMBER_ORANGE = "\033[38;5;208m"
RESET = "\033[0m"


def _print_banner() -> None:
    banner = (Path(__file__).parent.parent / "assets" / "banner.txt").read_text()
    click.echo(f"{AMBER_ORANGE}{banner}{RESET}")


@click.command()
@click.option("--name", help="Project name (default: directory name)")
@click.option("--directory", default=".", help="Directory to initialize")
def init(name: str, directory: str) -> None:
    """Initialize a new Amber agent project."""

    target = Path(directory).resolve()
    config_path = target / "amber.yaml"

    if find_config_path(str(target)):
        click.echo(f"Already initialized: {config_path}")
        return

    if not name:
        name = target.name

    candidate = _select_candidate(discover_app_candidates(target))
    app_target = candidate.app_target if candidate else "my_app.main:app"
    worker_target = (
        candidate.worker_target if candidate else "my_app.main:agent_runtime"
    )
    frontend = _select_frontend(discover_frontend_candidates(target))
    environment = _prompt_environment()
    _print_banner()

    config_content = f"""# Amber Runtime configuration
# Used as the AWS resource prefix. Change this if you deploy multiple Amber apps
# in the same AWS account/environment.
name: {name}

# Explicit application entrypoints.
# app is the ASGI app served by ECS; worker is the AgentRuntime consumed by the
# queue worker process.
app: {app_target}
worker: {worker_target}
"""

    if frontend is not None:
        config_content += f"""
# React single-page app served at / from S3/CloudFront. Your API is served under
# /api (stripped before your FastAPI app); call it from React at /api/...
frontend:
  type: {frontend.framework}
  path: {frontend.rel_path(target)}
  build: {frontend.build_command}
  output: {frontend.output_dir}
path_prefix: /api
"""

    config_content += f"""
# Optional: infrastructure settings (sensible defaults applied)
environment: {environment}
# region: us-east-1
# profile: amber
# dashboard: true
"""

    os.makedirs(target, exist_ok=True)
    with open(config_path, "w") as f:
        f.write(config_content)

    gitignore_path = target / ".gitignore"
    existing = ""
    if gitignore_path.exists():
        with open(gitignore_path) as f:
            existing = f.read()
    if ".amber/" not in existing.splitlines():
        with open(gitignore_path, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(".amber/\n")

    click.echo(f"Created amber.yaml for {environment}.")
    if not candidate:
        click.echo("No app/worker pair discovered; using editable placeholders.")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Review amber.yaml")
    click.echo("  2. Configure AWS access: amber auth setup")
    click.echo("  3. Set your API key:  amber config set openai-api-key")
    click.echo("  4. Deploy:            amber deploy")
    click.echo(
        "  5. Create admin user: amber admin create-user --email <you@example.com>"
    )


def _select_candidate(candidates: list[AppCandidate]) -> AppCandidate | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    click.echo("Multiple Amber app candidates found:")
    for idx, candidate in enumerate(candidates, start=1):
        click.echo(f"  {idx}. {candidate.app_target} / {candidate.worker_target}")
    choice = click.prompt(
        "Choose the app to deploy",
        type=click.IntRange(1, len(candidates)),
        default=1,
    )
    return candidates[choice - 1]


def _select_frontend(
    candidates: list[FrontendCandidate],
) -> FrontendCandidate | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    click.echo("Multiple React frontends found:")
    for idx, candidate in enumerate(candidates, start=1):
        click.echo(f"  {idx}. {candidate.path}")
    choice = click.prompt(
        "Choose the frontend to serve",
        type=click.IntRange(1, len(candidates)),
        default=1,
    )
    return candidates[choice - 1]


def _prompt_environment() -> str:
    return click.prompt(
        "Deployment environment",
        type=click.Choice(["dev", "prod"]),
        default="dev",
        show_choices=True,
    )
