"""
Checkpoint dashboard backend.

Dashboard/admin API for workflow inspection and control. This service does not
import customer agent modules, list registered agents, or start workflows. It
reads DBOS workflow metadata through a lightweight DBOS client and enriches
traces from the same database used by embedded customer applications or the
optional runtime server.

## Run
  uv run uvicorn admin_control_plane.dashboard_backend:app --port 8001

## Endpoints
  GET /health
  GET /workflows?status=PENDING&limit=50
  GET /workflows/{workflow_id}
  POST /workflows/{workflow_id}/resume
  POST /workflows/{workflow_id}/cancel
"""

import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from sdk.dashboard import DashboardClient, WorkflowDetail, WorkflowSummary

load_dotenv()

DB_URL = os.environ.get("DB_URL") or os.environ.get("DBOS_SYSTEM_DATABASE_URL") or ""


@lru_cache(maxsize=1)
def get_dashboard_client() -> DashboardClient:
    if not DB_URL:
        raise RuntimeError("DB_URL or DBOS_SYSTEM_DATABASE_URL must be configured")
    return DashboardClient(db_url=DB_URL)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    if get_dashboard_client.cache_info().currsize:
        client = get_dashboard_client()
        try:
            client.destroy()
        finally:
            get_dashboard_client.cache_clear()


app = FastAPI(title="Admin Dashboard", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class WorkflowListPage(BaseModel):
    workflows: list[WorkflowSummary]
    has_more: bool


@app.get("/workflows", response_model=WorkflowListPage)
async def get_workflows(
    status: Optional[str] = Query(
        None, description="Filter by status (PENDING, SUCCESS, ERROR)"
    ),
    limit: int = Query(50, ge=1, le=1000, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """List workflows from DBOS, newest first. Paginated via limit + offset."""
    # Over-fetch by one row to detect has_more without a COUNT query.
    rows = await get_dashboard_client().list_workflows(
        status=status, limit=limit + 1, offset=offset
    )
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    workflows = [
        WorkflowSummary(
            workflow_id=r["workflow_id"],
            name=r["name"],
            status=r["status"],
            created_at=r["created_at"],
            completed_at=r["updated_at"],
            recovery_attempts=r["recovery_attempts"],
        )
        for r in rows
    ]
    return WorkflowListPage(workflows=workflows, has_more=has_more)


@app.get("/workflows/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow_detail(workflow_id: str):
    """Return workflow info, enriched step history, and raw agent events."""
    wf, step_records, agent_events = await get_dashboard_client().get_workflow_detail_data(
        workflow_id
    )
    if wf is None:
        raise HTTPException(
            status_code=404, detail=f"Workflow {workflow_id!r} not found"
        )

    return WorkflowDetail(workflow=wf, steps=step_records, events=agent_events)


@app.post("/workflows/{workflow_id}/resume")
async def resume_workflow(workflow_id: str):
    return await get_dashboard_client().resume_workflow(workflow_id)


@app.post("/workflows/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str):
    return await get_dashboard_client().cancel_workflow(workflow_id)
