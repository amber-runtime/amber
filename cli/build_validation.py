"""Build-time validation for Amber runtime package assets."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def _runtime_sdk_version(root: Path) -> str:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"].get("dependencies", [])
    for dependency in dependencies:
        match = re.match(r"amber-sdk\s*>=\s*([^,\s;]+)", dependency)
        if match:
            return match.group(1)
    raise RuntimeError("amber-runtime must declare an amber-sdk>=... dependency")


def validate_packaged_sdk_wheel(root: Path) -> None:
    expected_version = _runtime_sdk_version(root)
    sdk_assets = root / "amber_cli" / "assets" / "sdk"
    wheels = sorted(sdk_assets.glob("*.whl"))
    wheel_names = ", ".join(wheel.name for wheel in wheels) or "none"

    if len(wheels) != 1:
        raise RuntimeError(
            "Expected exactly one bundled SDK wheel in "
            f"{sdk_assets}, found {len(wheels)}: {wheel_names}. "
            "Run `make cli-assets` from a clean generated asset state."
        )

    expected_prefix = f"amber_sdk-{expected_version}-"
    if not wheels[0].name.startswith(expected_prefix):
        raise RuntimeError(
            "Bundled SDK wheel version does not match amber-runtime dependency "
            f"amber-sdk>={expected_version}: found {wheels[0].name}."
        )
