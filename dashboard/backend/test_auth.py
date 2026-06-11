from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from dashboard.backend import server


ISSUER = "https://cognito-idp.us-west-2.amazonaws.com/us-west-2_test"
CLIENT_ID = "dashboard-client"


@dataclass
class SigningKey:
    key: Any


class FakeJwksClient:
    def __init__(self, key: Any):
        self.key = key

    def get_signing_key_from_jwt(self, _token: str) -> SigningKey:
        return SigningKey(self.key)


class FakeDashboardClient:
    async def list_workflows(self, **_kwargs):
        return [
            {
                "workflow_id": "wf-1",
                "name": "agent",
                "status": "SUCCESS",
                "created_at": 1,
                "updated_at": 2,
                "recovery_attempts": 1,
            }
        ]


def configure_auth(monkeypatch, public_key: Any | None = None) -> None:
    monkeypatch.setattr(server, "DASHBOARD_AUTH_MODE", "auto")
    monkeypatch.setattr(server, "COGNITO_ISSUER", ISSUER)
    monkeypatch.setattr(server, "COGNITO_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(server, "COGNITO_REGION", "us-west-2")
    monkeypatch.setattr(server, "COGNITO_USER_POOL_ID", "us-west-2_test")
    monkeypatch.setattr(server, "COGNITO_DOMAIN", "https://example.auth.us-west-2.amazoncognito.com")
    if public_key is not None:
        monkeypatch.setattr(server, "_get_jwks_client", lambda: FakeJwksClient(public_key))


def make_token(private_key: Any, **claims: Any) -> str:
    payload = {
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "exp": int(time.time()) + 300,
        "sub": "user-1",
        **claims,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def test_health_and_auth_config_are_public(monkeypatch) -> None:
    configure_auth(monkeypatch)
    client = TestClient(server.app)

    assert client.get("/health").status_code == 200
    config = client.get("/auth/config")

    assert config.status_code == 200
    assert config.json()["enabled"] is True
    assert config.json()["client_id"] == CLIENT_ID


def test_auth_config_auto_without_cognito_disables_auth(monkeypatch) -> None:
    monkeypatch.setattr(server, "DASHBOARD_AUTH_MODE", "auto")
    monkeypatch.setattr(server, "COGNITO_ISSUER", "")
    monkeypatch.setattr(server, "COGNITO_CLIENT_ID", "")
    client = TestClient(server.app)

    response = client.get("/auth/config")

    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_auth_config_disabled_ignores_cognito_config(monkeypatch) -> None:
    configure_auth(monkeypatch)
    monkeypatch.setattr(server, "DASHBOARD_AUTH_MODE", "disabled")
    monkeypatch.setattr(server, "get_dashboard_client", lambda: FakeDashboardClient())
    client = TestClient(server.app)

    config = client.get("/auth/config")
    workflows = client.get("/workflows")

    assert config.status_code == 200
    assert config.json()["enabled"] is False
    assert workflows.status_code == 200


def test_auth_config_required_with_cognito_enables_auth(monkeypatch) -> None:
    configure_auth(monkeypatch)
    monkeypatch.setattr(server, "DASHBOARD_AUTH_MODE", "required")
    client = TestClient(server.app)

    response = client.get("/auth/config")

    assert response.status_code == 200
    assert response.json()["enabled"] is True


def test_auth_config_required_without_cognito_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(server, "DASHBOARD_AUTH_MODE", "required")
    monkeypatch.setattr(server, "COGNITO_ISSUER", "")
    monkeypatch.setattr(server, "COGNITO_CLIENT_ID", "")
    monkeypatch.setattr(server, "get_dashboard_client", lambda: FakeDashboardClient())
    client = TestClient(server.app)

    config = client.get("/auth/config")
    workflows = client.get("/workflows")

    assert config.status_code == 503
    assert "Dashboard auth is required" in config.json()["detail"]
    assert workflows.status_code == 503
    assert "Dashboard auth is required" in workflows.json()["detail"]


def test_auth_config_required_without_hosted_ui_domain_fails_closed(monkeypatch) -> None:
    configure_auth(monkeypatch)
    monkeypatch.setattr(server, "DASHBOARD_AUTH_MODE", "required")
    monkeypatch.setattr(server, "COGNITO_DOMAIN", "")
    client = TestClient(server.app)

    response = client.get("/auth/config")

    assert response.status_code == 503
    assert "COGNITO_DOMAIN" in response.json()["detail"]


def test_dashboard_routes_reject_missing_auth(monkeypatch) -> None:
    configure_auth(monkeypatch)
    client = TestClient(server.app)

    routes = [
        ("GET", "/workflows", None),
        ("GET", "/queued-workflows", None),
        ("GET", "/workflows/wf-1", None),
        ("GET", "/pricing", None),
        ("POST", "/workflows/wf-1/resume", None),
        ("POST", "/workflows/wf-1/cancel", None),
        ("POST", "/workflows/delete", {"workflow_ids": ["wf-1"]}),
        ("POST", "/workflows/wf-1/fork", {"start_step": 1}),
    ]

    for method, path, body in routes:
        response = client.request(method, path, json=body)
        assert response.status_code == 401, path


def test_dashboard_routes_reject_invalid_auth(monkeypatch) -> None:
    configure_auth(monkeypatch)
    client = TestClient(server.app)

    response = client.get("/workflows", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


def test_valid_cognito_access_token_allows_dashboard_route(monkeypatch) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    configure_auth(monkeypatch, key.public_key())
    monkeypatch.setattr(server, "get_dashboard_client", lambda: FakeDashboardClient())
    token = make_token(key)
    client = TestClient(server.app)

    response = client.get("/workflows", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["workflows"][0]["workflow_id"] == "wf-1"
