"""amber dashboard - run the packaged Amber dashboard locally."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from rich.console import Console
from starlette.exceptions import HTTPException as StarletteHTTPException

from amber_cli.assets import asset_path

console = Console()


class DashboardCommandError(click.ClickException):
    """Raised when the local dashboard cannot be started."""


class SPAStaticFiles(StaticFiles):
    """Serve index.html for React Router paths under /admin/."""

    async def get_response(self, path: str, scope: dict[str, Any]):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return FileResponse(Path(self.directory) / "index.html")
        if response.status_code != 404:
            return response
        return FileResponse(Path(self.directory) / "index.html")


def packaged_frontend_dist() -> Path:
    return asset_path("frontend", "dist")


def packaged_control_plane() -> Path:
    return asset_path("control_plane")


def resolve_db_url() -> str:
    return os.environ.get("DB_URL") or os.environ.get("DBOS_SYSTEM_DATABASE_URL") or ""


def clear_dashboard_modules() -> None:
    for name in list(sys.modules):
        if name == "dashboard" or name.startswith("dashboard."):
            del sys.modules[name]


def build_local_dashboard_app(db_url: str | None = None) -> FastAPI:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    resolved_db_url = db_url or resolve_db_url()
    if not resolved_db_url:
        raise DashboardCommandError(
            "No database URL configured. Set DB_URL, or DBOS_SYSTEM_DATABASE_URL as a fallback, "
            "before running `amber dashboard dev`."
        )

    frontend_dist = packaged_frontend_dist()
    if not (frontend_dist / "index.html").is_file():
        raise DashboardCommandError(
            f"Packaged dashboard frontend assets were not found at {frontend_dist}. "
            "Rebuild the package assets with `make cli-wheelhouse`."
        )

    control_plane = packaged_control_plane()
    if not (control_plane / "dashboard" / "backend" / "server.py").is_file():
        raise DashboardCommandError(
            f"Packaged dashboard backend assets were not found at {control_plane}. "
            "Rebuild the package assets with `make cli-wheelhouse`."
        )

    os.environ["DB_URL"] = resolved_db_url
    os.environ["AMBER_DASHBOARD_AUTH"] = "disabled"
    clear_dashboard_modules()
    if str(control_plane) not in sys.path:
        sys.path.insert(0, str(control_plane))

    from dashboard.backend.server import app as backend_app

    app = FastAPI(title="Amber Local Dashboard")
    app.mount("/admin/api", backend_app)
    app.mount("/admin", SPAStaticFiles(directory=str(frontend_dist), html=True), name="dashboard")
    return app


@click.group(short_help="Run the local Amber dashboard.")
def dashboard() -> None:
    """Run the local Amber dashboard for development."""


@dashboard.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind.")
@click.option("--port", default=8765, show_default=True, type=int, help="Port to bind.")
def dev(host: str, port: int) -> None:
    """Serve the packaged local dashboard without Cognito or AWS."""
    app = build_local_dashboard_app()

    import uvicorn

    console.print("[green]Amber dashboard running locally.[/green]")
    console.print(f"Open: http://{host}:{port}/admin/")
    console.print("Auth: disabled")
    uvicorn.run(app, host=host, port=port)
