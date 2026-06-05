from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from botocore.exceptions import ClientError
from click.testing import CliRunner

from amber_cli import cli
from amber_cli.commands import destroy as destroy_mod


@dataclass
class FakeIdentity:
    account: str = "123456789012"
    arn: str = "arn:aws:iam::123456789012:user/test"
    user_id: str = "test"


class FakeWaiter:
    def __init__(self, calls: list[tuple[str, dict]]) -> None:
        self.calls = calls

    def wait(self, **kwargs) -> None:
        self.calls.append(("wait", kwargs))


class FakeRDSClient:
    def __init__(
        self,
        calls: list[tuple[str, dict]],
        *,
        not_found: bool = False,
    ) -> None:
        self.calls = calls
        self.not_found = not_found

    def modify_db_instance(self, **kwargs) -> None:
        self.calls.append(("modify_db_instance", kwargs))
        if self.not_found:
            raise ClientError(
                {"Error": {"Code": "DBInstanceNotFound"}},
                "ModifyDBInstance",
            )

    def get_waiter(self, name: str) -> FakeWaiter:
        self.calls.append(("get_waiter", {"name": name}))
        return FakeWaiter(self.calls)


class FakeSession:
    def __init__(
        self,
        calls: list[tuple[str, dict]] | None = None,
        *,
        db_not_found: bool = False,
    ) -> None:
        self.calls = calls if calls is not None else []
        self.db_not_found = db_not_found

    def client(self, service_name: str, region_name: str):
        self.calls.append(
            ("client", {"service_name": service_name, "region_name": region_name})
        )
        assert service_name == "rds"
        return FakeRDSClient(self.calls, not_found=self.db_not_found)


