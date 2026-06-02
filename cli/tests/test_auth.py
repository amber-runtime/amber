from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from click.testing import CliRunner

from amber_cli import cli
from amber_cli.commands import auth as auth_mod


@dataclass
class FakeIdentity:
    account: str = "123456789012"
    arn: str = "arn:aws:iam::123456789012:role/AmberDeploy"
    user_id: str = "test"


def write_config(path: Path, *, include_profile: bool = False, environment: str = "dev") -> None:
    lines = [
        "name: test-project",
        "app: my_app.main:app",
        "worker: my_app.main:agent_runtime",
        "region: us-west-2",
        f"environment: {environment}",
    ]
    if include_profile:
        lines.append("profile: amber-dev")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_auth_setup_sso_configures_logs_in_and_saves_profile(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[tuple[list[str], bool]] = []

    def fake_run_aws(args: list[str], *, interactive: bool = False, input_text: str | None = None) -> None:
        calls.append((args, interactive))

    def fake_verify_identity(profile: str, region: str) -> FakeIdentity:
        assert profile == "amber-dev"
        assert region == "us-west-2"
        return FakeIdentity()

    monkeypatch.setattr(auth_mod, "_run_aws", fake_run_aws)
    monkeypatch.setattr(auth_mod, "verify_identity", fake_verify_identity)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        config_path = root / "amber.yaml"
        write_config(config_path)

        result = runner.invoke(
            cli,
            ["auth", "setup"],
            input="amber-dev\nus-west-2\n",
        )

        config_text = config_path.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Configuring AWS SSO / IAM Identity Center" in result.output
    assert "How do you access AWS?" not in result.output
    assert "CloudFormation" not in result.output
    assert "already have AWS credentials" not in result.output
    assert calls == [
        (["configure", "sso", "--profile", "amber-dev"], True),
    ]
    assert "profile: amber-dev" in config_text
    assert "region: us-west-2" in config_text


def test_auth_setup_defaults_prod_profile_from_environment(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[tuple[list[str], bool]] = []

    def fake_run_aws(args: list[str], *, interactive: bool = False, input_text: str | None = None) -> None:
        calls.append((args, interactive))

    def fake_verify_identity(profile: str, region: str) -> FakeIdentity:
        assert profile == "amber-prod"
        assert region == "us-west-2"
        return FakeIdentity()

    monkeypatch.setattr(auth_mod, "_run_aws", fake_run_aws)
    monkeypatch.setattr(auth_mod, "verify_identity", fake_verify_identity)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        config_path = root / "amber.yaml"
        write_config(config_path, environment="prod")

        result = runner.invoke(cli, ["auth", "setup"], input="\nus-west-2\n")
        config_text = config_path.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert calls == [
        (["configure", "sso", "--profile", "amber-prod"], True),
    ]
    assert "profile: amber-prod" in config_text


def test_auth_login_refreshes_saved_sso_profile(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[tuple[list[str], bool]] = []

    def fake_run_aws(args: list[str], *, interactive: bool = False, input_text: str | None = None) -> None:
        calls.append((args, interactive))

    def fake_verify_identity(profile: str, region: str) -> FakeIdentity:
        assert profile == "amber-dev"
        assert region == "us-west-2"
        return FakeIdentity()

    monkeypatch.setattr(auth_mod, "_run_aws", fake_run_aws)
    monkeypatch.setattr(auth_mod, "verify_identity", fake_verify_identity)

    with runner.isolated_filesystem() as tmp:
        root = Path(tmp)
        config_path = root / "amber.yaml"
        write_config(config_path, include_profile=True)

        result = runner.invoke(cli, ["auth", "login"])

        config_text = config_path.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert calls == [
        (["sso", "login", "--profile", "amber-dev"], True),
    ]
    assert "profile: amber-dev" in config_text
    assert "region: us-west-2" in config_text


def test_auth_login_without_profile_points_to_setup_sso_first() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as tmp:
        write_config(Path(tmp) / "amber.yaml")

        result = runner.invoke(cli, ["auth", "login"])

    assert result.exit_code == 1
    assert "No AWS profile is configured in amber.yaml." in result.output
    assert "Run `amber auth setup` first." in result.output
