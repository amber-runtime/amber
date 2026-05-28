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
  GET /pricing
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Optional

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from sdk.dashboard import DashboardClient, WorkflowDetail, WorkflowSummary

load_dotenv()

logger = logging.getLogger(__name__)

DB_URL = os.environ.get("DB_URL") or os.environ.get("DBOS_SYSTEM_DATABASE_URL") or ""

LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
PRICING_FRESH_SQL = (
    "SELECT 1 FROM model_pricing "
    "WHERE last_synced_at > NOW() - INTERVAL '24 hours' LIMIT 1"
)
ALLOWED_PROVIDERS = {"openai", "anthropic"}
EXCLUDED_MODES = {
    "image_generation",
    "embedding",
    "audio_transcription",
    "audio_speech",
    "moderation",
    "rerank",
    "search",
}

_PRICING_DDL = """
CREATE TABLE IF NOT EXISTS model_pricing (
    model_name              TEXT             PRIMARY KEY,
    input_cost_per_token    DOUBLE PRECISION NOT NULL,
    output_cost_per_token   DOUBLE PRECISION NOT NULL,
    cache_read_cost         DOUBLE PRECISION,
    cache_creation_cost     DOUBLE PRECISION,
    last_synced_at          TIMESTAMPTZ      NOT NULL,
    manual_override         BOOLEAN          NOT NULL DEFAULT FALSE
);
"""


@lru_cache(maxsize=1)
def get_dashboard_client() -> DashboardClient:
    if not DB_URL:
        raise RuntimeError("DB_URL or DBOS_SYSTEM_DATABASE_URL must be configured")
    return DashboardClient(db_url=DB_URL)


def ensure_pricing_table(db_url: str) -> None:
    """Create model_pricing table if it does not exist. Called once at init."""
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(_PRICING_DDL)
        conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if DB_URL:
        await asyncio.to_thread(ensure_pricing_table, DB_URL)
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


class QueuedWorkflowSummary(BaseModel):
    workflow_id: str
    name: str
    status: str
    created_at: Optional[int]
    queue_name: Optional[str]
    recovery_attempts: Optional[int]


class QueuedWorkflowListPage(BaseModel):
    workflows: list[QueuedWorkflowSummary]
    has_more: bool


class ForkWorkflowRequest(BaseModel):
    start_step: int


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


