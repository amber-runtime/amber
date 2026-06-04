"""Preflight checks for amber deploy."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from botocore.exceptions import ClientError

from amber_cli.assets import asset_path
from amber_cli.aws_auth import AWSAuthError, require_identity
from amber_cli.config_loader import AmberConfig, resolve_secret_path, validate_deploy_config


@dataclass
class PreflightResult:
    session: object | None = None
    identity: object | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_deploy_preflight(
    cfg: AmberConfig,
    repo_root: Path,
    *,
    require_build: bool = True,
    require_frontend: bool = True,
) -> PreflightResult:
    """Validate local and AWS prerequisites before deploy mutates anything."""
    result = PreflightResult()
    needs_frontend_build = require_frontend and _needs_frontend_build(cfg)
    result.errors.extend(validate_deploy_config(cfg))
    result.errors.extend(_check_assets(require_build=require_build, require_frontend=require_frontend))
    result.errors.extend(
        _check_tooling(require_docker=require_build or needs_frontend_build)
    )
    if needs_frontend_build:
        result.errors.extend(_check_customer_frontend(repo_root, cfg))
    result.errors.extend(_check_import_target(repo_root, cfg.app, "app"))
    result.errors.extend(_check_import_target(repo_root, cfg.worker, "worker"))
    if not cfg.profile:
        result.errors.append(
            "No AWS profile is configured in amber.yaml. Run `amber auth setup` before `amber deploy`."
        )
        return result

    try:
        session, identity = require_identity(cfg.profile, cfg.region)
        result.session = session
        result.identity = identity
    except AWSAuthError as exc:
        result.errors.append(_auth_error_message(exc))
        return result

    secret_error = _check_openai_key(session, cfg)
    if secret_error:
        result.errors.append(secret_error)
    return result


def _auth_error_message(exc: AWSAuthError) -> str:
    text = str(exc).rstrip(".")
    lower = text.lower()
    if any(token in lower for token in ["sso", "session", "token", "expired"]):
        return f"AWS SSO session is invalid or expired: {text}. Run `amber auth login`."
    return f"AWS credentials are invalid: {text}. Run `amber auth setup`."


def _check_assets(*, require_build: bool = True, require_frontend: bool = True) -> list[str]:
    errors: list[str] = []
    required_files = [
        ("Terraform template", asset_path("terraform", "main.tf")),
    ]
    if require_build:
        required_files.extend(
            [
                ("customer app Dockerfile", asset_path("docker", "Dockerfile.customer-app")),
                ("customer worker Dockerfile", asset_path("docker", "Dockerfile.customer-worker")),
                ("dashboard API Dockerfile", asset_path("docker", "Dockerfile.dashboard-api")),
            ]
        )
    if require_frontend:
        required_files.append(("frontend bundle", asset_path("frontend", "dist", "index.html")))
    for label, path in required_files:
        if not path.exists():
            errors.append(f"Missing packaged {label}: {path}. Run `make cli-assets`.")

    if require_build:
        wheels = sorted(asset_path("sdk").glob("*.whl"))
        if len(wheels) != 1:
            errors.append(
                f"Expected exactly one packaged SDK wheel, found {len(wheels)}. Run `make cli-assets`."
            )
    return errors


def _needs_frontend_build(cfg: AmberConfig) -> bool:
    return cfg.frontend is not None and cfg.frontend.type == "react"


def _check_customer_frontend(repo_root: Path, cfg: AmberConfig) -> list[str]:
    """Ensure a declared React frontend actually exists on disk before deploy."""
    if not _needs_frontend_build(cfg):
        return []
    fe = cfg.frontend
    if not fe.path:
        return []  # already reported by validate_deploy_config
    frontend_dir = (repo_root / fe.path).resolve()
    if not frontend_dir.is_dir():
        return [f"frontend.path does not exist: {frontend_dir}."]
    if not (frontend_dir / "package.json").is_file():
        return [f"No package.json in frontend.path: {frontend_dir}."]
    return []


def _check_tooling(*, require_docker: bool = True) -> list[str]:
    errors: list[str] = []
    required_tools = [("terraform", "Install Terraform and make sure it is on PATH.")]
    if require_docker:
        required_tools.append(("docker", "Install/start Docker and make sure it is on PATH."))
    for tool, install_hint in required_tools:
        if shutil.which(tool) is None:
            errors.append(f"`{tool}` is required. {install_hint}")

    if require_docker and shutil.which("docker") is not None:
        result = subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            errors.append(f"Docker is not running or is unavailable. {detail}")
    return errors


def _check_import_target(repo_root: Path, target: str, label: str) -> list[str]:
    if not target:
        return []
    if ":" not in target:
        return [f"{label} target must use module:attribute syntax, got {target!r}."]
    module, attr = target.split(":", 1)
    if not module or not attr:
        return [f"{label} target must use module:attribute syntax, got {target!r}."]

    code = """
import importlib
import pathlib
import sys

repo_root = pathlib.Path(sys.argv[1])
module_name = sys.argv[2]
attr_name = sys.argv[3]
sys.path.insert(0, str(repo_root))
module = importlib.import_module(module_name)
obj = module
for part in attr_name.split("."):
    obj = getattr(obj, part)
"""
    proc = subprocess.run(
        [sys.executable, "-c", code, str(repo_root), module, attr],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if proc.returncode == 0:
        return []
    detail = (proc.stderr or proc.stdout).strip().splitlines()[-1:]
    suffix = f": {detail[0]}" if detail else ""
    return [f"Could not import {label} target {target!r}{suffix}."]


def _check_openai_key(session, cfg: AmberConfig) -> str:
    entry = resolve_secret_path("openai-api-key", cfg)
    ssm = session.client("ssm", region_name=cfg.region)
    try:
        resp = ssm.get_parameter(Name=entry["path"], WithDecryption=True)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ParameterNotFound":
            return (
                "openai-api-key is not set. Run `amber config set openai-api-key` "
                "before `amber deploy`."
            )
        return f"Could not read openai-api-key from SSM: {exc}."

    value = resp.get("Parameter", {}).get("Value", "")
    if not value or "placeholder" in value.lower() or "set-me" in value.lower():
        return (
            "openai-api-key is still a placeholder. Run `amber config set openai-api-key` "
            "before `amber deploy`."
        )
    return ""
