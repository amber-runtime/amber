"""HTTP client for the deployed Amber admin dashboard API.

Resolves the API base URL from .amber terraform outputs, obtains a Cognito
access token via ``dashboard_auth``, and calls the read-only ``/admin/api``
workflow endpoints with ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from amber_cli import dashboard_auth

NO_OUTPUTS_MESSAGE = "Could not read .amber terraform outputs. Has amber deploy run?"
AUTH_REQUIRED_MESSAGE = dashboard_auth.LOGIN_HINT  # "Run: amber admin login"


class DashboardAPIError(Exception):
    """Raised when a dashboard API request cannot be completed."""


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def _terraform_output(tf_dir: Path) -> dict[str, Any]:
    result = _run(["terraform", "output", "-json"], cwd=tf_dir)
    raw = json.loads(result.stdout)
    return {k: v["value"] for k, v in raw.items()}


def resolve_api_base(config_path: str) -> str:
    """Build ``https://<cloudfront_domain>/admin/api`` from terraform outputs."""
    repo_root = Path(config_path).resolve().parent
    tf_dir = repo_root / ".amber" / "terraform"
    try:
        tf_out = _terraform_output(tf_dir)
    except Exception as exc:  # noqa: BLE001 — surface a single actionable message
        raise DashboardAPIError(NO_OUTPUTS_MESSAGE) from exc
    cloudfront = str(tf_out.get("cloudfront_domain") or "")
    if not cloudfront:
        raise DashboardAPIError(NO_OUTPUTS_MESSAGE)
    return f"https://{cloudfront}/admin/api"


def resolve_context(config_path: str) -> tuple[str, Optional[str]]:
    """Return (api_base, access_token). Token is None when auth is disabled."""
    api_base = resolve_api_base(config_path)
    config = dashboard_auth.fetch_auth_config(api_base)
    token = dashboard_auth.get_access_token(config) if config.enabled else None
    return api_base, token


# --- HTTP seam (monkeypatched in tests) ---------------------------------------


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30, context=dashboard_auth.ssl_context()) as resp:  # noqa: S310 (trusted https)
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        return exc.code, body
    except urllib.error.URLError as exc:
        raise DashboardAPIError(f"Could not reach dashboard API: {exc}") from exc


def _get_json(
    api_base: str,
    path: str,
    token: Optional[str],
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    url = f"{api_base}{path}"
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if query:
            url = f"{url}?{query}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status, body = _http_get(url, headers)
    if status == 401:
        raise DashboardAPIError(AUTH_REQUIRED_MESSAGE)
    if status >= 400:
        raise DashboardAPIError(f"Dashboard API error {status}: {body[:200]}")
    return json.loads(body)


# --- Endpoint wrappers --------------------------------------------------------


def list_workflows(
    api_base: str,
    token: Optional[str],
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    return _get_json(
        api_base,
        "/workflows",
        token,
        {"status": status, "limit": limit, "offset": offset},
    )


def list_queued(
    api_base: str,
    token: Optional[str],
    *,
    queue_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    return _get_json(
        api_base,
        "/queued-workflows",
        token,
        {"queue_name": queue_name, "limit": limit, "offset": offset},
    )


def get_workflow(api_base: str, token: Optional[str], workflow_id: str) -> dict[str, Any]:
    return _get_json(api_base, f"/workflows/{urllib.parse.quote(workflow_id)}", token)
