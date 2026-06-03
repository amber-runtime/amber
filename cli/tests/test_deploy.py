from __future__ import annotations

import subprocess
import runpy
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from click.testing import CliRunner

from amber_cli import cli
from amber_cli.commands import deploy as deploy_mod
from amber_cli.routes import public_urls


@dataclass
class FakeConfig:
    name: str = "test-project"
    project_prefix: str = ""
    environment: str = "dev"
    region: str = "us-west-2"
    app: str = "my_app.main:app"
    worker: str = "my_app.main:agent_runtime"
    path_prefix: str = ""
    profile: str = ""

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


class FakeS3:
    def __init__(self) -> None:
        self.uploads: list[str] = []
        self.deleted: list[str] = []

    def upload_file(self, Filename: str, Bucket: str, Key: str, ExtraArgs: dict | None = None):
        assert Bucket == "frontend-bucket"
        self.uploads.append(Key)

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket: str):
        assert Bucket == "frontend-bucket"
        return [{"Contents": [{"Key": "admin/stale.js"}, {"Key": "elsewhere.txt"}]}]

    def delete_objects(self, Bucket: str, Delete: dict):
        assert Bucket == "frontend-bucket"
        self.deleted.extend(obj["Key"] for obj in Delete["Objects"])


class FakeCloudFront:
    def __init__(self) -> None:
        self.invalidations: list[dict] = []

    def create_invalidation(self, **kwargs):
        self.invalidations.append(kwargs)


class FakeFrontendSession:
    def __init__(self) -> None:
        self.s3 = FakeS3()
        self.cloudfront = FakeCloudFront()

    def client(self, service: str, region_name: str):
        assert region_name == "us-west-2"
        if service == "s3":
            return self.s3
        if service == "cloudfront":
            return self.cloudfront
        raise AssertionError(service)


class FakeDeploySession:
    def client(self, service: str, region_name: str):
        assert region_name == "us-west-2"
        if service == "cognito-idp":
            return self
        raise AssertionError(service)

    def list_users(self, **kwargs):
        assert kwargs == {"UserPoolId": "us-west-2_pool", "Limit": 1}
        return {"Users": []}


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


def test_public_urls_use_customer_root_and_admin_namespace() -> None:
    assert public_urls("d111111abcdef8.cloudfront.net") == {
        "customer_app": "https://d111111abcdef8.cloudfront.net/",
        "amber_admin": "https://d111111abcdef8.cloudfront.net/admin/",
        "admin_api_health": "https://d111111abcdef8.cloudfront.net/admin/api/health",
    }


def test_deploy_summary_guides_admin_creation_when_no_admin_user(monkeypatch) -> None:
    runner = CliRunner()
    session = FakeDeploySession()

    monkeypatch.setattr(deploy_mod, "_image_tag", lambda repo_root: "tag")
    monkeypatch.setattr(deploy_mod, "_ensure_gitignore", lambda repo_root: None)
    monkeypatch.setattr(deploy_mod, "_sync_terraform", lambda tf_dir: None)
    monkeypatch.setattr(deploy_mod, "_write_tfvars", lambda tf_dir, cfg, image_tag: None)
    monkeypatch.setattr(
        deploy_mod,
        "run_deploy_preflight",
        lambda *args, **kwargs: SimpleNamespace(
            ok=True,
            errors=[],
            session=session,
            identity=SimpleNamespace(account="123456789012"),
        ),
    )
    monkeypatch.setattr(
        deploy_mod,
        "_terraform_output",
        lambda tf_dir: {
            "ecs_cluster_name": "cluster",
            "dashboard_api_service_name": "dashboard-api",
            "customer_app_service_name": "customer-app",
            "customer_worker_service_name": "customer-worker",
            "cloudfront_domain": "d111111abcdef8.cloudfront.net",
            "cognito_user_pool_id": "us-west-2_pool",
            "cognito_region": "us-west-2",
        },
    )
    monkeypatch.setattr(deploy_mod, "_restart_ecs", lambda *args, **kwargs: None)

    with runner.isolated_filesystem() as tmp:
        Path(tmp, "amber.yaml").write_text(
            "\n".join(
                [
                    "name: test-project",
                    "app: my_app.main:app",
                    "worker: my_app.main:agent_runtime",
                    "region: us-west-2",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = runner.invoke(cli, ["deploy", "--no-build", "--no-infra", "--no-frontend"])

    assert result.exit_code == 0
    assert "Deploy complete!" in result.output
    assert "Admin access: no dashboard admin user exists yet." in result.output
    assert "amber admin create-user --email <you@example.com>" in result.output
    assert "Cognito will email the temporary password." in result.output


def test_sync_frontend_uploads_admin_prefixed_assets(monkeypatch, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")

    def fake_asset_path(*parts: str) -> Path:
        assert parts == ("frontend", "dist")
        return dist

    monkeypatch.setattr(deploy_mod, "asset_path", fake_asset_path)
    monkeypatch.setattr(deploy_mod.time, "time", lambda: 1_717_171_719)
    session = FakeFrontendSession()

    deploy_mod._sync_frontend(session, "frontend-bucket", "DIST123", "us-west-2")

    assert session.s3.uploads == ["admin/index.html", "admin/assets/app.js"]
    assert session.s3.deleted == ["admin/stale.js"]
    assert session.cloudfront.invalidations[0]["DistributionId"] == "DIST123"


def test_packaged_terraform_routes_admin_api_and_customer_root() -> None:
    terraform_dir = Path(__file__).parents[1] / "amber_cli" / "assets" / "terraform"
    cloudfront = (terraform_dir / "cloudfront.tf").read_text(encoding="utf-8")
    alb = (terraform_dir / "alb.tf").read_text(encoding="utf-8")

    assert 'path_pattern             = "/admin/api/*"' in cloudfront
    assert 'path_pattern           = "/admin/*"' in cloudfront
    assert 'target_origin_id         = "alb"' in cloudfront
    assert 'target_origin_id       = "s3"' in cloudfront
    assert 'values = ["/admin/api/*", "/admin/api"]' in alb
    assert 'values = ["/*"]' in alb
    assert 'values = ["/dashboard/*", "/dashboard"]' not in alb


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
    assert 'path_prefix = ""' in tfvars


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
