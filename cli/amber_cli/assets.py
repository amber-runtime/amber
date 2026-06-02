"""Runtime access to packaged Amber CLI assets."""

from __future__ import annotations

from importlib import resources
from pathlib import Path


def asset_path(*parts: str) -> Path:
    """Return a filesystem path to a packaged asset."""
    return Path(str(resources.files("amber_cli").joinpath("assets", *parts)))
