"""Load and parse amber.yaml configuration."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class FrontendConfig:
    """Customer React SPA delivery settings from amber.yaml's `frontend:` block."""

    type: str = ""  # "react" (empty = server-rendered app owns /)
    path: str = ""  # frontend dir relative to repo root
    build: str = "npm run build"
    output: str = "dist"  # build output dir relative to `path`


@dataclass
class AmberConfig:
    """Represents an amber.yaml configuration."""

    name: str = ""
    agents: list[str] = field(default_factory=list)
    app: str = ""
    worker: str = ""
    path_prefix: str = ""
    profile: str = ""
    region: str = "us-east-1"
    environment: str = "dev"
    dashboard: bool = True
    project_prefix: str = ""  # terraform project name, defaults to config name
    frontend: FrontendConfig | None = None

    @property
    def prefix(self) -> str:
        """Resource naming prefix (e.g. amber-dev)."""
        p = self.project_prefix or self.name
        return f"{p}-{self.environment}"

    @property
    def ssm_base(self) -> str:
        """SSM parameter path prefix."""
        p = self.project_prefix or self.name
        return f"/app/{p}/{self.environment}"

    @property
    def secrets_prefix(self) -> str:
        """Secrets Manager secret name prefix."""
        return self.prefix


# Mapping of friendly key names to their AWS locations
SECRET_REGISTRY: dict[str, dict] = {
    "openai-api-key": {
        "type": "ssm",
        "path": "{ssm_base}/openai-api-key",
        "description": "OpenAI API key for LLM calls",
        "env_var": "OPENAI_API_KEY",
    },
    "db": {
        "type": "secretsmanager",
        "path": "{secrets_prefix}/db",
        "description": "Database connection URL (managed by AWS)",
        "env_var": "DBOS_SYSTEM_DATABASE_URL",
        "readonly": True,
    },
}


def find_config_path(start: str | None = None) -> str | None:
    """Walk up from start dir looking for amber.yaml."""
    current = Path(start or os.getcwd())
    while True:
        candidate = current / "amber.yaml"
        if candidate.exists():
            return str(candidate)
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_config(start: str | None = None) -> AmberConfig:
    """Load amber.yaml, returning defaults if not found."""
    path = find_config_path(start)
    if path is None:
        return AmberConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return AmberConfig(
        name=raw.get("name", ""),
        agents=raw.get("agents", []),
        app=raw.get("app", ""),
        worker=raw.get("worker", ""),
        path_prefix=raw.get("path_prefix", "") or "",
        profile=raw.get("profile", "") or "",
        region=raw.get("region", "us-east-1"),
        environment=raw.get("environment", "dev"),
        dashboard=raw.get("dashboard", True),
        project_prefix=raw.get("project_prefix", ""),
        frontend=_parse_frontend(raw.get("frontend")),
    )


def _parse_frontend(raw: dict | None) -> FrontendConfig | None:
    """Parse the optional `frontend:` block into a FrontendConfig."""
    if not isinstance(raw, dict):
        return None
    return FrontendConfig(
        type=raw.get("type", "") or "",
        path=raw.get("path", "") or "",
        build=raw.get("build", "") or "npm run build",
        output=raw.get("output", "") or "dist",
    )


def validate_deploy_config(config: AmberConfig) -> list[str]:
    """Return deploy-blocking config errors."""
    errors: list[str] = []
    if not config.name:
        errors.append("name is required")
    if not config.app:
        errors.append("app is required, for example: my_app.main:app")
    if not config.worker:
        errors.append("worker is required, for example: my_app.main:agent_runtime")
    if config.path_prefix and not config.path_prefix.startswith("/"):
        errors.append("path_prefix must start with /")
    errors.extend(_validate_frontend(config))
    return errors


def _validate_frontend(config: AmberConfig) -> list[str]:
    fe = config.frontend
    if fe is None or not fe.type:
        return []
    errors: list[str] = []
    if fe.type != "react":
        errors.append(
            f"frontend.type {fe.type!r} is not supported (only 'react')."
        )
        return errors
    if not fe.path:
        errors.append("frontend.path is required when frontend.type is react.")
    if config.path_prefix != "/api":
        errors.append(
            "frontend.type react requires path_prefix: /api "
            "(the reserved customer API route)."
        )
    return errors


def resolve_secret_path(key: str, config: AmberConfig) -> dict:
    """Resolve a friendly key name to its AWS location."""
    if key not in SECRET_REGISTRY:
        raise ValueError(
            f"Unknown key: {key}\n"
            f"Known keys: {', '.join(SECRET_REGISTRY.keys())}"
        )

    entry = SECRET_REGISTRY[key].copy()
    entry["path"] = entry["path"].format(
        ssm_base=config.ssm_base,
        secrets_prefix=config.secrets_prefix,
    )
    return entry
