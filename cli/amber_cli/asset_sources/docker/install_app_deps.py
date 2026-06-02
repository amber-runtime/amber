"""Install customer app dependencies inside Amber runtime images."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import tomllib


SKIP_PACKAGES = {"amber-runtime", "amber-sdk", "pytest"}


def dependency_name(requirement: str) -> str:
    name = requirement.split(";", 1)[0].strip()
    name = re.split(r"\s*(?:\[|<|>|=|!|~)", name, maxsplit=1)[0]
    return name.replace("_", "-").lower()


def load_dependencies() -> list[str]:
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        return []
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    return [dep for dep in deps if dependency_name(dep) not in SKIP_PACKAGES]


def main() -> None:
    deps = load_dependencies()
    if not deps:
        return
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--find-links=/wheels",
            *deps,
        ]
    )


if __name__ == "__main__":
    main()
