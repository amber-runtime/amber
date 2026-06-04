from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from amber_cli import cli
from amber_cli import dashboard_api, dashboard_auth


def write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: test-project",
                "app: my_app.main:app",
                "worker: my_app.main:agent_runtime",
                "region: us-west-2",
                "environment: dev",
                "profile: amber-dev",
                "",
            ]
        ),
        encoding="utf-8",
    )


def make_http_get(captured: list[dict], payload: dict):
    def fake_http_get(url: str, headers: dict) -> tuple[int, str]:
        captured.append({"url": url, "headers": headers})
        return 200, json.dumps(payload)

    return fake_http_get


def patch_context(monkeypatch, token: str = "tok-123") -> None:
    monkeypatch.setattr(
        dashboard_api,
        "resolve_context",
        lambda config_path: ("https://cf.example.com/admin/api", token),
    )


def test_workflows_list_sends_bearer_and_renders_table(monkeypatch) -> None:
    runner = CliRunner()
    captured: list[dict] = []
    payload = {
        "workflows": [
            {
                "workflow_id": "wf-1",
                "name": "ingest",
                "status": "SUCCESS",
                "created_at": 1_700_000_000_000,
                "completed_at": 1_700_000_100_000,
                "recovery_attempts": 1,
            }
        ],
        "has_more": False,
    }
    patch_context(monkeypatch)
    monkeypatch.setattr(dashboard_api, "_http_get", make_http_get(captured, payload))

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")
        result = runner.invoke(cli, ["workflows", "list", "--status", "SUCCESS", "--limit", "10"])

    assert result.exit_code == 0, result.output
    assert captured[0]["headers"]["Authorization"] == "Bearer tok-123"
    assert "/admin/api/workflows" in captured[0]["url"]
    assert "status=SUCCESS" in captured[0]["url"]
    assert "limit=10" in captured[0]["url"]
    assert "wf-1" in result.output
    assert "ingest" in result.output


def test_workflows_list_json_emits_raw_payload(monkeypatch) -> None:
    runner = CliRunner()
    payload = {"workflows": [{"workflow_id": "wf-1", "name": "n", "status": "PENDING",
                              "created_at": None, "completed_at": None,
                              "recovery_attempts": None}], "has_more": True}
    patch_context(monkeypatch)
    monkeypatch.setattr(dashboard_api, "_http_get", make_http_get([], payload))

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")
        result = runner.invoke(cli, ["workflows", "list", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == payload


def test_workflows_queued_sends_bearer_and_queue_param(monkeypatch) -> None:
    runner = CliRunner()
    captured: list[dict] = []
    payload = {
        "workflows": [
            {
                "workflow_id": "wf-9",
                "name": "batch",
                "status": "ENQUEUED",
                "created_at": 1_700_000_000_000,
                "queue_name": "default",
                "recovery_attempts": None,
            }
        ],
        "has_more": False,
    }
    patch_context(monkeypatch)
    monkeypatch.setattr(dashboard_api, "_http_get", make_http_get(captured, payload))

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")
        result = runner.invoke(cli, ["workflows", "queued", "--queue-name", "default"])

    assert result.exit_code == 0, result.output
    assert captured[0]["headers"]["Authorization"] == "Bearer tok-123"
    assert "/admin/api/queued-workflows" in captured[0]["url"]
    assert "queue_name=default" in captured[0]["url"]
    assert "wf-9" in result.output


def test_workflows_show_renders_detail(monkeypatch) -> None:
    runner = CliRunner()
    captured: list[dict] = []
    payload = {
        "workflow": {
            "workflow_id": "wf-1",
            "name": "ingest",
            "status": "SUCCESS",
            "created_at": 1_700_000_000_000,
            "updated_at": 1_700_000_100_000,
            "recovery_attempts": 1,
        },
        "steps": [
            {
                "step_id": 0,
                "function_name": "fetch",
                "event_type": "step",
                "status": "SUCCESS",
                "duration_ms": 12,
            }
        ],
        "events": [],
    }
    patch_context(monkeypatch)
    monkeypatch.setattr(dashboard_api, "_http_get", make_http_get(captured, payload))

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")
        result = runner.invoke(cli, ["workflows", "show", "wf-1"])

    assert result.exit_code == 0, result.output
    assert captured[0]["headers"]["Authorization"] == "Bearer tok-123"
    assert "/admin/api/workflows/wf-1" in captured[0]["url"]
    assert "ingest" in result.output
    assert "fetch" in result.output


def test_workflows_401_points_to_login(monkeypatch) -> None:
    runner = CliRunner()
    patch_context(monkeypatch)

    def fake_http_get(url: str, headers: dict) -> tuple[int, str]:
        return 401, "Unauthorized"

    monkeypatch.setattr(dashboard_api, "_http_get", fake_http_get)

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")
        result = runner.invoke(cli, ["workflows", "list"])

    assert result.exit_code == 1
    assert "amber admin login" in result.output


def test_workflows_missing_session_points_to_login(monkeypatch) -> None:
    runner = CliRunner()

    def raise_auth(config_path):
        raise dashboard_auth.DashboardAuthError(dashboard_auth.LOGIN_HINT)

    monkeypatch.setattr(dashboard_api, "resolve_context", raise_auth)

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")
        result = runner.invoke(cli, ["workflows", "list"])

    assert result.exit_code == 1
    assert "amber admin login" in result.output


def test_workflows_missing_terraform_outputs_message(monkeypatch) -> None:
    runner = CliRunner()

    def raise_api(config_path):
        raise dashboard_api.DashboardAPIError(dashboard_api.NO_OUTPUTS_MESSAGE)

    monkeypatch.setattr(dashboard_api, "resolve_context", raise_api)

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")
        result = runner.invoke(cli, ["workflows", "list"])

    assert result.exit_code == 1
    assert "Could not read .amber terraform outputs" in result.output
