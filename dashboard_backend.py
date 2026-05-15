"""
FastAPI dashboard backend — exposes DBOS + Phoenix JOIN logic via HTTP.
Run: uv run uvicorn dashboard_backend:app --reload
"""
import json
import sqlite3
import sys
import textwrap
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# mordec_ai_agents has no __init__.py — add its directory to sys.path
sys.path.insert(0, str(Path(__file__).parent / "mordec_ai_agents"))
from agent import run_agent  # noqa: E402

DB_PATH = "research_assistant.sqlite"
PHOENIX_BASE = "http://localhost:6006"
PHOENIX_PROJECT = "default"
PHOENIX_OTLP = "http://localhost:6006/v1/traces"


# ── Pydantic models ───────────────────────────────────────────────────────────

class WorkflowSummary(BaseModel):
    workflow_uuid: str
    name: str
    status: str
    created_at: Optional[int]
    completed_at: Optional[int]
    recovery_attempts: Optional[int]


class StepRecord(BaseModel):
    step_id: int
    function_name: str
    status: str
    duration_ms: Optional[int]
    llm_model: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    tool_name: Optional[str]
    tool_args: Optional[str]


class WorkflowDetail(BaseModel):
    workflow: dict[str, Any]
    steps: list[StepRecord]


class RunAgentRequest(BaseModel):
    topic: str
    workflow_uuid: Optional[str] = None


class RunAgentResponse(BaseModel):
    workflow_uuid: str
    topic: str
    output: str


# ── DBOS data access ──────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def list_workflows_db(status: Optional[str] = None, limit: int = 50) -> list[dict]:
    con = _db()
    cur = con.cursor()
    if status:
        cur.execute(
            "SELECT workflow_uuid, name, status, created_at, updated_at,"
            " recovery_attempts FROM workflow_status"
            " WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
    else:
        cur.execute(
            "SELECT workflow_uuid, name, status, created_at, updated_at,"
            " recovery_attempts FROM workflow_status"
            " ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def get_workflow_db(workflow_uuid: str) -> Optional[dict]:
    con = _db()
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM workflow_status WHERE workflow_uuid = ?", (workflow_uuid,)
    )
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None


def get_steps_db(workflow_uuid: str) -> list[dict]:
    con = _db()
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM operation_outputs WHERE workflow_uuid = ? ORDER BY function_id",
        (workflow_uuid,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


# ── Phoenix data access ───────────────────────────────────────────────────────

def _phoenix_get(path: str) -> dict:
    with urllib.request.urlopen(f"{PHOENIX_BASE}{path}") as r:
        return json.loads(r.read())


def fetch_phoenix_spans(workflow_uuid: str, workflow_name: str) -> list[dict]:
    """Return all spans in the trace for this workflow. Empty list on any error."""
    try:
        attr = urllib.parse.quote(f"operationUUID:{workflow_uuid}")
        resp = _phoenix_get(
            f"/v1/projects/{PHOENIX_PROJECT}/spans?attribute={attr}&limit=50"
        )

        trace_id = next(
            (s["context"]["trace_id"] for s in resp["data"] if s["name"] == workflow_name),
            None,
        )
        if not trace_id:
            return []

        all_resp = _phoenix_get(
            f"/v1/projects/{PHOENIX_PROJECT}/spans?trace_id={trace_id}&limit=200"
        )
        return all_resp["data"]
    except Exception:
        return []


# ── JOIN logic ────────────────────────────────────────────────────────────────

def build_step_records(
    ops: list[dict], all_spans: list[dict], workflow_name: str
) -> list[dict]:
    """
    JOIN operation_outputs rows with Phoenix spans on function_id == dbos.step_id.
    Returns dicts matching the StepRecord schema. Phoenix fields are None when
    spans are unavailable.
    """
    by_id: dict[str, dict] = {s["context"]["span_id"]: s for s in all_spans}
    children: dict[Optional[str], list[dict]] = {}
    for s in all_spans:
        children.setdefault(s.get("parent_id"), []).append(s)

    step_spans_by_id: dict[int, dict] = {
        int(s["attributes"]["dbos.step_id"]): s
        for s in all_spans
        if s["span_kind"] == "UNKNOWN"
        and s["name"] != workflow_name
        and "dbos.step_id" in s.get("attributes", {})
    }

    records = []
    for op in ops:
        step_span = step_spans_by_id.get(op["function_id"])
        tool_span = by_id.get(step_span.get("parent_id")) if step_span else None

        llm_span = None
        if tool_span:
            siblings = children.get(tool_span.get("parent_id"), [])
            llm_span = next((s for s in siblings if s["span_kind"] == "LLM"), None)

        duration_ms = None
        if op.get("started_at_epoch_ms") and op.get("completed_at_epoch_ms"):
            duration_ms = op["completed_at_epoch_ms"] - op["started_at_epoch_ms"]

        tool_attrs = tool_span["attributes"] if tool_span else {}
        llm_attrs = llm_span["attributes"] if llm_span else {}

        raw_args = tool_attrs.get("input.value", "")
        try:
            short_args: Optional[str] = textwrap.shorten(
                json.dumps(json.loads(raw_args)), width=80
            )
        except (json.JSONDecodeError, TypeError):
            short_args = textwrap.shorten(str(raw_args), width=80) or None

        tok_in = llm_attrs.get("llm.token_count.prompt")
        tok_out = llm_attrs.get("llm.token_count.completion")

        records.append(
            {
                "step_id":       op["function_id"],
                "function_name": op["function_name"],
                "status":        "SUCCESS" if op.get("error") is None else "ERROR",
                "duration_ms":   duration_ms,
                "llm_model":     llm_attrs.get("llm.model_name"),
                "tokens_in":     int(tok_in) if tok_in is not None else None,
                "tokens_out":    int(tok_out) if tok_out is not None else None,
                "tool_name":     tool_attrs.get("tool.name"),
                "tool_args":     short_args,
            }
        )
    return records


# ── App startup: OTel + DBOS initialized once ────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    from dbos import DBOS, DBOSConfig
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

    tp = TracerProvider()
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=PHOENIX_OTLP)))
    trace.set_tracer_provider(tp)
    OpenAIAgentsInstrumentor().instrument(tracer_provider=tp)

    config: DBOSConfig = {
        "name": "research-assistant",
        "enable_otlp": True,
    }
    DBOS(config=config)
    DBOS.launch()

    yield

    tp.shutdown()


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Checkpoint Dashboard", version="0.1.0", lifespan=lifespan)


