from __future__ import annotations

import subprocess
import runpy
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from amber_cli.commands import deploy as deploy_mod


@dataclass
class FakeConfig:
    name: str = "test-project"
    project_prefix: str = ""
    environment: str = "dev"
    region: str = "us-west-2"
    app: str = "my_app.main:app"
    worker: str = "my_app.main:agent_runtime"
    path_prefix: str = "/api"

    @property
    def ssm_base(self) -> str:
        return f"/app/{self.project_prefix or self.name}/{self.environment}"

    @property
    def secrets_prefix(self) -> str:
        return f"{self.project_prefix or self.name}-{self.environment}"


class FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self, service: str, region_name: str):
        assert service == "ssm"
        assert region_name == "us-west-2"
        return self._client


class FakeSSM:
    def __init__(self, error_code: str | None = None):
        self.error_code = error_code

    def get_parameter(self, *, Name: str, WithDecryption: bool):
        assert Name == "/app/test-project/dev/openai-api-key"
        assert WithDecryption is False
        if self.error_code:
            raise ClientError(
                {"Error": {"Code": self.error_code, "Message": self.error_code}},
                "GetParameter",
            )
        return {"Parameter": {"Name": Name}}


def test_import_existing_openai_parameter_when_unmanaged(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, check=True):
        calls.append(cmd)
        assert cwd == tmp_path
        if cmd == ["terraform", "state", "list"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    def fake_run_with_status(cmd, cwd, message):
        calls.append(cmd)
        assert cwd == tmp_path
        assert "Importing existing OpenAI API key parameter" in message
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(deploy_mod, "_run", fake_run)
    monkeypatch.setattr(deploy_mod, "_run_with_status", fake_run_with_status)

    deploy_mod._import_existing_openai_parameter(
        FakeSession(FakeSSM()),
        FakeConfig(),
        tmp_path,
        "us-west-2",
    )

    assert calls == [
        ["terraform", "state", "list"],
        [
            "terraform",
            "import",
            "aws_ssm_parameter.openai_api_key",
            "/app/test-project/dev/openai-api-key",
        ],
    ]


def test_import_existing_openai_parameter_skips_managed_resource(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, check=True):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="aws_ssm_parameter.openai_api_key\n",
            stderr="",
        )

    def fake_run_with_status(cmd, cwd, message):
        raise AssertionError("terraform import should not run")

    monkeypatch.setattr(deploy_mod, "_run", fake_run)
    monkeypatch.setattr(deploy_mod, "_run_with_status", fake_run_with_status)

    deploy_mod._import_existing_openai_parameter(
        FakeSession(FakeSSM()),
        FakeConfig(),
        tmp_path,
        "us-west-2",
    )

    assert calls == [["terraform", "state", "list"]]


def test_import_existing_openai_parameter_skips_missing_parameter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_run(cmd, cwd=None, check=True):
        raise AssertionError("terraform state should not be checked")

    def fake_run_with_status(cmd, cwd, message):
        raise AssertionError("terraform import should not run")

    monkeypatch.setattr(deploy_mod, "_run", fake_run)
    monkeypatch.setattr(deploy_mod, "_run_with_status", fake_run_with_status)

    deploy_mod._import_existing_openai_parameter(
        FakeSession(FakeSSM(error_code="ParameterNotFound")),
        FakeConfig(),
        tmp_path,
        "us-west-2",
    )


