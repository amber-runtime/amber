from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from click.testing import CliRunner

from amber_cli import cli
from amber_cli.commands import destroy as destroy_mod


@dataclass
class FakeIdentity:
    account: str = "123456789012"
    arn: str = "arn:aws:iam::123456789012:user/test"
    user_id: str = "test"


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
