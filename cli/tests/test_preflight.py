from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from botocore.exceptions import ClientError

from amber_cli import preflight
from amber_cli.aws_auth import AWSAuthError
from amber_cli.config_loader import AmberConfig


@dataclass
class FakeIdentity:
    account: str = "123456789012"
    arn: str = "arn:aws:iam::123456789012:user/test"
    user_id: str = "test"


class FakeSession:
    def __init__(self, value: str | None = "sk-test", error_code: str | None = None):
        self.value = value
        self.error_code = error_code

    def client(self, service: str, region_name: str):
        assert service == "ssm"
        assert region_name == "us-west-2"
        return self

    def get_parameter(self, *, Name: str, WithDecryption: bool):
        assert Name == "/app/demo/dev/openai-api-key"
        assert WithDecryption is True
        if self.error_code:
            raise ClientError(
                {"Error": {"Code": self.error_code, "Message": self.error_code}},
                "GetParameter",
            )
        return {"Parameter": {"Value": self.value or ""}}


def config() -> AmberConfig:
    return AmberConfig(
        name="demo",
        app="my_app.main:app",
        worker="my_app.main:agent_runtime",
        profile="amber-dev",
        region="us-west-2",
        environment="dev",
    )


def write_importable_app(root: Path) -> None:
    package = root / "my_app"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "main.py").write_text(
        "\n".join(
            [
                "class FakeRuntime:",
                "    pass",
                "",
                "app = object()",
                "agent_runtime = FakeRuntime()",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_check_tooling_reports_missing_docker_and_terraform(monkeypatch) -> None:
    monkeypatch.setattr(preflight.shutil, "which", lambda _tool: None)

    errors = preflight._check_tooling()

    assert any("`terraform` is required" in error for error in errors)
    assert any("`docker` is required" in error for error in errors)


def test_check_tooling_allows_missing_docker_when_build_is_skipped(monkeypatch) -> None:
    def fake_which(tool: str) -> str | None:
        if tool == "terraform":
            return "/usr/bin/terraform"
        return None

    monkeypatch.setattr(preflight.shutil, "which", fake_which)

    assert preflight._check_tooling(require_docker=False) == []


def test_check_tooling_reports_unavailable_docker(monkeypatch) -> None:
    monkeypatch.setattr(preflight.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    def fake_run(cmd, check=False, capture_output=True, text=True):
        assert cmd == ["docker", "info"]
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="daemon unavailable")

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)

    errors = preflight._check_tooling()

    assert errors == ["Docker is not running or is unavailable. daemon unavailable"]


def test_check_assets_reports_missing_packaged_assets(monkeypatch, tmp_path: Path) -> None:
    def fake_asset_path(*parts: str) -> Path:
        return tmp_path.joinpath(*parts)

    monkeypatch.setattr(preflight, "asset_path", fake_asset_path)

    errors = preflight._check_assets()

    assert any("Missing packaged Terraform template" in error for error in errors)
    assert any("Expected exactly one packaged SDK wheel" in error for error in errors)


def test_check_assets_allows_missing_build_assets_when_build_and_frontend_are_skipped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "terraform").mkdir()
    (tmp_path / "terraform" / "main.tf").write_text("", encoding="utf-8")

    def fake_asset_path(*parts: str) -> Path:
        return tmp_path.joinpath(*parts)

    monkeypatch.setattr(preflight, "asset_path", fake_asset_path)

    assert preflight._check_assets(require_build=False, require_frontend=False) == []


def test_check_import_target_reports_invalid_target(tmp_path: Path) -> None:
    errors = preflight._check_import_target(tmp_path, "missing.module:app", "app")

    assert len(errors) == 1
    assert "Could not import app target 'missing.module:app'" in errors[0]


def test_run_deploy_preflight_reports_missing_openai_key(monkeypatch, tmp_path: Path) -> None:
    write_importable_app(tmp_path)
    monkeypatch.setattr(preflight, "_check_assets", lambda **_kwargs: [])
    monkeypatch.setattr(preflight, "_check_tooling", lambda **_kwargs: [])
    monkeypatch.setattr(
        preflight,
        "require_identity",
        lambda profile, region: (FakeSession(error_code="ParameterNotFound"), FakeIdentity()),
    )

    result = preflight.run_deploy_preflight(config(), tmp_path)

    assert not result.ok
    assert result.errors == [
        "openai-api-key is not set. Run `amber config set openai-api-key` before `amber deploy`."
    ]


def test_run_deploy_preflight_requires_saved_profile(monkeypatch, tmp_path: Path) -> None:
    write_importable_app(tmp_path)
    monkeypatch.setattr(preflight, "_check_assets", lambda **_kwargs: [])
    monkeypatch.setattr(preflight, "_check_tooling", lambda **_kwargs: [])

    cfg = config()
    cfg.profile = ""
    result = preflight.run_deploy_preflight(cfg, tmp_path)

    assert not result.ok
    assert result.errors == [
        "No AWS profile is configured in amber.yaml. Run `amber auth setup` before `amber deploy`."
    ]


def test_run_deploy_preflight_points_expired_sso_to_login(monkeypatch, tmp_path: Path) -> None:
    write_importable_app(tmp_path)
    monkeypatch.setattr(preflight, "_check_assets", lambda **_kwargs: [])
    monkeypatch.setattr(preflight, "_check_tooling", lambda **_kwargs: [])

    def fake_require_identity(profile: str, region: str):
        raise AWSAuthError("The AWS session for profile 'amber-dev' is missing, invalid, or expired.")

    monkeypatch.setattr(preflight, "require_identity", fake_require_identity)

    result = preflight.run_deploy_preflight(config(), tmp_path)

    assert not result.ok
    assert result.errors == [
        "AWS SSO session is invalid or expired: The AWS session for profile 'amber-dev' is missing, invalid, or expired. Run `amber auth login`."
    ]


def test_run_deploy_preflight_reports_placeholder_openai_key(monkeypatch, tmp_path: Path) -> None:
    write_importable_app(tmp_path)
    monkeypatch.setattr(preflight, "_check_assets", lambda **_kwargs: [])
    monkeypatch.setattr(preflight, "_check_tooling", lambda **_kwargs: [])
    monkeypatch.setattr(
        preflight,
        "require_identity",
        lambda profile, region: (FakeSession(value="placeholder-set-me"), FakeIdentity()),
    )

    result = preflight.run_deploy_preflight(config(), tmp_path)

    assert not result.ok
    assert result.errors == [
        "openai-api-key is still a placeholder. Run `amber config set openai-api-key` before `amber deploy`."
    ]


def test_run_deploy_preflight_passes(monkeypatch, tmp_path: Path) -> None:
    write_importable_app(tmp_path)
    monkeypatch.setattr(preflight, "_check_assets", lambda **_kwargs: [])
    monkeypatch.setattr(preflight, "_check_tooling", lambda **_kwargs: [])
    monkeypatch.setattr(
        preflight,
        "require_identity",
        lambda profile, region: (FakeSession(value="sk-test"), FakeIdentity()),
    )

    result = preflight.run_deploy_preflight(config(), tmp_path)

    assert result.ok
    assert result.identity == FakeIdentity()
