from __future__ import annotations

import importlib
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from dbos import DBOS, DBOSConfig

from .decorators import (
    _registered_agents,
    get_registered_agent,
    list_registered_agents,
    logger,
)

DEFAULT_AGENT_QUEUE = "agent-runs"

_init_lock = threading.Lock()
_initialized = False
_runtime_owner_id: int | None = None
_default_runtime: "Runtime" | None = None


def _single_runtime_error() -> RuntimeError:
    return RuntimeError(
        "Only one Runtime may be started per process. "
        "Reuse the existing Runtime for AgentService and WorkerService."
    )


class Runtime:
    def __init__(
        self,
        *,
        name: str | None = None,
        db_url: str | None = None,
        conductor_key: str | None = None,
    ) -> None:
        self.name = name
        self.db_url = db_url
        self.conductor_key = conductor_key

    def start(
        self,
        *,
        listen_queues: list[str] | tuple[str, ...] | None = None,
        before_launch: Callable[[DBOSConfig], None] | None = None,
    ) -> None:
        _start_dbos_runtime(
            owner_id=id(self),
            name=self.name,
            db_url=self.db_url,
            conductor_key=self.conductor_key,
            listen_queues=listen_queues,
            before_launch=before_launch,
        )


def _get_default_runtime() -> Runtime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = Runtime()
    return _default_runtime


class AgentService:
    def __init__(
        self,
        runtime: Runtime | None = None,
        *,
        default_queue_name: str = DEFAULT_AGENT_QUEUE,
    ) -> None:
        self.runtime = runtime or _get_default_runtime()
        self.default_queue_name = default_queue_name

    async def run(self, name: str, input: str):
        self.runtime.start()
        registered_agent = get_registered_agent(name)
        return await DBOS.start_workflow_async(registered_agent.workflow, input)

    async def enqueue(
        self,
        name: str,
        input: str,
        *,
        queue_name: str | None = None,
    ):
        self.runtime.start()
        registered_agent = get_registered_agent(name)
        resolved_queue_name = queue_name or self.default_queue_name
        _ensure_queue_exists(resolved_queue_name)
        return await DBOS.enqueue_workflow_async(
            resolved_queue_name,
            registered_agent.workflow,
            input,
        )


class WorkerService:
    def __init__(
        self,
        runtime: Runtime | None = None,
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
        keep_alive: bool = True,
    ) -> None:
        if concurrency is not None and worker_concurrency is not None:
            if concurrency < worker_concurrency:
                raise ValueError(
                    "concurrency must be greater than or equal to worker_concurrency"
                )
        self.runtime = runtime or _get_default_runtime()
        self.agent_modules = list(agent_modules)
        self.queue_name = queue_name
        self.worker_concurrency = worker_concurrency
        self.concurrency = concurrency
        self.limiter = limiter
        self.priority_enabled = priority_enabled
        self.partition_queue = partition_queue
        self.polling_interval_sec = polling_interval_sec
        self.on_conflict = on_conflict
        self.keep_alive = keep_alive

    def register_queue(self) -> Any:
        self.runtime.start()
        return DBOS.register_queue(
            self.queue_name,
            worker_concurrency=self.worker_concurrency,
            concurrency=self.concurrency,
            limiter=self.limiter,
            priority_enabled=self.priority_enabled,
            partition_queue=self.partition_queue,
            polling_interval_sec=self.polling_interval_sec,
            on_conflict=self.on_conflict,
        )

    def run(self) -> None:
        if not self.agent_modules:
            raise ValueError("agent_modules must include at least one import path.")

        imported_modules = []
        for module_name in self.agent_modules:
            imported_modules.append(importlib.import_module(module_name).__name__)

        if not _registered_agents:
            raise RuntimeError(
                "No agents are registered. Check that agent_modules imports modules "
                "containing @register_agent workflows."
            )

        def configure_worker(config: DBOSConfig) -> None:
            _listen_agent_queues([self.queue_name])
            logger.info(
                "agent worker configured queue=%s worker_concurrency=%s "
                "concurrency=%s runtime=%s modules=%s registered_agents=%s",
                self.queue_name,
                self.worker_concurrency,
                self.concurrency,
                config.get("name"),
                imported_modules,
                [agent.name for agent in list_registered_agents()],
            )

        self.runtime.start(before_launch=configure_worker)

        DBOS.register_queue(
            self.queue_name,
            worker_concurrency=self.worker_concurrency,
            concurrency=self.concurrency,
            limiter=self.limiter,
            priority_enabled=self.priority_enabled,
            partition_queue=self.partition_queue,
            polling_interval_sec=self.polling_interval_sec,
            on_conflict=self.on_conflict,
        )
        logger.info("agent worker listening on queues=%s", [self.queue_name])
        if self.keep_alive:
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                logger.info("agent worker shutting down")


def _ensure_queue_exists(queue_name: str) -> Any:
    return DBOS.register_queue(queue_name, on_conflict="never_update")


def _dbos_config(
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


def _start_dbos_runtime(
    *,
    owner_id: int | None = None,
    name: str | None = None,
    db_url: str | None = None,
    conductor_key: str | None = None,
    listen_queues: list[str] | tuple[str, ...] | None = None,
    before_launch: Callable[[DBOSConfig], None] | None = None,
) -> None:
    global _initialized, _runtime_owner_id

    config = _dbos_config(
        name=name,
        db_url=db_url,
        conductor_key=conductor_key,
    )
    resolved_db = config.get("system_database_url")
    if not isinstance(resolved_db, str) or not resolved_db.strip():
        raise RuntimeError(
            "DBOS system database URL is required. Set DB_URL or "
            "DBOS_SYSTEM_DATABASE_URL."
        )

    with _init_lock:
        if _initialized:
            if owner_id is not None and owner_id != _runtime_owner_id:
                raise _single_runtime_error()
            if before_launch is not None or listen_queues is not None:
                raise RuntimeError(
                    "Runtime is already started; queue listeners must be configured "
                    "before DBOS.launch()."
                )
            return

        if _runtime_owner_id is not None and owner_id is not None and owner_id != _runtime_owner_id:
            raise _single_runtime_error()
        _runtime_owner_id = owner_id

        DBOS(config=config)
        if listen_queues is not None:
            _listen_agent_queues(listen_queues)
        if before_launch is not None:
            before_launch(config)
        DBOS.launch()
        _initialized = True

        if isinstance(resolved_db, str) and resolved_db.startswith("postgresql"):
            from .tracing import register_checkpoint_tracing_processor

            register_checkpoint_tracing_processor(resolved_db)


def _listen_agent_queues(
    queue_names: list[str] | tuple[str, ...] = (DEFAULT_AGENT_QUEUE,),
) -> None:
    DBOS.listen_queues(list(queue_names))
