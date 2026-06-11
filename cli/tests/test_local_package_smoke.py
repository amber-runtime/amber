from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("AMBER_RUN_PACKAGE_SMOKE") != "1",
    reason="set AMBER_RUN_PACKAGE_SMOKE=1 to run the local wheel packaging smoke test",
)
def test_local_wheel_install_behaves_like_product_package(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()

    subprocess.run(["make", "cli-assets"], cwd=ROOT, check=True)
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(wheelhouse)],
        cwd=ROOT / "sdk",
        check=True,
    )
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(wheelhouse)],
        cwd=ROOT / "cli",
        check=True,
    )

    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = venv / "bin" / "python"
    amber = venv / "bin" / "amber"
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--find-links",
            str(wheelhouse),
            "amber-runtime",
        ],
        check=True,
    )

    help_result = subprocess.run(
        [str(amber), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Amber Runtime CLI" in help_result.stdout

    asset_result = subprocess.run(
        [
            str(python),
            "-c",
            "\n".join(
                [
                    "from amber_cli.assets import asset_path",
                    "required = [",
                    "    asset_path('frontend', 'dist', 'index.html'),",
                    "    asset_path('control_plane', 'dashboard', 'backend', 'server.py'),",
                    "    asset_path('docker', 'Dockerfile.dashboard-api'),",
                    "    asset_path('docker', 'Dockerfile.customer-app'),",
                    "    asset_path('docker', 'Dockerfile.customer-worker'),",
                    "    asset_path('terraform', 'main.tf'),",
                    "    asset_path('terraform', 'ecs.tf'),",
                    "]",
                    "missing = [str(path) for path in required if not path.is_file()]",
                    "assert not missing, missing",
                ]
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert asset_result.returncode == 0

    customer = tmp_path / "customer"
    app_dir = customer / "my_app"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "main.py").write_text(
        "\n".join(
            [
                "from fastapi import FastAPI",
                "from amber import AgentRuntime",
                "",
                "agent_runtime = AgentRuntime()",
                "app = FastAPI(lifespan=agent_runtime.api_lifespan())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    init_result = subprocess.run(
        [str(amber), "init", "--name", "smoke-app"],
        cwd=customer,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Discovered app:    my_app.main:app" in init_result.stdout
    config = (customer / "amber.yaml").read_text(encoding="utf-8")
    assert "app: my_app.main:app" in config
    assert "worker: my_app.main:agent_runtime" in config

    deploy_result = subprocess.run(
        [str(amber), "deploy"],
        cwd=customer,
        check=False,
        capture_output=True,
        text=True,
    )
    assert deploy_result.returncode != 0
    assert "Preflight: checking deploy prerequisites" in deploy_result.stdout