def write_config(path: Path, *, environment: str = "dev") -> None:
    path.write_text(
        "\n".join(
            [
                "name: test-project",
                "app: my_app.main:app",
                "worker: my_app.main:agent_runtime",
                "region: us-west-2",
                f"environment: {environment}",
                "profile: amber-dev",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_state(root: Path) -> Path:
    tf_dir = root / ".amber" / "terraform"
    tf_dir.mkdir(parents=True)
    (tf_dir / "terraform.tfstate").write_text("{}", encoding="utf-8")
    return tf_dir


def test_destroy_fails_without_amber_yaml() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["destroy"])

    assert result.exit_code == 1
    assert "No amber.yaml found. Run 'amber init' first." in result.output


def test_destroy_fails_without_deploy_state() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")

        result = runner.invoke(cli, ["destroy"])

    assert result.exit_code == 1
    assert "No Amber deploy state found. Has `amber deploy` run?" in result.output


def test_destroy_runs_terraform_from_generated_workspace(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[tuple[list[str], Path]] = []

    def fake_require_identity(profile: str, region: str):
        assert profile == "amber-dev"
        assert region == "us-west-2"
        return object(), FakeIdentity()

    def fake_run(cmd, cwd=None, check=False, capture_output=True, text=True):
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(destroy_mod, "require_identity", fake_require_identity)
    monkeypatch.setattr(destroy_mod.subprocess, "run", fake_run)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")
        tf_dir = write_state(root)

        result = runner.invoke(cli, ["destroy", "--yes"])

    assert result.exit_code == 0
    assert calls == [
        (["terraform", "init"], tf_dir.resolve()),
        (["terraform", "destroy", "-auto-approve"], tf_dir.resolve()),
    ]
    assert "Cloud resources destroyed." in result.output
    assert "Local config kept: amber.yaml" in result.output
    assert "rm amber.yaml && rm -rf .amber" in result.output


def test_destroy_prompts_before_running_terraform(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[list[str]] = []

    def fake_require_identity(profile: str, region: str):
        return object(), FakeIdentity()

    def fake_run(cmd, cwd=None, check=False, capture_output=True, text=True):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(destroy_mod, "require_identity", fake_require_identity)
    monkeypatch.setattr(destroy_mod.subprocess, "run", fake_run)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")
        write_state(root)

        result = runner.invoke(cli, ["destroy"], input="n\n")

    assert result.exit_code == 1
    assert "Destroy these AWS resources?" in result.output
    assert "Destroy cancelled." in result.output
    assert calls == []


def test_destroy_env_override_changes_display(monkeypatch) -> None:
    runner = CliRunner()

    def fake_require_identity(profile: str, region: str):
        return object(), FakeIdentity()

    def fake_run(cmd, cwd=None, check=False, capture_output=True, text=True):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(destroy_mod, "require_identity", fake_require_identity)
    monkeypatch.setattr(destroy_mod.subprocess, "run", fake_run)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml")
        write_state(root)

        result = runner.invoke(cli, ["destroy", "--env", "staging", "--yes"])

    assert result.exit_code == 0
    assert "Amber destroy - test-project (staging)" in result.output


def test_destroy_refuses_prod_without_allow_prod_data_loss(monkeypatch) -> None:
    runner = CliRunner()

    def fake_require_identity(profile: str, region: str):
        return object(), FakeIdentity()

    def fake_run(cmd, cwd=None, check=False, capture_output=True, text=True):
        raise AssertionError("terraform should not run")

    monkeypatch.setattr(destroy_mod, "require_identity", fake_require_identity)
    monkeypatch.setattr(destroy_mod.subprocess, "run", fake_run)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml", environment="prod")
        write_state(root)

        result = runner.invoke(cli, ["destroy", "--yes"])

    assert result.exit_code == 1
    assert "Refusing to destroy prod without --allow-prod-data-loss." in result.output


def test_destroy_prod_with_allow_prod_data_loss_requires_typed_confirmation(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[tuple[list[str], Path]] = []
    rds_calls: list[tuple[str, dict]] = []

    def fake_require_identity(profile: str, region: str):
        return FakeSession(rds_calls), FakeIdentity()

    def fake_run(cmd, cwd=None, check=False, capture_output=True, text=True):
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(destroy_mod, "require_identity", fake_require_identity)
    monkeypatch.setattr(destroy_mod.subprocess, "run", fake_run)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml", environment="prod")
        tf_dir = write_state(root)

        result = runner.invoke(
            cli,
            ["destroy", "--allow-prod-data-loss"],
            input="test-project-prod\n",
        )

    assert result.exit_code == 0
    assert "permanently delete the prod database without a final snapshot" in result.output
    assert "automated backups" in result.output
    assert "Type test-project-prod to destroy this prod stack" in result.output
    assert rds_calls == [
        (
            "client",
            {"service_name": "rds", "region_name": "us-west-2"},
        ),
        (
            "modify_db_instance",
            {
                "DBInstanceIdentifier": "test-project-prod",
                "DeletionProtection": False,
                "ApplyImmediately": True,
            },
        ),
        ("get_waiter", {"name": "db_instance_available"}),
        ("wait", {"DBInstanceIdentifier": "test-project-prod"}),
    ]
    assert calls == [
        (["terraform", "init"], tf_dir.resolve()),
        (
            [
                "terraform",
                "destroy",
                "-auto-approve",
                "-var=db_deletion_protection=false",
                "-var=frontend_bucket_force_destroy=true",
                "-var=secrets_force_destroy=true",
                "-var=db_skip_final_snapshot=true",
                "-var=db_delete_automated_backups=true",
            ],
            tf_dir.resolve(),
        ),
    ]


def test_destroy_prod_yes_still_requires_typed_confirmation(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[list[str]] = []

    def fake_require_identity(profile: str, region: str):
        return FakeSession(), FakeIdentity()

    def fake_run(cmd, cwd=None, check=False, capture_output=True, text=True):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(destroy_mod, "require_identity", fake_require_identity)
    monkeypatch.setattr(destroy_mod.subprocess, "run", fake_run)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml", environment="prod")
        write_state(root)

        result = runner.invoke(
            cli,
            ["destroy", "--allow-prod-data-loss", "--yes"],
            input="\n",
        )

    assert result.exit_code == 1
    assert "Type test-project-prod to destroy this prod stack" in result.output
    assert "Destroy cancelled." in result.output
    assert calls == []


def test_destroy_prod_continues_when_rds_is_already_gone(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[tuple[list[str], Path]] = []
    rds_calls: list[tuple[str, dict]] = []

    def fake_require_identity(profile: str, region: str):
        return FakeSession(rds_calls, db_not_found=True), FakeIdentity()

    def fake_run(cmd, cwd=None, check=False, capture_output=True, text=True):
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(destroy_mod, "require_identity", fake_require_identity)
    monkeypatch.setattr(destroy_mod.subprocess, "run", fake_run)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        write_config(root / "amber.yaml", environment="prod")
        tf_dir = write_state(root)

        result = runner.invoke(
            cli,
            ["destroy", "--allow-prod-data-loss"],
            input="test-project-prod\n",
        )

    assert result.exit_code == 0
    assert "RDS instance test-project-prod is already gone; continuing." in result.output
    assert rds_calls == [
        (
            "client",
            {"service_name": "rds", "region_name": "us-west-2"},
        ),
        (
            "modify_db_instance",
            {
                "DBInstanceIdentifier": "test-project-prod",
                "DeletionProtection": False,
                "ApplyImmediately": True,
            },
        ),
    ]
    assert calls == [
        (["terraform", "init"], tf_dir.resolve()),
        (
            [
                "terraform",
                "destroy",
                "-auto-approve",
                "-var=db_deletion_protection=false",
                "-var=frontend_bucket_force_destroy=true",
                "-var=secrets_force_destroy=true",
                "-var=db_skip_final_snapshot=true",
                "-var=db_delete_automated_backups=true",
            ],
            tf_dir.resolve(),
        ),
    ]
