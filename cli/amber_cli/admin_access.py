"""Shared Cognito admin-user guidance for Amber CLI commands."""

from __future__ import annotations

from typing import Any

from rich.console import Console


ADMIN_CREATE_USER_HINT = "amber admin create-user --email <you@example.com>"


def admin_users_exist(session: Any, user_pool_id: str, region: str) -> bool:
    """Return whether the Cognito user pool has at least one admin user."""
    client = session.client("cognito-idp", region_name=region)
    response = client.list_users(UserPoolId=user_pool_id, Limit=1)
    return bool(response.get("Users"))


def print_admin_access_status(
    console: Console,
    session: Any,
    tf_out: dict[str, object],
    region: str,
) -> None:
    """Print advisory dashboard admin setup status."""
    user_pool_id = str(tf_out.get("cognito_user_pool_id") or "")
    cognito_region = str(tf_out.get("cognito_region") or region)
    if not user_pool_id:
        console.print("[yellow]Admin access: Cognito is not deployed yet.[/yellow]")
        return

    try:
        if admin_users_exist(session, user_pool_id, cognito_region):
            console.print("[green]Admin access: ready[/green]")
            return
    except Exception as exc:
        console.print(f"[yellow]Admin access: could not verify admin users ({exc}).[/yellow]")
        console.print(f"  To create one: {ADMIN_CREATE_USER_HINT}")
        return

    console.print("[yellow]Admin access: no dashboard admin user exists yet.[/yellow]")
    console.print(f"  Create one: {ADMIN_CREATE_USER_HINT}")
    console.print("  Cognito will email the temporary password.")