def test_import_existing_openai_parameter_surfaces_access_denied(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        deploy_mod._import_existing_openai_parameter(
            FakeSession(FakeSSM(error_code="AccessDeniedException")),
            FakeConfig(),
            tmp_path,
            "us-west-2",
        )


def test_image_tag_includes_git_sha_and_timestamp(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd, cwd=None, check=True):
        assert cmd == ["git", "rev-parse", "--short", "HEAD"]
        assert cwd == tmp_path
        assert check is False
        return subprocess.CompletedProcess(cmd, 0, stdout="abc1234\n", stderr="")

    monkeypatch.setattr(deploy_mod, "_run", fake_run)
    monkeypatch.setattr(deploy_mod.time, "time", lambda: 1_717_171_717)

    assert deploy_mod._image_tag(tmp_path) == "abc1234-1717171717"


def test_image_tag_falls_back_to_timestamp_without_git(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd, cwd=None, check=True):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a git repo")

    monkeypatch.setattr(deploy_mod, "_run", fake_run)
    monkeypatch.setattr(deploy_mod.time, "time", lambda: 1_717_171_718)

    assert deploy_mod._image_tag(tmp_path) == "1717171718"


def test_write_tfvars_uses_dev_disposable_defaults(tmp_path: Path) -> None:
    deploy_mod._write_tfvars(tmp_path, FakeConfig(environment="dev"), "tag")

    tfvars = (tmp_path / "terraform.tfvars").read_text(encoding="utf-8")

    assert 'environment = "dev"' in tfvars
    assert "frontend_bucket_force_destroy = true" in tfvars
    assert "secrets_force_destroy = true" in tfvars
    assert "db_multi_az = false" in tfvars
    assert "db_deletion_protection = false" in tfvars
    assert "db_skip_final_snapshot = true" in tfvars
    assert "db_delete_automated_backups = true" in tfvars
    assert "db_backup_retention_period = 7" in tfvars
    assert 'db_instance_class = "db.t4g.micro"' in tfvars
    assert "db_allocated_storage = 20" in tfvars


def test_write_tfvars_uses_prod_hardened_defaults(tmp_path: Path) -> None:
    deploy_mod._write_tfvars(tmp_path, FakeConfig(environment="prod"), "tag")

    tfvars = (tmp_path / "terraform.tfvars").read_text(encoding="utf-8")

    assert 'environment = "prod"' in tfvars
    assert "frontend_bucket_force_destroy = false" in tfvars
    assert "secrets_force_destroy = false" in tfvars
    assert "db_multi_az = true" in tfvars
    assert "db_deletion_protection = true" in tfvars
    assert "db_skip_final_snapshot = false" in tfvars
    assert "db_delete_automated_backups = false" in tfvars
    assert "db_backup_retention_period = 30" in tfvars
    assert 'db_instance_class = "db.t4g.small"' in tfvars
    assert "db_allocated_storage = 100" in tfvars


def test_customer_context_copies_dependency_filter_assets(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'dependencies = ["amber-sdk", "amber-runtime", "pytest>=9", "fastapi>=0.110"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    docker_assets = tmp_path / "docker-assets"
    docker_assets.mkdir()
    for name in [
        ".dockerignore",
        "Dockerfile.customer-app",
        "Dockerfile.customer-worker",
        "strip_prefix.py",
        "run_worker.py",
    ]:
        (docker_assets / name).write_text(name, encoding="utf-8")
    (docker_assets / "Dockerfile.customer-app").write_text(
        "COPY install_app_deps.py /workspace/install_app_deps.py\n"
        "RUN python /workspace/install_app_deps.py\n",
        encoding="utf-8",
    )
    (docker_assets / "install_app_deps.py").write_text(
        'SKIP_PACKAGES = {"amber-runtime", "amber-sdk", "pytest"}\n',
        encoding="utf-8",
    )

    def fake_asset_path(*parts: str) -> Path:
        assert parts[0] == "docker"
        return docker_assets.joinpath(*parts[1:])

    monkeypatch.setattr(deploy_mod, "asset_path", fake_asset_path)
    wheel = tmp_path / "amber_sdk-0.1.0-py3-none-any.whl"
    wheel.write_text("wheel", encoding="utf-8")

    context = deploy_mod._assemble_customer_context(
        repo_root,
        tmp_path / "build",
        "customer-app",
        wheel,
    )

    dockerfile = (context / "Dockerfile").read_text(encoding="utf-8")
    installer = (context / "install_app_deps.py").read_text(encoding="utf-8")
    copied_pyproject = (context / "app" / "pyproject.toml").read_text(encoding="utf-8")

    assert "RUN python /workspace/install_app_deps.py" in dockerfile
    assert '"amber-runtime", "amber-sdk", "pytest"' in installer
    assert "amber-runtime" in copied_pyproject
    assert (context / "wheels" / wheel.name).exists()


def test_install_app_deps_filters_workspace_and_test_dependencies(tmp_path: Path, monkeypatch) -> None:
    script_path = (
        Path(__file__).parents[1]
        / "amber_cli"
        / "asset_sources"
        / "docker"
        / "install_app_deps.py"
    )
    namespace = runpy.run_path(str(script_path), run_name="install_app_deps_test")

    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                "dependencies = [",
                '  "amber-sdk",',
                '  "amber_runtime",',
                '  "pytest>=9",',
                '  "fastapi>=0.110",',
                '  "requests[security]>=2.31",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert namespace["load_dependencies"]() == [
        "fastapi>=0.110",
        "requests[security]>=2.31",
    ]


def test_install_app_deps_installs_requirements_when_pyproject_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    script_path = (
        Path(__file__).parents[1]
        / "amber_cli"
        / "asset_sources"
        / "docker"
        / "install_app_deps.py"
    )
    namespace = runpy.run_path(str(script_path), run_name="install_app_deps_test")
    calls: list[list[str]] = []

    (tmp_path / "requirements.txt").write_text("fastapi>=0.110\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(namespace["subprocess"], "check_call", calls.append)

    namespace["main"]()

    assert calls == [
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--find-links=/wheels",
            "-r",
            "requirements.txt",
        ]
    ]


def test_install_app_deps_prefers_pyproject_over_requirements(
    tmp_path: Path,
    monkeypatch,
) -> None:
    script_path = (
        Path(__file__).parents[1]
        / "amber_cli"
        / "asset_sources"
        / "docker"
        / "install_app_deps.py"
    )
    namespace = runpy.run_path(str(script_path), run_name="install_app_deps_test")
    calls: list[list[str]] = []

    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'dependencies = ["fastapi>=0.110"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("httpx>=0.27\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(namespace["subprocess"], "check_call", calls.append)

    namespace["main"]()

    assert calls == [
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--find-links=/wheels",
            "fastapi>=0.110",
        ]
    ]
