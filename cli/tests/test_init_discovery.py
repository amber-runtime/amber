from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from amber_cli import cli
from amber_cli.discovery import discover_app_candidates


def write_customer_app(path: Path, *, app_name: str = "app", worker_name: str = "agent_runtime") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "from fastapi import FastAPI",
                "from amber import AgentRuntime",
                "",
                f"{worker_name} = AgentRuntime()",
                f"{app_name} = FastAPI(lifespan={worker_name}.api_lifespan())",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_dashboard_app(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "from fastapi import FastAPI",
                "",
                'app = FastAPI(title="Admin Dashboard")',
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_discovery_finds_single_customer_app(tmp_path: Path) -> None:
    write_customer_app(tmp_path / "my_app" / "main.py")

    candidates = discover_app_candidates(tmp_path)

    assert len(candidates) == 1
    assert candidates[0].app_target == "my_app.main:app"
    assert candidates[0].worker_target == "my_app.main:agent_runtime"


def test_discovery_ignores_dashboard_only_fastapi_app(tmp_path: Path) -> None:
    write_dashboard_app(tmp_path / "dashboard" / "backend" / "server.py")

    assert discover_app_candidates(tmp_path) == []


def test_discovery_resolves_customer_app_in_monorepo_shape(tmp_path: Path) -> None:
    write_dashboard_app(tmp_path / "dashboard" / "backend" / "server.py")
    write_customer_app(tmp_path / "example_customer_app" / "main.py")

    candidates = discover_app_candidates(tmp_path)

    assert len(candidates) == 1
    assert candidates[0].app_target == "example_customer_app.main:app"
    assert candidates[0].worker_target == "example_customer_app.main:agent_runtime"


def test_init_writes_discovered_targets() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_customer_app(root / "my_app" / "main.py")

        result = runner.invoke(cli, ["init", "--name", "demo"], input="\n")
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Environment: dev" in result.output
    assert "Discovered app:    my_app.main:app" in result.output
    assert "amber admin create-user --email <you@example.com>" in result.output
    assert "app: my_app.main:app" in config
    assert "worker: my_app.main:agent_runtime" in config
    assert "environment: dev" in config


def test_init_can_write_prod_environment() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_customer_app(root / "my_app" / "main.py")

        result = runner.invoke(cli, ["init", "--name", "demo"], input="prod\n")
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Environment: prod" in result.output
    assert "environment: prod" in config


def test_init_prompts_for_multiple_customer_candidates() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_customer_app(root / "first_app" / "main.py")
        write_customer_app(root / "second_app" / "main.py")

        result = runner.invoke(cli, ["init", "--name", "demo"], input="2\n\n")
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Multiple Amber app candidates found" in result.output
    assert "app: second_app.main:app" in config
    assert "worker: second_app.main:agent_runtime" in config


def test_init_falls_back_to_manual_template_without_candidates() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)

        result = runner.invoke(cli, ["init", "--name", "demo"], input="\n")
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "No app/worker pair discovered" in result.output
    assert "app: my_app.main:app" in config
    assert "worker: my_app.main:agent_runtime" in config


def test_init_does_not_overwrite_existing_amber_yaml() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        (root / "amber.yaml").write_text("name: existing\n", encoding="utf-8")

        result = runner.invoke(cli, ["init", "--name", "demo"])
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Already initialized" in result.output
    assert config == "name: existing\n"
