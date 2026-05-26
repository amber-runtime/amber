import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from dbos import DBOS, DBOSConfig
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .queries import (
    build_step_records,
    fetch_agent_events_for_dashboard,
    get_steps,
    get_workflow,
    list_workflows,
)


def _resolve_dbos_config(
    name: str,
) -> tuple[DBOSConfig, str | None]:
    resolved_db = (
        os.environ.get("DB_URL")
        or os.environ.get("DBOS_SYSTEM_DATABASE_URL")
        or os.environ.get("CHECKPOINT_DB_URL")
    )
    resolved_conductor_key = os.environ.get("DBOS_CONDUCTOR_KEY")

    config: DBOSConfig = {
        "name": name,
        "system_database_url": resolved_db,
    }
    if resolved_conductor_key is not None:
        config["conductor_key"] = resolved_conductor_key

    return config, resolved_db


def _ensure_dbos_started(
    name: str,
) -> str | None:
    config, resolved_db = _resolve_dbos_config(name)
    DBOS(config=config)
    DBOS.launch()

    if resolved_db and resolved_db.startswith("postgresql"):
        from .tracing import register_checkpoint_tracing_processor

        register_checkpoint_tracing_processor(resolved_db)

    return resolved_db


def create_app(
    name: str,
    workflow: Callable[..., Any],
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_db = _ensure_dbos_started(name=name)
        app.state.db_url = resolved_db or ""
        yield

    app = FastAPI(title=name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.workflow = workflow
    app.state.db_url = ""  # placeholder; replaced in lifespan once DBOS resolves db_url

    class RunRequest(BaseModel):
        input: str = Field(
            ...,
            description="Workflow input string, such as a research topic or user message.",
            examples=[
                "Research the history of container orchestration",
                "Plan a day in San Francisco based on weather and air quality",
            ],
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/workflows")
    async def start_workflow(req: RunRequest) -> dict[str, str]:
        handle = await DBOS.start_workflow_async(app.state.workflow, req.input)
        return {"workflow_id": handle.workflow_id}

    @app.get("/workflows")
    async def get_workflows_route(
        status: str | None = Query(None, description="Filter: PENDING, SUCCESS, ERROR"),
        limit: int = Query(50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        return await list_workflows(status=status, limit=limit)

    @app.get("/workflows/{workflow_id}")
    async def get_workflow_detail(workflow_id: str) -> dict[str, Any]:
        workflow_record = await get_workflow(workflow_id)
        if workflow_record is None:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow {workflow_id!r} not found",
            )

        steps = await get_steps(workflow_id)
        agent_events = []
        if app.state.db_url:
            agent_events = await fetch_agent_events_for_dashboard(
                workflow_id,
                app.state.db_url,
            )
        step_records = build_step_records(steps, agent_events)
        return {
            "workflow": workflow_record,
            "steps": step_records,
            "events": agent_events,
        }

    @app.post("/workflows/{workflow_id}/resume")
    def resume_workflow(workflow_id: str) -> dict[str, str]:
        DBOS.resume_workflow(workflow_id)
        return {"workflow_id": workflow_id, "status": "queued"}

    return app


def serve(
    name: str,
    workflow: Callable[..., Any],
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
) -> None:
    import uvicorn

    app = create_app(name=name, workflow=workflow)
    uvicorn.run(app, host=host, port=port, reload=reload)