@app.get("/queued-workflows", response_model=QueuedWorkflowListPage)
async def get_queued_workflows(
    queue_name: Optional[str] = Query(None, description="Filter by specific queue name"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List workflows associated with a queue, newest first. Paginated via limit + offset."""
    rows = await get_dashboard_client().list_queued_workflows(
        queue_name=queue_name, limit=limit + 1, offset=offset
    )
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    workflows = [
        QueuedWorkflowSummary(
            workflow_id=r["workflow_id"],
            name=r["name"],
            status=r["status"],
            created_at=r["created_at"],
            queue_name=r.get("queue_name"),
            recovery_attempts=r.get("recovery_attempts"),
        )
        for r in rows
    ]
    return QueuedWorkflowListPage(workflows=workflows, has_more=has_more)


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
    client = get_dashboard_client()
    workflow = await client.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(
            status_code=404, detail=f"Workflow {workflow_id!r} not found"
        )
    return await client.resume_workflow(
        workflow_id, queue_name=workflow.get("queue_name")
    )


@app.post("/workflows/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str):
    return await get_dashboard_client().cancel_workflow(workflow_id)


@app.post("/workflows/{workflow_id}/fork")
async def fork_workflow(workflow_id: str, request: ForkWorkflowRequest):
    if request.start_step < 1:
        raise HTTPException(status_code=422, detail="start_step must be >= 1")
    return await get_dashboard_client().fork_workflow(workflow_id, request.start_step)


def _pricing_is_fresh(db_url: str) -> bool:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(PRICING_FRESH_SQL)
            return cur.fetchone() is not None
    finally:
        conn.close()


def _filter_litellm(payload: Any) -> list[dict[str, Any]]:
    """Extract rows we care about from the LiteLLM JSON blob."""
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for name, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("litellm_provider") not in ALLOWED_PROVIDERS:
            continue
        if entry.get("mode") in EXCLUDED_MODES:
            continue
        input_cost = entry.get("input_cost_per_token")
        output_cost = entry.get("output_cost_per_token")
        if not isinstance(input_cost, (int, float)) or not isinstance(output_cost, (int, float)):
            continue
        rows.append(
            {
                "model_name": name,
                "input_cost_per_token": float(input_cost),
                "output_cost_per_token": float(output_cost),
                "cache_read_cost": _opt_float(entry.get("cache_read_input_token_cost")),
                "cache_creation_cost": _opt_float(entry.get("cache_creation_input_token_cost")),
            }
        )
    return rows


def _opt_float(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) else None


def _upsert_pricing(db_url: str, rows: list[dict[str, Any]]) -> None:
    """Upsert filtered rows; rows where manual_override = TRUE are left alone."""
    if not rows:
        return
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO model_pricing (
                    model_name, input_cost_per_token, output_cost_per_token,
                    cache_read_cost, cache_creation_cost, last_synced_at
                ) VALUES %s
                ON CONFLICT (model_name) DO UPDATE SET
                    input_cost_per_token  = EXCLUDED.input_cost_per_token,
                    output_cost_per_token = EXCLUDED.output_cost_per_token,
                    cache_read_cost       = EXCLUDED.cache_read_cost,
                    cache_creation_cost   = EXCLUDED.cache_creation_cost,
                    last_synced_at        = EXCLUDED.last_synced_at
                WHERE model_pricing.manual_override = FALSE
                """,
                [
                    (
                        r["model_name"],
                        r["input_cost_per_token"],
                        r["output_cost_per_token"],
                        r["cache_read_cost"],
                        r["cache_creation_cost"],
                    )
                    for r in rows
                ],
                template="(%s, %s, %s, %s, %s, NOW())",
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _read_pricing(db_url: str) -> tuple[dict[str, dict[str, Optional[float]]], Optional[int]]:
    """Read the full pricing table and the most-recent non-override sync time."""
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT model_name, input_cost_per_token, output_cost_per_token,
                       cache_read_cost, cache_creation_cost
                FROM model_pricing
                """
            )
            models: dict[str, dict[str, Optional[float]]] = {}
            for name, inp, outp, cr, cc in cur.fetchall():
                models[name] = {
                    "input": float(inp),
                    "output": float(outp),
                    "cache_read": float(cr) if cr is not None else None,
                    "cache_creation": float(cc) if cc is not None else None,
                }

            cur.execute(
                """
                SELECT EXTRACT(EPOCH FROM MAX(last_synced_at)) * 1000
                FROM model_pricing
                WHERE manual_override = FALSE
                """
            )
            row = cur.fetchone()
            synced_at = int(row[0]) if row and row[0] is not None else None
            return models, synced_at
    finally:
        conn.close()


async def _fetch_litellm() -> Any:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(LITELLM_PRICING_URL)
        resp.raise_for_status()
        return resp.json()


@app.get("/pricing")
async def get_pricing() -> dict[str, Any]:
    if not DB_URL:
        raise HTTPException(status_code=500, detail="DB_URL not configured")

    fresh = await asyncio.to_thread(_pricing_is_fresh, DB_URL)

    if not fresh:
        try:
            payload = await _fetch_litellm()
            rows = _filter_litellm(payload)
            await asyncio.to_thread(_upsert_pricing, DB_URL, rows)
        except Exception as exc:
            logger.warning("pricing sync failed: %s", exc)
            models, synced_at = await asyncio.to_thread(_read_pricing, DB_URL)
            response: dict[str, Any] = {"models": models, "synced_at": synced_at}
            if not models:
                response["error"] = f"fetch failed: {exc}"
            return response

    models, synced_at = await asyncio.to_thread(_read_pricing, DB_URL)
    return {"models": models, "synced_at": synced_at}
