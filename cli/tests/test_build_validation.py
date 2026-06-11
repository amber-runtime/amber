from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


BUILD_VALIDATION_PATH = Path(__file__).parents[1] / "build_validation.py"
SPEC = importlib.util.spec_from_file_location("build_validation", BUILD_VALIDATION_PATH)
assert SPEC is not None
build_validation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_validation)
validate_packaged_sdk_wheel = build_validation.validate_packaged_sdk_wheel


def write_runtime_package(root: Path, dependency: str = "amber-sdk>=0.1.2") -> Path:
    (root / "amber_cli" / "assets" / "sdk").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "amber-runtime"',
                'version = "0.1.2"',
                "dependencies = [",
                f'    "{dependency}",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root / "amber_cli" / "assets" / "sdk"


def test_validate_packaged_sdk_wheel_accepts_matching_single_wheel(tmp_path: Path) -> None:
    sdk_assets = write_runtime_package(tmp_path)
    (sdk_assets / "amber_sdk-0.1.2-py3-none-any.whl").write_text("", encoding="utf-8")

    validate_packaged_sdk_wheel(tmp_path)


def test_validate_packaged_sdk_wheel_rejects_multiple_wheels(tmp_path: Path) -> None:
    sdk_assets = write_runtime_package(tmp_path)
    (sdk_assets / "amber_sdk-0.1.0-py3-none-any.whl").write_text("", encoding="utf-8")
    (sdk_assets / "amber_sdk-0.1.2-py3-none-any.whl").write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Expected exactly one bundled SDK wheel"):
        validate_packaged_sdk_wheel(tmp_path)


def test_validate_packaged_sdk_wheel_rejects_wrong_version(tmp_path: Path) -> None:
    sdk_assets = write_runtime_package(tmp_path)
    (sdk_assets / "amber_sdk-0.1.0-py3-none-any.whl").write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError, match="does not match amber-runtime dependency"):
        validate_packaged_sdk_wheel(tmp_path)
