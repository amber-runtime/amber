from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from click.testing import CliRunner

from amber_cli import cli
from amber_cli.commands import config as config_mod
from amber_cli.config_loader import load_config, validate_deploy_config


@dataclass
class FakeIdentity:
    account: str = "123456789012"
    arn: str = "arn:aws:iam::123456789012:role/AmberDeploy"
    user_id: str = "test"


class FakeSession:
    def __init__(
        self,
        *,
        ecs_services: list[dict] | None = None,
        ecs_failures: list[dict] | None = None,
    ) -> None:
        self.put_calls: list[dict] = []
        self.ecs_services = ecs_services or []
        self.ecs_failures = ecs_failures or []

    def client(self, service: str, region_name: str):
        assert service in {"ssm", "ecs"}
        assert region_name == "us-west-2"
        return self

    def put_parameter(self, **kwargs) -> None:
        self.put_calls.append(kwargs)

    def describe_services(self, **kwargs) -> dict:
        assert kwargs == {
            "cluster": "test-cluster",
            "services": [
                "test-dashboard-api",
                "test-customer-app",
                "test-customer-worker",
            ],
        }
        return {"services": self.ecs_services, "failures": self.ecs_failures}


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


def write_state(root: Path) -> None:
    tf_dir = root / ".amber" / "terraform"
    tf_dir.mkdir(parents=True)
    (tf_dir / "terraform.tfstate").write_text("{}", encoding="utf-8")


def terraform_outputs() -> dict:
    return {
        "ecs_cluster_name": {"value": "test-cluster"},
        "dashboard_api_service_name": {"value": "test-dashboard-api"},
        "customer_app_service_name": {"value": "test-customer-app"},
        "customer_worker_service_name": {"value": "test-customer-worker"},
    }


def completed_terraform_output(stdout: dict) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        ["terraform", "output", "-json"],
        0,
        stdout=json.dumps(stdout),
        stderr="",
    )


def test_load_config_defaults_customer_path_prefix_to_root(tmp_path: Path) -> None:
    write_config(tmp_path / "amber.yaml")

    cfg = load_config(str(tmp_path))

    assert cfg.path_prefix == ""
    assert validate_deploy_config(cfg) == []


def test_validate_deploy_config_allows_empty_path_prefix() -> None:
    cfg = load_config("/path/that/does/not/exist")
    cfg.name = "test-project"
    cfg.app = "my_app.main:app"
    cfg.worker = "my_app.main:agent_runtime"
    cfg.path_prefix = ""

    assert validate_deploy_config(cfg) == []


def test_validate_deploy_config_rejects_relative_path_prefix() -> None:
    cfg = load_config("/path/that/does/not/exist")
    cfg.name = "test-project"
    cfg.app = "my_app.main:app"
    cfg.worker = "my_app.main:agent_runtime"
    cfg.path_prefix = "api"

    assert validate_deploy_config(cfg) == ["path_prefix must start with /"]


def test_config_set_openai_key_first_deploy_recommends_full_deploy(monkeypatch) -> None:
    runner = CliRunner()
    fake_session = FakeSession()
    monkeypatch.setattr(config_mod, "verify_identity", lambda profile, region: FakeIdentity())
    monkeypatch.setattr(config_mod, "create_session", lambda profile, region: fake_session)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")

        result = runner.invoke(cli, ["config", "set", "openai-api-key"], input="sk-test\n")

    assert result.exit_code == 0
    assert "Set openai-api-key in SSM: /app/test-project/dev/openai-api-key" in result.output
    assert "Secret saved. Continue the first deploy with: amber deploy" in result.output
    assert "amber deploy --no-build" not in result.output
    assert fake_session.put_calls == [
        {
            "Name": "/app/test-project/dev/openai-api-key",
            "Value": "sk-test",
            "Type": "SecureString",
            "Overwrite": True,
        }
    ]


def test_config_set_openai_key_state_without_outputs_recommends_full_deploy(monkeypatch) -> None:
    runner = CliRunner()
    fake_session = FakeSession()
    monkeypatch.setattr(config_mod, "verify_identity", lambda profile, region: FakeIdentity())
    monkeypatch.setattr(config_mod, "create_session", lambda profile, region: fake_session)
    monkeypatch.setattr(config_mod, "_run", lambda cmd, cwd=None, check=True: completed_terraform_output({}))

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")
        write_state(root)

        result = runner.invoke(cli, ["config", "set", "openai-api-key"], input="sk-test\n")

    assert result.exit_code == 0
    assert "Secret saved. Continue the first deploy with: amber deploy" in result.output
    assert "amber deploy --no-build" not in result.output


def test_config_set_openai_key_inactive_ecs_services_recommends_full_deploy(monkeypatch) -> None:
    runner = CliRunner()
    fake_session = FakeSession(
        ecs_services=[
            {"serviceName": "test-dashboard-api", "status": "ACTIVE"},
            {"serviceName": "test-customer-app", "status": "INACTIVE"},
            {"serviceName": "test-customer-worker", "status": "ACTIVE"},
        ],
    )
    monkeypatch.setattr(config_mod, "verify_identity", lambda profile, region: FakeIdentity())
    monkeypatch.setattr(config_mod, "create_session", lambda profile, region: fake_session)
    monkeypatch.setattr(
        config_mod,
        "_run",
        lambda cmd, cwd=None, check=True: completed_terraform_output(terraform_outputs()),
    )

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")
        write_state(root)

        result = runner.invoke(cli, ["config", "set", "openai-api-key"], input="sk-test\n")

    assert result.exit_code == 0
    assert "Secret saved. Continue the first deploy with: amber deploy" in result.output
    assert "amber deploy --no-build" not in result.output


def test_config_set_openai_key_active_ecs_services_recommends_no_build(monkeypatch) -> None:
    runner = CliRunner()
    fake_session = FakeSession(
        ecs_services=[
            {"serviceName": "test-dashboard-api", "status": "ACTIVE"},
            {"serviceName": "test-customer-app", "status": "ACTIVE"},
            {"serviceName": "test-customer-worker", "status": "ACTIVE"},
        ],
    )
    monkeypatch.setattr(config_mod, "verify_identity", lambda profile, region: FakeIdentity())
    monkeypatch.setattr(config_mod, "create_session", lambda profile, region: fake_session)
    monkeypatch.setattr(
        config_mod,
        "_run",
        lambda cmd, cwd=None, check=True: completed_terraform_output(terraform_outputs()),
    )

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")
        write_state(root)

        result = runner.invoke(cli, ["config", "set", "openai-api-key"], input="sk-test\n")

    assert result.exit_code == 0
    assert "Secret saved. Restart services to pick up the change: amber deploy --no-build" in result.output


def test_config_set_unknown_key_fails_before_auth(monkeypatch) -> None:
    runner = CliRunner()

    def fail_verify(profile: str, region: str):
        raise AssertionError("auth should not run for unknown keys")

    monkeypatch.setattr(config_mod, "verify_identity", fail_verify)

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")

        result = runner.invoke(cli, ["config", "set", "missing-key"])

    assert result.exit_code == 1
    assert "Unknown key: missing-key" in result.output
    assert "Known keys: openai-api-key, db" in result.output


def test_config_set_readonly_key_fails_before_auth(monkeypatch) -> None:
    runner = CliRunner()

    def fail_verify(profile: str, region: str):
        raise AssertionError("auth should not run for read-only keys")

    monkeypatch.setattr(config_mod, "verify_identity", fail_verify)

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")

        result = runner.invoke(cli, ["config", "set", "db"])

    assert result.exit_code == 1
    assert "db is read-only (managed by AWS)." in result.output
