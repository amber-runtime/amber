"""Static discovery for customer Amber app entrypoints."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {
    ".amber",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


@dataclass(frozen=True)
class AppCandidate:
    """A module containing both a customer ASGI app and AgentRuntime target."""

    module: str
    app_name: str
    worker_name: str
    path: Path

    @property
    def app_target(self) -> str:
        return f"{self.module}:{self.app_name}"

    @property
    def worker_target(self) -> str:
        return f"{self.module}:{self.worker_name}"


def discover_app_candidates(root: Path) -> list[AppCandidate]:
    """Find Python modules that define both FastAPI app and AgentRuntime objects."""
    candidates: list[AppCandidate] = []
    for path in _iter_python_files(root):
        module = _module_name(root, path)
        if not module:
            continue
        found = _inspect_python_file(path)
        if found is None:
            continue
        app_name, worker_name = found
        candidates.append(
            AppCandidate(
                module=module,
                app_name=app_name,
                worker_name=worker_name,
                path=path,
            )
        )
    return sorted(candidates, key=lambda c: (len(c.module.split(".")), c.module))


def _iter_python_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        paths.append(path)
    return sorted(paths)


def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if not parts:
        return ""
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return ""
    return ".".join(parts)


def _inspect_python_file(path: Path) -> tuple[str, str] | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None

    app_names: list[str] = []
    worker_names: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not targets:
            continue
        if _is_call_named(node.value, {"FastAPI", "Starlette"}):
            app_names.extend(targets)
        if _is_call_named(node.value, {"AgentRuntime"}):
            worker_names.extend(targets)

    if not app_names or not worker_names:
        return None
    return app_names[0], worker_names[0]


def _is_call_named(node: ast.AST, names: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in names
    if isinstance(func, ast.Attribute):
        return func.attr in names
    return False
