from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
from fastapi.testclient import TestClient

from amber_cli import cli
from amber_cli.commands import dashboard as dashboard_mod


def clear_imported_dashboard_modules(monkeypatch) -> None:
    for name in ["dashboard.backend.server", "dashboard.backend", "dashboard"]:
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_dashboard_dev_requires_db_url(monkeypatch) -> None:
    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.delenv("DBOS_SYSTEM_DATABASE_URL", raising=False)

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["dashboard", "dev"])

    assert result.exit_code == 1
    assert "No database URL configured" in result.output
    assert "Set DB_URL, or DBOS_SYSTEM_DATABASE_URL" in result.output


def test_dashboard_help_describes_local_development() -> None:
    runner = CliRunner()

    group = runner.invoke(cli, ["dashboard", "--help"])
    dev = runner.invoke(cli, ["dashboard", "dev", "--help"])

    assert group.exit_code == 0
    assert "Run the local Amber dashboard for development." in group.output
    assert dev.exit_code == 0
    assert "Serve the packaged local dashboard without Cognito or AWS." in dev.output


def test_dashboard_dev_uses_packaged_assets_and_starts_uvicorn(monkeypatch) -> None:
    clear_imported_dashboard_modules(monkeypatch)
    monkeypatch.setenv("DB_URL", "postgresql://local-db")
    run_calls: list[dict] = []

    def fake_run(app, *, host: str, port: int) -> None:
        run_calls.append({"app": app, "host": host, "port": port})

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))

    result = CliRunner().invoke(
        cli,
        ["dashboard", "dev", "--host", "0.0.0.0", "--port", "9876"],
    )

    assert result.exit_code == 0
    assert run_calls
    assert run_calls[0]["host"] == "0.0.0.0"
    assert run_calls[0]["port"] == 9876
    assert "Open: http://0.0.0.0:9876/admin/" in result.output
    assert "/admin/api" not in result.output
    assert (dashboard_mod.packaged_frontend_dist() / "index.html").is_file()
    assert (dashboard_mod.packaged_control_plane() / "dashboard" / "backend" / "server.py").is_file()


def test_dashboard_dev_loads_db_url_from_dotenv(monkeypatch) -> None:
    clear_imported_dashboard_modules(monkeypatch)
    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.delenv("DBOS_SYSTEM_DATABASE_URL", raising=False)
    run_calls: list[dict] = []

    def fake_run(app, *, host: str, port: int) -> None:
        run_calls.append({"app": app, "host": host, "port": port})

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))

    with CliRunner().isolated_filesystem():
        Path(".env").write_text("DB_URL=postgresql://from-dotenv\n", encoding="utf-8")

        result = CliRunner().invoke(cli, ["dashboard", "dev"])

    assert result.exit_code == 0
    assert run_calls
    assert os.environ["DB_URL"] == "postgresql://from-dotenv"


def test_dashboard_dev_prefers_exported_db_url_over_dotenv(monkeypatch) -> None:
    clear_imported_dashboard_modules(monkeypatch)
    monkeypatch.setenv("DB_URL", "postgresql://exported")
    monkeypatch.delenv("DBOS_SYSTEM_DATABASE_URL", raising=False)
    run_calls: list[dict] = []

    def fake_run(app, *, host: str, port: int) -> None:
        run_calls.append({"app": app, "host": host, "port": port})

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))

    with CliRunner().isolated_filesystem():
        Path(".env").write_text("DB_URL=postgresql://from-dotenv\n", encoding="utf-8")

        result = CliRunner().invoke(cli, ["dashboard", "dev"])

    assert result.exit_code == 0
    assert run_calls
    assert os.environ["DB_URL"] == "postgresql://exported"


def test_local_dashboard_mounts_frontend_and_auth_disabled_api(monkeypatch) -> None:
    clear_imported_dashboard_modules(monkeypatch)
    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "postgresql://fallback-db")

    app = dashboard_mod.build_local_dashboard_app()
    client = TestClient(app)

    config = client.get("/admin/api/auth/config")
    frontend = client.get("/admin/")

    assert config.status_code == 200
    assert config.json()["enabled"] is False
    assert frontend.status_code == 200
    assert "text/html" in frontend.headers["content-type"]
    assert Path(sys.modules["dashboard.backend.server"].__file__).resolve().is_relative_to(
        dashboard_mod.packaged_control_plane().resolve()
    )
