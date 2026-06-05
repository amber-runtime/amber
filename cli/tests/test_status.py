from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from amber_cli import cli
from amber_cli.commands import status as status_mod


class FakeStatusSession:
    def client(self, service: str, region_name: str):
        assert region_name == "us-west-2"
        if service == "ecs":
            return FakeECS()
        if service == "ssm":
            return FakeSSM()
        if service == "cognito-idp":
            return FakeCognito()
        raise AssertionError(service)


class FakeECS:
    def describe_services(self, *, cluster: str, services: list[str]):
        assert cluster == "cluster"
        assert len(services) == 1
        return {
            "services": [
                {
                    "runningCount": 1,
                    "desiredCount": 1,
                    "pendingCount": 0,
                    "deployments": [{"status": "PRIMARY"}],
                }
            ]
        }


class FakeSSM:
    class exceptions:
        class ParameterNotFound(Exception):
            pass

    def get_parameter(self, *, Name: str, WithDecryption: bool):
        assert Name == "/app/test-project/dev/openai-api-key"
        assert WithDecryption is True
        return {"Parameter": {"Value": "sk-test"}}


class FakeCognito:
    def list_users(self, **kwargs):
        assert kwargs == {"UserPoolId": "us-west-2_pool", "Limit": 1}
        return {"Users": []}


def test_status_guides_admin_creation_when_no_admin_user(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run(cmd, cwd=None, check=True):
        if cmd == ["terraform", "output", "-json"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "cloudfront_domain": {"value": "d111111abcdef8.cloudfront.net"},
                        "ecs_cluster_name": {"value": "cluster"},
                        "dashboard_api_service_name": {"value": "dashboard-api"},
                        "customer_app_service_name": {"value": "customer-app"},
                        "customer_worker_service_name": {"value": "customer-worker"},
                        "cognito_user_pool_id": {"value": "us-west-2_pool"},
                        "cognito_region": {"value": "us-west-2"},
                    }
                ),
                stderr="",
            )
        if cmd[0] == "curl":
            return subprocess.CompletedProcess(cmd, 0, stdout="200", stderr="")
        raise AssertionError(cmd)

    monkeypatch.setattr(status_mod, "_run", fake_run)
    monkeypatch.setattr(
        status_mod,
        "require_identity",
        lambda profile, region: (FakeStatusSession(), object()),
    )

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
        Path(tmp, ".amber", "terraform").mkdir(parents=True)

        result = runner.invoke(cli, ["status"])

    assert result.exit_code == 0
    assert "Admin Access" in result.output
    assert "Admin access: no dashboard admin user exists yet." in result.output
    assert "amber admin create-user --email <you@example.com>" in result.output
