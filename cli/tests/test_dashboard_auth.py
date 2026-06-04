from __future__ import annotations

import base64
import hashlib
import json
import stat
import time
import urllib.error
from pathlib import Path

import pytest

from amber_cli import dashboard_auth as auth


@pytest.fixture
def cache_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / ".amber" / "credentials.json"
    monkeypatch.setattr(auth, "CREDENTIALS_PATH", path)
    return path


def _config() -> auth.AuthConfig:
    return auth.AuthConfig(
        enabled=True,
        domain="https://example.auth.us-east-1.amazoncognito.com",
        issuer="https://issuer",
        client_id="client123",
        region="us-east-1",
        user_pool_id="pool",
    )


def test_pkce_challenge_is_s256_of_verifier() -> None:
    verifier = auth._random_string()
    challenge = auth._pkce_challenge(verifier)
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert challenge == expected
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge


def test_authorize_url_carries_pkce_params() -> None:
    url = auth._authorize_url(_config(), state="st", challenge="ch")
    assert url.startswith("https://example.auth.us-east-1.amazoncognito.com/oauth2/authorize?")
    assert "code_challenge=ch" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert "client_id=client123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback" in url


def test_store_tokens_writes_cache_with_0600(cache_path) -> None:
    auth._store_tokens(
        _config(),
        {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600},
    )
    assert cache_path.exists()
    mode = stat.S_IMODE(cache_path.stat().st_mode)
    assert mode == 0o600
    data = json.loads(cache_path.read_text())
    session = data["sessions"]["https://example.auth.us-east-1.amazoncognito.com|client123"]
    assert session["access_token"] == "a1"
    assert session["refresh_token"] == "r1"


def test_get_access_token_returns_cached_when_valid(cache_path) -> None:
    auth._store_tokens(_config(), {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600})
    assert auth.get_access_token(_config()) == "a1"


def test_get_access_token_refreshes_when_expired(cache_path, monkeypatch) -> None:
    auth._store_tokens(_config(), {"access_token": "old", "refresh_token": "r1", "expires_in": 1})
    # Force expiry.
    cache = auth._read_cache()
    key = "https://example.auth.us-east-1.amazoncognito.com|client123"
    cache["sessions"][key]["expires_at"] = time.time() - 10
    auth._write_cache(cache)

    calls: list[tuple[str, dict]] = []

    def fake_post(url: str, fields: dict) -> dict:
        calls.append((url, fields))
        return {"access_token": "new", "expires_in": 3600}

    monkeypatch.setattr(auth, "_http_post_form", fake_post)

    assert auth.get_access_token(_config()) == "new"
    assert calls[0][0].endswith("/oauth2/token")
    assert calls[0][1]["grant_type"] == "refresh_token"
    assert calls[0][1]["refresh_token"] == "r1"
    # New access token persisted; refresh token preserved across the grant.
    session = auth._read_cache()["sessions"][key]
    assert session["access_token"] == "new"
    assert session["refresh_token"] == "r1"


def test_get_access_token_without_session_points_to_login(cache_path) -> None:
    with pytest.raises(auth.DashboardAuthError) as exc:
        auth.get_access_token(_config())
    assert "amber admin login" in str(exc.value)


def test_get_access_token_failed_refresh_reports_expired(cache_path, monkeypatch) -> None:
    auth._store_tokens(_config(), {"access_token": "old", "refresh_token": "r1", "expires_in": 1})
    cache = auth._read_cache()
    key = "https://example.auth.us-east-1.amazoncognito.com|client123"
    cache["sessions"][key]["expires_at"] = time.time() - 10
    auth._write_cache(cache)

    def fake_post(url: str, fields: dict) -> dict:
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(auth, "_http_post_form", fake_post)

    with pytest.raises(auth.DashboardAuthError) as exc:
        auth.get_access_token(_config())
    assert "Admin session expired" in str(exc.value)
    assert "amber admin login" in str(exc.value)


def test_login_exchanges_captured_code_for_tokens(cache_path, monkeypatch) -> None:
    api_base = "https://cf.example.com/admin/api"
    monkeypatch.setattr(
        auth, "fetch_auth_config", lambda base: _config() if base == api_base else None
    )
    monkeypatch.setattr(auth, "_capture_authorization_code", lambda state: "auth-code")

    posted: list[tuple[str, dict]] = []

    def fake_post(url: str, fields: dict) -> dict:
        posted.append((url, fields))
        return {"access_token": "a2", "refresh_token": "r2", "expires_in": 3600}

    monkeypatch.setattr(auth, "_http_post_form", fake_post)

    config = auth.login(api_base, open_browser=False)
    assert config.client_id == "client123"
    assert posted[0][0].endswith("/oauth2/token")
    assert posted[0][1]["grant_type"] == "authorization_code"
    assert posted[0][1]["code"] == "auth-code"
    assert posted[0][1]["redirect_uri"] == auth.REDIRECT_URI
    # Tokens are cached after login.
    assert auth.get_access_token(_config()) == "a2"


def test_clear_session_removes_cached_tokens(cache_path) -> None:
    auth._store_tokens(_config(), {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600})
    assert auth.clear_session() is True
    assert auth.clear_session() is False
