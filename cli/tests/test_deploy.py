from __future__ import annotations

import subprocess
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
