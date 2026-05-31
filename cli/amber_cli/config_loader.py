"""Load and parse amber.yaml configuration."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class AmberConfig:
    """Represents an amber.yaml configuration."""

    name: str = ""
    agents: list[str] = field(default_factory=list)
    region: str = "us-east-1"
    environment: str = "dev"
    dashboard: bool = True
    project_prefix: str = ""  # terraform project name, defaults to config name

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
        region=raw.get("region", "us-east-1"),
        environment=raw.get("environment", "dev"),
        dashboard=raw.get("dashboard", True),
        project_prefix=raw.get("project_prefix", ""),
    )


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
