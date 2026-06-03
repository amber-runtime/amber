"""Public Amber route helpers."""

from __future__ import annotations

ADMIN_PATH = "/admin/"
ADMIN_API_HEALTH_PATH = "/admin/api/health"
CUSTOMER_APP_PATH = "/"


def public_urls(cloudfront_domain: str) -> dict[str, str]:
    base = f"https://{cloudfront_domain}"
    return {
        "customer_app": f"{base}{CUSTOMER_APP_PATH}",
        "amber_admin": f"{base}{ADMIN_PATH}",
        "admin_api_health": f"{base}{ADMIN_API_HEALTH_PATH}",
    }
