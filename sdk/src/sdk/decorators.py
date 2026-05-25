import asyncio
import functools
import importlib
import os
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from dbos import DBOS, DBOSConfig
from dbos_openai_agents import DBOSRunner


@dataclass(frozen=True)
class RegisteredAgent:
    name: str
    workflow: Callable[..., Any]


_registered_agents: dict[str, RegisteredAgent] = {}
_init_lock = threading.Lock()
_initialized = False
DEFAULT_AGENT_QUEUE = "agent-runs"


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
        _registered_agents[name] = RegisteredAgent(name=name, workflow=workflow_fn)
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


async def agentic_runner(*args, **kwargs):
    return await DBOSRunner.run(*args, **kwargs)


logger = DBOS.logger


def _runtime_config(
    *,
    name: str | None = None,
    db_url: str | None = None,
    conductor_key: str | None = None,
) -> DBOSConfig:
    resolved_name = name or os.environ.get(
        "CHECKPOINT_RUNTIME_NAME", "checkpoint-runtime"
    )
    resolved_db = (
        db_url or os.environ.get("DB_URL") or os.environ.get("DBOS_SYSTEM_DATABASE_URL")
    )
    resolved_conductor_key = (
        conductor_key
        or os.environ.get("CHECKPOINT_CONDUCTOR_KEY")
        or os.environ.get("DBOS_CONDUCTOR_KEY")
    )

    config: DBOSConfig = {
        "name": resolved_name,
        "system_database_url": resolved_db,
    }
    if resolved_conductor_key is not None:
        config["conductor_key"] = resolved_conductor_key

    return config


def _launch_dbos(
    *,
    name: str | None = None,
    db_url: str | None = None,
    conductor_key: str | None = None,
    listen_queues: list[str] | tuple[str, ...] | None = None,
    before_launch: Callable[[DBOSConfig], None] | None = None,
) -> None:
    global _initialized

    config = _runtime_config(
        name=name,
        db_url=db_url,
        conductor_key=conductor_key,
    )

    with _init_lock:
        if _initialized:
            if before_launch is not None or listen_queues is not None:
                raise RuntimeError(
                    "DBOS is already initialized; queue listeners must be configured "
                    "before DBOS.launch()."
                )
            return

        DBOS(config=config)
        if listen_queues is not None:
            listen_agent_queues(listen_queues)
        if before_launch is not None:
            before_launch(config)
        DBOS.launch()
        _initialized = True

        resolved_db = config.get("system_database_url")
        if isinstance(resolved_db, str) and resolved_db.startswith("postgresql"):
            from sdk.tracing import register_checkpoint_tracing_processor

            register_checkpoint_tracing_processor(resolved_db)


def init(
    name: str | None = None,
    db_url: str | None = None,
    conductor_key: str | None = None,
    listen_queues: list[str] | tuple[str, ...] | None = None,
) -> None:
    _launch_dbos(
        name=name,
        db_url=db_url,
        conductor_key=conductor_key,
        listen_queues=listen_queues,
    )


def ensure_initialized(
    *,
    name: str | None = None,
    db_url: str | None = None,
    conductor_key: str | None = None,
    listen_queues: list[str] | tuple[str, ...] | None = None,
) -> None:
    init(
        name=name,
        db_url=db_url,
        conductor_key=conductor_key,
        listen_queues=listen_queues,
    )


async def start_agent(name: str, input: str):
    ensure_initialized()
    registered_agent = get_registered_agent(name)
    return await DBOS.start_workflow_async(registered_agent.workflow, input)


def register_agent_queue(
    queue_name: str = DEFAULT_AGENT_QUEUE,
    *,
    worker_concurrency: int | None = 1,
    concurrency: int | None = None,
    limiter: dict[str, Any] | None = None,
    priority_enabled: bool = False,
    partition_queue: bool = False,
    polling_interval_sec: float = 1.0,
    on_conflict: str = "update_if_latest_version",
):
    ensure_initialized()
    return DBOS.register_queue(
        queue_name,
        worker_concurrency=worker_concurrency,
        concurrency=concurrency,
        limiter=limiter,
        priority_enabled=priority_enabled,
        partition_queue=partition_queue,
        polling_interval_sec=polling_interval_sec,
        on_conflict=on_conflict,
    )


def listen_agent_queues(
    queue_names: list[str] | tuple[str, ...] = (DEFAULT_AGENT_QUEUE,),
) -> None:
    DBOS.listen_queues(list(queue_names))


async def enqueue_agent(
    name: str,
    input: str,
    *,
    queue_name: str = DEFAULT_AGENT_QUEUE,
):
    ensure_initialized()
    registered_agent = get_registered_agent(name)
    register_agent_queue(queue_name, on_conflict="never_update")
    return await DBOS.enqueue_workflow_async(
        queue_name,
        registered_agent.workflow,
        input,
    )


def run_agent_worker(
    *,
    agent_modules: list[str] | tuple[str, ...],
    queue_name: str = DEFAULT_AGENT_QUEUE,
    worker_concurrency: int | None = 1,
    concurrency: int | None = None,
    limiter: dict[str, Any] | None = None,
    priority_enabled: bool = False,
    partition_queue: bool = False,
    polling_interval_sec: float = 1.0,
    on_conflict: str = "update_if_latest_version",
    name: str | None = None,
    db_url: str | None = None,
    conductor_key: str | None = None,
    keep_alive: bool = True,
) -> None:
    if not agent_modules:
        raise ValueError("agent_modules must include at least one import path.")

    imported_modules = []
    for module_name in agent_modules:
        imported_modules.append(importlib.import_module(module_name).__name__)

    if not _registered_agents:
        raise RuntimeError(
            "No agents are registered. Check that agent_modules imports modules "
            "containing @register_agent workflows."
        )

    def configure_worker(config: DBOSConfig) -> None:
        listen_agent_queues([queue_name])
        logger.info(
            "agent worker configured queue=%s worker_concurrency=%s "
            "concurrency=%s runtime=%s modules=%s registered_agents=%s",
            queue_name,
            worker_concurrency,
            concurrency,
            config.get("name"),
            imported_modules,
            [agent.name for agent in list_registered_agents()],
        )

    _launch_dbos(
        name=name,
        db_url=db_url,
        conductor_key=conductor_key,
        before_launch=configure_worker,
    )

    DBOS.register_queue(
        queue_name,
        worker_concurrency=worker_concurrency,
        concurrency=concurrency,
        limiter=limiter,
        priority_enabled=priority_enabled,
        partition_queue=partition_queue,
        polling_interval_sec=polling_interval_sec,
        on_conflict=on_conflict,
    )
    logger.info("agent worker listening on queues=%s", [queue_name])
    if keep_alive:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            logger.info("agent worker shutting down")


def _log_step_started(step_name: str) -> float:
    logger.info("step %s started", step_name)
    return time.monotonic()


def _log_step_succeeded(step_name: str, started_at: float) -> None:
    logger.info("step %s done (%.2fs)", step_name, time.monotonic() - started_at)


def _log_step_failed(step_name: str, started_at: float, exc: Exception) -> None:
    logger.error(
        "step %s failed (%.2fs): %s", step_name, time.monotonic() - started_at, exc
    )
