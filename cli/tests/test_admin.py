from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from amber_cli import cli
from amber_cli.commands import admin as admin_mod


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


class FakeSession:
    def __init__(self, calls: list[dict]):
        self.calls = calls

    def client(self, service: str, region_name: str | None = None):
        assert service == "cognito-idp"
        assert region_name == "us-west-2"
        return self

    def admin_create_user(self, **kwargs):
        self.calls.append(kwargs)
        return {}


def test_admin_create_user_reads_terraform_outputs_and_creates_cognito_user(monkeypatch) -> None:
    runner = CliRunner()
    cognito_calls: list[dict] = []
    terraform_cwds: list[Path | None] = []

    def fake_run(cmd, cwd=None, check=True):
        terraform_cwds.append(cwd)
        assert cmd == ["terraform", "output", "-json"]
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "cognito_user_pool_id": {"value": "us-west-2_pool"},
                    "cognito_region": {"value": "us-west-2"},
                }
            ),
            stderr="",
        )

    def fake_require_identity(profile: str, region: str):
        assert profile == "amber-dev"
        assert region == "us-west-2"
        return FakeSession(cognito_calls), object()

    monkeypatch.setattr(admin_mod, "_run", fake_run)
    monkeypatch.setattr(admin_mod, "require_identity", fake_require_identity)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")
        (root / ".amber" / "terraform").mkdir(parents=True)

        result = runner.invoke(cli, ["admin", "create-user", "--email", "dev@example.com"])

    assert result.exit_code == 0
    assert [p.resolve() for p in terraform_cwds if p is not None] == [
        (root / ".amber" / "terraform").resolve()
    ]
    assert cognito_calls == [
        {
            "UserPoolId": "us-west-2_pool",
            "Username": "dev@example.com",
            "UserAttributes": [
                {"Name": "email", "Value": "dev@example.com"},
                {"Name": "email_verified", "Value": "true"},
            ],
            "DesiredDeliveryMediums": ["EMAIL"],
        }
    ]
    assert "Created dashboard admin user" in result.output
    assert "Cognito is sending a temporary password email." in result.output
    assert "Use that email and temporary password at /admin/." in result.output
    assert "First login may require choosing a new password." in result.output


def test_admin_create_user_can_resend_cognito_invite(monkeypatch) -> None:
    runner = CliRunner()
    cognito_calls: list[dict] = []

    def fake_run(cmd, cwd=None, check=True):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "cognito_user_pool_id": {"value": "us-west-2_pool"},
                    "cognito_region": {"value": "us-west-2"},
                }
            ),
            stderr="",
        )

    def fake_require_identity(profile: str, region: str):
        return FakeSession(cognito_calls), object()

    monkeypatch.setattr(admin_mod, "_run", fake_run)
    monkeypatch.setattr(admin_mod, "require_identity", fake_require_identity)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")
        (root / ".amber" / "terraform").mkdir(parents=True)

        result = runner.invoke(
            cli,
            ["admin", "create-user", "--resend", "--email", "dev@example.com"],
        )

    assert result.exit_code == 0
    assert cognito_calls[0]["MessageAction"] == "RESEND"
    assert "Resent dashboard admin invite" in result.output
    assert "Cognito is sending a temporary password email." in result.output


def test_cognito_terraform_assets_are_packaged() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for base in [
        repo_root / "infra" / "terraform",
        repo_root / "cli" / "amber_cli" / "assets" / "terraform",
    ]:
        cognito = (base / "cognito.tf").read_text(encoding="utf-8")
        outputs = (base / "outputs.tf").read_text(encoding="utf-8")
        ecs = (base / "ecs.tf").read_text(encoding="utf-8")

        assert 'resource "aws_cognito_user_pool" "dashboard_admin"' in cognito
        assert 'resource "aws_cognito_user_pool_client" "dashboard_spa"' in cognito
        assert 'output "cognito_user_pool_id"' in outputs
        assert '"COGNITO_ISSUER"' in ecs
        assert '"COGNITO_CLIENT_ID"' in ecs
