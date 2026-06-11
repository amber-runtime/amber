from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from amber_cli import cli
from amber_cli.discovery import (
    discover_app_candidates,
    discover_frontend_candidates,
)

AMBER_BANNER_PATH = Path(__file__).parents[1] / "amber_cli" / "assets" / "banner.txt"
AMBER_BANNER_LINE = next(
    line
    for line in AMBER_BANNER_PATH.read_text(encoding="utf-8").splitlines()
    if line.strip()
)


def write_package_json(
    path: Path, *, deps: dict | None = None, dev_deps: dict | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": "ui", "dependencies": deps or {}}
    if dev_deps is not None:
        data["devDependencies"] = dev_deps
    path.write_text(json.dumps(data), encoding="utf-8")


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
    assert "Created amber.yaml for dev." in result.output
    assert AMBER_BANNER_LINE in result.output
    assert result.output.index("Deployment environment") < result.output.index(
        AMBER_BANNER_LINE
    )
    assert result.output.index(AMBER_BANNER_LINE) < result.output.index(
        "Created amber.yaml for dev."
    )
    assert "Discovered app:" not in result.output
    assert "Discovered worker:" not in result.output
    assert "Review amber.yaml" in result.output
    assert "amber admin create-user --email <you@example.com>" in result.output
    assert "Local dashboard:" in result.output
    assert "Set DB_URL, run your app, then inspect local workflows with:" in result.output
    assert "amber dashboard dev" in result.output
    assert result.output.index("amber admin create-user --email <you@example.com>") < result.output.index(
        "Local dashboard:"
    )
    assert "github.com/amber-runtime/amber" not in config
    assert (
        "# Used as the AWS resource prefix. Change this if you deploy multiple Amber apps\n"
        "# in the same AWS account/environment.\n"
        "name: demo"
    ) in config
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
    assert "Created amber.yaml for prod." in result.output
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


def test_discovery_finds_react_frontend(tmp_path: Path) -> None:
    write_package_json(tmp_path / "frontend" / "package.json", deps={"react": "^18"})

    candidates = discover_frontend_candidates(tmp_path)

    assert len(candidates) == 1
    assert candidates[0].framework == "react"
    assert candidates[0].output_dir == "dist"
    assert candidates[0].rel_path(tmp_path) == "frontend"


def test_discovery_react_in_dev_dependencies(tmp_path: Path) -> None:
    write_package_json(
        tmp_path / "web" / "package.json", deps={}, dev_deps={"react": "^18"}
    )

    candidates = discover_frontend_candidates(tmp_path)

    assert len(candidates) == 1
    assert candidates[0].rel_path(tmp_path) == "web"


def test_discovery_cra_output_dir_is_build(tmp_path: Path) -> None:
    write_package_json(
        tmp_path / "frontend" / "package.json",
        deps={"react": "^18", "react-scripts": "5.0.1"},
    )

    candidates = discover_frontend_candidates(tmp_path)

    assert candidates[0].output_dir == "build"


def test_discovery_ignores_non_react_package_json(tmp_path: Path) -> None:
    write_package_json(tmp_path / "tools" / "package.json", deps={"eslint": "^9"})

    assert discover_frontend_candidates(tmp_path) == []


def test_discovery_ignores_amber_dashboard_react_frontend(tmp_path: Path) -> None:
    write_package_json(
        tmp_path / "dashboard" / "frontend" / "package.json",
        deps={"react": "^18"},
    )

    assert discover_frontend_candidates(tmp_path) == []


def test_discovery_skips_node_modules(tmp_path: Path) -> None:
    write_package_json(
        tmp_path / "frontend" / "node_modules" / "react" / "package.json",
        deps={"react": "^18"},
    )

    assert discover_frontend_candidates(tmp_path) == []


def test_init_writes_react_frontend_block() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_customer_app(root / "my_app" / "main.py")
        write_package_json(root / "frontend" / "package.json", deps={"react": "^18"})

        result = runner.invoke(cli, ["init", "--name", "demo"], input="\n")
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Discovered frontend:" not in result.output
    assert "frontend:" in config
    assert "type: react" in config
    assert "path: frontend" in config
    assert "output: dist" in config
    assert "path_prefix: /api" in config


def test_init_omits_frontend_block_without_react() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_customer_app(root / "my_app" / "main.py")

        result = runner.invoke(cli, ["init", "--name", "demo"], input="\n")
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "frontend:" not in config
    assert "path_prefix: /api" not in config


def test_init_ignores_dashboard_frontend_when_customer_has_backend_only() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_customer_app(root / "my_app" / "main.py")
        write_package_json(
            root / "dashboard" / "frontend" / "package.json",
            deps={"react": "^18"},
        )

        result = runner.invoke(cli, ["init", "--name", "demo"], input="\n")
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Discovered app:" not in result.output
    assert "Discovered frontend:" not in result.output
    assert "frontend:" not in config
    assert "path_prefix: /api" not in config


def test_init_does_not_overwrite_existing_amber_yaml() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        (root / "amber.yaml").write_text("name: existing\n", encoding="utf-8")

        result = runner.invoke(cli, ["init", "--name", "demo"])
        config = (root / "amber.yaml").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Already initialized" in result.output
    assert AMBER_BANNER_LINE not in result.output
    assert config == "name: existing\n"
