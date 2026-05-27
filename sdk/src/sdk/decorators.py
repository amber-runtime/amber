import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from dbos import DBOS
from dbos_openai_agents import DBOSRunner


@dataclass(frozen=True)
class RegisteredAgent:
    name: str
    workflow: Callable[..., Any]
    queued: bool = False


_registered_agents: dict[str, RegisteredAgent] = {}


def workflow(
    *,
    name: str | None = None,
    max_recovery_attempts: int | None = 5,
):
    return DBOS.workflow(name=name, max_recovery_attempts=max_recovery_attempts)


def register_agent(
    *,
    name: str,
    max_recovery_attempts: int | None = 5,
    queued: bool = False,
):
    if not name:
        raise ValueError("Agent name must be a non-empty string.")

    def decorator(fn: Callable[..., Any]):
        if name in _registered_agents:
            raise ValueError(f"Agent {name!r} is already registered.")

        workflow_fn = workflow(
            name=name,
            max_recovery_attempts=max_recovery_attempts,
        )(fn)
        _registered_agents[name] = RegisteredAgent(
            name=name,
            workflow=workflow_fn,
            queued=queued,
        )
        return workflow_fn

    return decorator


def get_registered_agent(name: str) -> RegisteredAgent:
    try:
        return _registered_agents[name]
    except KeyError:
        registered = ", ".join(sorted(_registered_agents)) or "none"
        raise ValueError(
            f"Agent {name!r} is not registered. Registered agents: {registered}."
        ) from None


def list_registered_agents() -> list[RegisteredAgent]:
    return [_registered_agents[name] for name in sorted(_registered_agents)]


def step(
    *,
    name: str | None = None,
    retries_allowed: bool = False,
    interval_seconds: float = 1.0,
    max_attempts: int = 3,
    backoff_rate: float = 2.0,
    should_retry: Callable[[BaseException], bool | Awaitable[bool]] | None = None,
):
    dbos_step = DBOS.step(
        name=name,
        retries_allowed=retries_allowed,
        interval_seconds=interval_seconds,
        max_attempts=max_attempts,
        backoff_rate=backoff_rate,
        should_retry=should_retry,
    )

    def decorator(fn):
        step_name = fn.__name__

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def wrapped_step(*args: Any, **kwargs: Any):
                started_at = _log_step_started(step_name)
                try:
                    result = await fn(*args, **kwargs)
                    _log_step_succeeded(step_name, started_at)
                    return result
                except Exception as exc:
                    _log_step_failed(step_name, started_at, exc)
                    raise

        else:

            @functools.wraps(fn)
            def wrapped_step(*args: Any, **kwargs: Any):
                started_at = _log_step_started(step_name)
                try:
                    result = fn(*args, **kwargs)
                    _log_step_succeeded(step_name, started_at)
                    return result
                except Exception as exc:
                    _log_step_failed(step_name, started_at, exc)
                    raise

        return dbos_step(wrapped_step)

    return decorator


async def sleep(*args, **kwargs):
    return await DBOS.sleep_async(*args, **kwargs)


async def agent_runner(*args, **kwargs):
    return await DBOSRunner.run(*args, **kwargs)


logger = DBOS.logger


def _log_step_started(step_name: str) -> float:
    logger.info("step %s started", step_name)
    return time.monotonic()


def _log_step_succeeded(step_name: str, started_at: float) -> None:
    logger.info("step %s done (%.2fs)", step_name, time.monotonic() - started_at)


def _log_step_failed(step_name: str, started_at: float, exc: Exception) -> None:
    logger.error(
        "step %s failed (%.2fs): %s", step_name, time.monotonic() - started_at, exc
    )