@app.get("/workflows", response_model=list[WorkflowSummary])
def get_workflows(
    status: Optional[str] = Query(
        None, description="Filter by workflow status (PENDING, SUCCESS, ERROR)"
    ),
    limit: int = Query(50, ge=1, le=1000, description="Maximum results to return"),
):
    """List workflows from DBOS, newest first."""
    rows = list_workflows_db(status=status, limit=limit)
    return [
        WorkflowSummary(
            workflow_uuid=r["workflow_uuid"],
            name=r["name"],
            status=r["status"],
            created_at=r["created_at"],
            completed_at=r["updated_at"],
            recovery_attempts=r["recovery_attempts"],
        )
        for r in rows
    ]


@app.get("/workflows/{workflow_id}", response_model=WorkflowDetail)
def get_workflow_detail(workflow_id: str):
    """Return full workflow info + unified per-step JOIN of DBOS + Phoenix data."""
    wf = get_workflow_db(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")

    ops = get_steps_db(workflow_id)
    all_spans = fetch_phoenix_spans(workflow_id, wf["name"])
    steps = build_step_records(ops, all_spans, wf["name"])

    return WorkflowDetail(workflow=wf, steps=steps)


@app.post("/run-agent", response_model=RunAgentResponse)
async def trigger_run_agent(body: RunAgentRequest):
    """Start or reconnect to a research-assistant workflow.

    If workflow_uuid is provided, reconnects to that existing run.
    If omitted, starts a new workflow with a DBOS-generated UUID.
    """
    from dbos import DBOS
    from dbos._error import DBOSNonExistentWorkflowError

    if body.workflow_uuid:
        try:
            handle = await DBOS.retrieve_workflow_async(body.workflow_uuid)
        except DBOSNonExistentWorkflowError:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow {body.workflow_uuid!r} not found in DBOS",
            )
    else:
        handle = await DBOS.start_workflow_async(run_agent, body.topic)

    output = await handle.get_result()
    return RunAgentResponse(
        workflow_uuid=handle.workflow_id,
        topic=body.topic,
        output=output,
    )


class ResumeWorkflowRequest(BaseModel):
    workflow_uuid: str


class ResumeWorkflowResponse(BaseModel):
    workflow_uuid: str
    status: str
    output: Optional[str]


@app.post("/resume-workflow", response_model=ResumeWorkflowResponse)
async def resume_workflow(body: ResumeWorkflowRequest):
    """Reconnect to an existing workflow by UUID and return its result.

    Returns 404 if the UUID is not found, 400 if the workflow already
    completed (SUCCESS or ERROR) and cannot be meaningfully resumed.
    Blocks until the workflow completes if it is still running.
    """
    from dbos import DBOS
    from dbos._error import DBOSNonExistentWorkflowError

    wf = get_workflow_db(body.workflow_uuid)
    if wf is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow {body.workflow_uuid!r} not found",
        )
    if wf["status"] in ("SUCCESS", "ERROR"):
        raise HTTPException(
            status_code=400,
            detail=f"Workflow {body.workflow_uuid!r} has already finished with status {wf['status']!r}",
        )

    try:
        handle = await DBOS.retrieve_workflow_async(body.workflow_uuid)
    except DBOSNonExistentWorkflowError:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow {body.workflow_uuid!r} not found in DBOS",
        )

    output = await handle.get_result()
    wf = get_workflow_db(body.workflow_uuid)
    return ResumeWorkflowResponse(
        workflow_uuid=body.workflow_uuid,
        status=wf["status"] if wf else "UNKNOWN",
        output=str(output) if output is not None else None,
    )
