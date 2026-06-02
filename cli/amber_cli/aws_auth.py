"""Shared AWS authentication helpers for Amber CLI commands."""

from __future__ import annotations

from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound
from rich.console import Console


@dataclass
class AWSIdentity:
    account: str
    arn: str
    user_id: str


class AWSAuthError(Exception):
    """Raised when AWS credentials are missing, invalid, or expired."""


def create_session(profile: str = "", region: str = "us-east-1") -> boto3.Session:
    kwargs = {"region_name": region}
    if profile:
        kwargs["profile_name"] = profile
    return boto3.Session(**kwargs)


def verify_identity(profile: str = "", region: str = "us-east-1") -> AWSIdentity:
    try:
        session = create_session(profile, region)
        resp = session.client("sts", region_name=region).get_caller_identity()
    except (NoCredentialsError, ProfileNotFound, ClientError, BotoCoreError) as exc:
        raise AWSAuthError(_friendly_error(str(exc), profile)) from exc

    return AWSIdentity(
        account=resp.get("Account", ""),
        arn=resp.get("Arn", ""),
        user_id=resp.get("UserId", ""),
    )


def require_identity(profile: str = "", region: str = "us-east-1") -> tuple[boto3.Session, AWSIdentity]:
    identity = verify_identity(profile, region)
    return create_session(profile, region), identity


def print_auth_error(console: Console, error: Exception, retry_command: str) -> None:
    console.print("[red]AWS credentials are invalid or expired.[/red]")
    console.print()
    console.print(str(error))
    console.print()
    console.print("Run:")
    console.print("  amber auth setup")
    console.print()
    console.print("Then retry:")
    console.print(f"  {retry_command}")


def is_auth_client_error(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    message = exc.response.get("Error", {}).get("Message", "")
    text = f"{code} {message}".lower()
    return any(
        token in text
        for token in [
            "invalidclienttokenid",
            "unrecognizedclientexception",
            "expiredtoken",
            "unauthorizedssotoken",
            "security token",
        ]
    )


def _friendly_error(message: str, profile: str) -> str:
    profile_hint = f" for profile {profile!r}" if profile else ""
    lower = message.lower()
    if "profile" in lower and "not found" in lower:
        return f"AWS profile{profile_hint} was not found."
    if "sso" in lower or "token" in lower:
        return f"The AWS session{profile_hint} is missing, invalid, or expired."
    if "credential" in lower:
        return f"Amber could not find usable AWS credentials{profile_hint}."
    return message
