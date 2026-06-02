"""Prepare package assets for the Amber CLI wheel."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = ROOT / "cli"
ASSETS = CLI_ROOT / "amber_cli" / "assets"


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_tree(src: Path, dst: Path, ignore: shutil.IgnorePattern | None = None) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def prepare_terraform() -> None:
    dst = ASSETS / "terraform"
    clean_dir(dst)
    for item in (ROOT / "infra" / "terraform").glob("*.tf"):
        shutil.copy2(item, dst / item.name)
    example = ROOT / "infra" / "terraform" / "terraform.tfvars.example"
    if example.exists():
        shutil.copy2(example, dst / example.name)


def prepare_docker() -> None:
    dst = ASSETS / "docker"
    clean_dir(dst)
    src_dir = CLI_ROOT / "amber_cli" / "asset_sources" / "docker"
    for item in src_dir.iterdir():
        shutil.copy2(item, dst / item.name)


def prepare_control_plane() -> None:
    dst = ASSETS / "control_plane"
    clean_dir(dst)
    copy_tree(ROOT / "admin_control_plane", dst / "admin_control_plane", shutil.ignore_patterns("__pycache__", "*.pyc"))
    (dst / "pyproject.toml").write_text(
        """[project]
name = "amber-control-plane"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "httpx>=0.28.1",
    "psycopg2-binary>=2.9.12",
    "python-dotenv>=1.2.2",
    "pydantic>=2.13.3",
]

[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["admin_control_plane*"]
""",
        encoding="utf-8",
    )


def prepare_sdk() -> None:
    dst = ASSETS / "sdk"
    clean_dir(dst)
    out_dir = dst.resolve()
    run(["uv", "build", "--wheel", "--out-dir", str(out_dir)], cwd=ROOT / "sdk")


def prepare_frontend() -> None:
    dst = ASSETS / "frontend" / "dist"
    clean_dir(dst)
    env = os.environ.copy()
    env["VITE_API_BASE_URL"] = "/dashboard"
    run(["npm", "ci"], cwd=ROOT / "dashboard", env=env)
    run(["npm", "run", "build"], cwd=ROOT / "dashboard", env=env)
    copy_tree(ROOT / "dashboard" / "dist", dst)


def prepare_bootstrap() -> None:
    dst = ASSETS / "bootstrap"
    clean_dir(dst)
    src = CLI_ROOT / "amber_cli" / "asset_sources" / "bootstrap" / "amber-bootstrap.yaml"
    shutil.copy2(src, dst / src.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-builds", action="store_true", help="Skip SDK wheel and frontend builds")
    args = parser.parse_args()

    ASSETS.mkdir(parents=True, exist_ok=True)
    prepare_terraform()
    prepare_docker()
    prepare_control_plane()
    prepare_bootstrap()
    if not args.skip_builds:
        prepare_sdk()
        prepare_frontend()


if __name__ == "__main__":
    main()
