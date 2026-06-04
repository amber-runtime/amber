"""Cognito Hosted-UI login and token cache for the Amber dashboard CLI.

Mirrors the browser PKCE flow in dashboard/frontend/src/lib/auth.tsx so the CLI
authenticates as the same Cognito admin user, but keeps its own persistent
session under ~/.amber/credentials.json. A human runs ``amber admin login``
once; the refresh token then lets read commands (including ones invoked by
coding agents) run non-interactively until the refresh window lapses.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"
SCOPE = "openid email profile"
EXPIRY_BUFFER_SECONDS = 30
LOGIN_TIMEOUT_SECONDS = 300

CREDENTIALS_PATH = Path.home() / ".amber" / "credentials.json"

LOGIN_HINT = "Run: amber admin login"
SESSION_EXPIRED_MESSAGE = f"Admin session expired. {LOGIN_HINT}"

_SUCCESS_HTML = (
    b"<!doctype html><html><body style=\"font-family:sans-serif;background:#0f172a;"
    b"color:#e2e8f0;display:grid;place-items:center;height:100vh\">"
    b"<div><h2>Amber CLI login complete</h2><p>You can close this tab and return "
    b"to your terminal.</p></div></body></html>"
)


class DashboardAuthError(Exception):
    """Raised when CLI dashboard authentication fails."""


@dataclass
class AuthConfig:
    """Cognito parameters served by GET /admin/api/auth/config."""

    enabled: bool
    domain: str
    issuer: str
    client_id: str
    region: str
    user_pool_id: str


# --- PKCE helpers (mirror dashboard/frontend/src/lib/auth.tsx) ----------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _random_string() -> str:
    return _b64url(secrets.token_bytes(32))


def _pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


# --- TLS trust store ----------------------------------------------------------

try:
    import certifi

    _CA_FILE: Optional[str] = certifi.where()
except ModuleNotFoundError:  # pragma: no cover — certifi is a declared dependency
    _CA_FILE = None


def ssl_context() -> ssl.SSLContext:
    """Verify TLS against certifi's CA bundle so requests do not depend on the
    host interpreter's default CA store (which may be missing, e.g. some
    pyenv-built Pythons have no cafile and fail every HTTPS verification)."""
    return ssl.create_default_context(cafile=_CA_FILE)


# --- HTTP seams (monkeypatched in tests) --------------------------------------


def _http_get_json(url: str, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=30, context=ssl_context()) as resp:  # noqa: S310 (trusted https)
        return json.loads(resp.read().decode("utf-8"))


def _http_post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30, context=ssl_context()) as resp:  # noqa: S310 (trusted https)
        return json.loads(resp.read().decode("utf-8"))


def fetch_auth_config(api_base: str) -> AuthConfig:
    """Fetch Cognito config from the public ``/auth/config`` endpoint."""
    try:
        payload = _http_get_json(f"{api_base}/auth/config")
    except urllib.error.URLError as exc:
        raise DashboardAuthError(f"Could not reach dashboard API at {api_base}: {exc}") from exc
    return AuthConfig(
        enabled=bool(payload.get("enabled")),
        domain=str(payload.get("domain") or "").rstrip("/"),
        issuer=str(payload.get("issuer") or ""),
        client_id=str(payload.get("client_id") or ""),
        region=str(payload.get("region") or ""),
        user_pool_id=str(payload.get("user_pool_id") or ""),
    )


# --- Token cache (~/.amber/credentials.json, mode 0600) -----------------------


def _session_key(domain: str, client_id: str) -> str:
    return f"{domain}|{client_id}"


def _read_cache() -> dict[str, Any]:
    try:
        with open(CREDENTIALS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(cache: dict[str, Any]) -> None:
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(CREDENTIALS_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)
    os.chmod(CREDENTIALS_PATH, 0o600)


def _store_tokens(config: AuthConfig, tokens: dict[str, Any]) -> None:
    cache = _read_cache()
    sessions = cache.setdefault("sessions", {})
    key = _session_key(config.domain, config.client_id)
    existing = sessions.get(key, {})
    sessions[key] = {
        "domain": config.domain,
        "client_id": config.client_id,
        "access_token": tokens["access_token"],
        # Refresh-token grants do not return a new refresh token; keep the old one.
        "refresh_token": tokens.get("refresh_token") or existing.get("refresh_token"),
        "expires_at": time.time() + int(tokens.get("expires_in", 3600)),
    }
    _write_cache(cache)


def clear_session(config: Optional[AuthConfig] = None) -> bool:
    """Remove a cached session (or all of them). Returns True if anything was removed."""
    cache = _read_cache()
    sessions = cache.get("sessions", {})
    if not sessions:
        return False
    if config is None:
        cache["sessions"] = {}
        _write_cache(cache)
        return True
    key = _session_key(config.domain, config.client_id)
    if key in sessions:
        del sessions[key]
        _write_cache(cache)
        return True
    return False


# --- Login + token retrieval --------------------------------------------------


def _authorize_url(config: AuthConfig, state: str, challenge: str) -> str:
    params = urllib.parse.urlencode(
        {
            "client_id": config.client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
        }
    )
    return f"{config.domain}/oauth2/authorize?{params}"


def _capture_authorization_code(expected_state: str) -> str:
    """Serve the localhost callback until Cognito redirects back with a code."""
    holder: dict[str, Optional[str]] = {}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            params = urllib.parse.parse_qs(parsed.query)
            holder["code"] = (params.get("code") or [None])[0]
            holder["state"] = (params.get("state") or [None])[0]
            holder["error"] = (params.get("error") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_SUCCESS_HTML)

        def log_message(self, *_args: Any) -> None:  # silence default logging
            return

    server = http.server.HTTPServer((CALLBACK_HOST, CALLBACK_PORT), _Handler)
    server.timeout = LOGIN_TIMEOUT_SECONDS
    try:
        deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
        while "code" not in holder and "error" not in holder:
            if time.monotonic() > deadline:
                raise DashboardAuthError("Timed out waiting for browser login.")
            server.handle_request()
    finally:
        server.server_close()

    if holder.get("error"):
        raise DashboardAuthError(f"Login failed: {holder['error']}")
    if not holder.get("state") or holder["state"] != expected_state:
        raise DashboardAuthError("Invalid login response (state mismatch).")
    code = holder.get("code")
    if not code:
        raise DashboardAuthError("Login response did not include an authorization code.")
    return code


def login(api_base: str, *, open_browser: bool = True) -> AuthConfig:
    """Run the Cognito Hosted-UI PKCE flow and cache the resulting tokens."""
    config = fetch_auth_config(api_base)
    if not config.enabled:
        raise DashboardAuthError(
            "Dashboard auth is not enabled on this deployment; no login required."
        )
    if not config.domain or not config.client_id:
        raise DashboardAuthError("Dashboard auth config is incomplete. Has amber deploy run?")

    verifier = _random_string()
    state = _random_string()
    challenge = _pkce_challenge(verifier)
    url = _authorize_url(config, state, challenge)

    if open_browser:
        webbrowser.open(url)
    else:
        print(f"Open this URL in your browser to log in:\n{url}")

    code = _capture_authorization_code(state)
    try:
        tokens = _http_post_form(
            f"{config.domain}/oauth2/token",
            {
                "client_id": config.client_id,
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            },
        )
    except urllib.error.HTTPError as exc:
        raise DashboardAuthError(f"Token exchange failed: HTTP {exc.code}") from exc
    _store_tokens(config, tokens)
    return config


def get_access_token(config: AuthConfig) -> str:
    """Return a valid access token, refreshing transparently when needed."""
    cache = _read_cache()
    key = _session_key(config.domain, config.client_id)
    session = cache.get("sessions", {}).get(key)
    if not session:
        raise DashboardAuthError(LOGIN_HINT)

    if float(session.get("expires_at", 0)) > time.time() + EXPIRY_BUFFER_SECONDS:
        return str(session["access_token"])

    refresh_token = session.get("refresh_token")
    if not refresh_token:
        raise DashboardAuthError(SESSION_EXPIRED_MESSAGE)
    try:
        tokens = _http_post_form(
            f"{config.domain}/oauth2/token",
            {
                "client_id": config.client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    except urllib.error.HTTPError as exc:
        raise DashboardAuthError(SESSION_EXPIRED_MESSAGE) from exc
    tokens.setdefault("refresh_token", refresh_token)
    _store_tokens(config, tokens)
    return str(tokens["access_token"])
