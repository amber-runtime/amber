"""Static discovery for customer Amber app entrypoints."""

from __future__ import annotations

import ast
import json
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


@dataclass(frozen=True)
class FrontendCandidate:
    """A customer React SPA discovered from a package.json."""

    path: Path  # directory containing package.json
    framework: str  # "react"
    build_command: str  # e.g. "npm run build"
    output_dir: str  # build output dir, e.g. "dist" (vite) or "build" (CRA)

    def rel_path(self, root: Path) -> str:
        """Path relative to the project root, for recording in amber.yaml."""
        rel = self.path.relative_to(root)
        return rel.as_posix() if rel.parts else "."


def discover_frontend_candidates(root: Path) -> list[FrontendCandidate]:
    """Find React SPA directories (package.json declaring a react dependency)."""
    candidates: list[FrontendCandidate] = []
    for path in _iter_package_jsons(root):
        found = _inspect_package_json(path)
        if found is None:
            continue
        build_command, output_dir = found
        candidates.append(
            FrontendCandidate(
                path=path.parent,
                framework="react",
                build_command=build_command,
                output_dir=output_dir,
            )
        )
    return sorted(candidates, key=lambda c: (len(c.path.parts), str(c.path)))


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


def _iter_package_jsons(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("package.json"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        paths.append(path)
    return sorted(paths)


def _inspect_package_json(path: Path) -> tuple[str, str] | None:
    """Return (build_command, output_dir) when package.json declares React."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    deps = {}
    for key in ("dependencies", "devDependencies"):
        value = data.get(key)
        if isinstance(value, dict):
            deps.update(value)
    if "react" not in deps:
        return None

    # react-scripts (Create React App) emits to build/; Vite and most others to dist/.
    output_dir = "build" if "react-scripts" in deps else "dist"
    return "npm run build", output_dir
