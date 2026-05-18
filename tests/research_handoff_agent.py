# cd playground
# uv run uvicorn tests.research_handoff_agent:app --port 8000
from __future__ import annotations

import json
import os
import signal
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from agents import Agent, function_tool, handoff
from dbos import DBOS, SetWorkflowID
from dbos._error import DBOSNonExistentWorkflowError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from sdk import agentic_runner, init as sdk_init, logger, step, workflow

load_dotenv()


APP_NAME = "research-handoff-agent"
DB_URL = os.getenv("DATABASE_URL")
CRASH_MARKER_DIR = Path("/tmp/dbos-handoff-crashes")
CRASH_REQUEST_DIR = Path("/tmp/dbos-handoff-crash-requests")
SAMPLE_MESSAGE = (
    "Prepare a deep research memo on whether midsize logistics operators should adopt "
    "AI dispatch copilots over the next 18 months. Gather source material, surface "
    "counterarguments, and end with a recommendation plus open risks."
)
HANDOFF_NOTE = (
    "DBOS durably stores workflow and step execution. The dashboard enriches that with "
    "agent events from the SDK. Handoff events are expected on successful runs, but a "
    "crash injected during handoff processing may interrupt that best-effort event."
)


def _ensure_crash_dirs() -> None:
    CRASH_MARKER_DIR.mkdir(parents=True, exist_ok=True)
    CRASH_REQUEST_DIR.mkdir(parents=True, exist_ok=True)


def _crash_marker_path(workflow_id: str) -> Path:
    return CRASH_MARKER_DIR / f"{workflow_id}.marker"


def _crash_request_path(workflow_id: str) -> Path:
    return CRASH_REQUEST_DIR / f"{workflow_id}.request"


def _request_handoff_crash(workflow_id: str) -> None:
    _ensure_crash_dirs()
    _crash_request_path(workflow_id).write_text(
        synthesis_writer.name,
        encoding="utf-8",
    )


def _crash_once_during_handoff(workflow_id: str, target_agent_name: str) -> None:
    _ensure_crash_dirs()
    marker = _crash_marker_path(workflow_id)
    request = _crash_request_path(workflow_id)
    if not request.exists() or marker.exists():
        return
    requested_target = request.read_text(encoding="utf-8").strip()
    if requested_target and requested_target != target_agent_name:
        return
    marker.write_text(target_agent_name, encoding="utf-8")
    request.unlink(missing_ok=True)
    logger.warning(
        "Simulating crash during handoff for workflow %s -> %s",
        workflow_id,
        target_agent_name,
    )
    os.kill(os.getpid(), signal.SIGTERM)


@function_tool
@step()
def search_public_sources(topic: str) -> dict[str, Any]:
    logger.info("Collecting public source pack for topic: %s", topic)
    return {
        "topic": topic,
        "sources": [
            {
                "title": "Fleet operators pilot AI dispatch copilots",
                "kind": "trade_report",
                "claim": "Dispatch copilots reduce manual scheduling load but need strong ops oversight.",
            },
            {
                "title": "Broker margin pressure and scheduling delays in regional freight",
                "kind": "industry_brief",
                "claim": "Midsize operators adopt automation when labor gaps outweigh software integration costs.",
            },
            {
                "title": "Transportation CIO benchmark survey",
                "kind": "survey",
                "claim": "Operations leaders want measurable ETA accuracy gains before scaling copilots fleet-wide.",
            },
        ],
        "open_questions": [
            "How quickly do deployment costs show up in operating margin?",
            "What operational guardrails are required before dispatch autonomy is trusted?",
        ],
    }


@function_tool
@step()
def gather_counterarguments(topic: str) -> dict[str, Any]:
    logger.info("Collecting counterarguments for topic: %s", topic)
    return {
        "topic": topic,
        "counterarguments": [
            "Dispatch copilots can amplify bad data quality if TMS integrations are incomplete.",
            "Change-management costs may exceed productivity gains for teams with low workflow standardization.",
            "Vendors often overstate short-term ROI relative to the training burden on dispatch managers.",
        ],
        "risks": [
            "False confidence in ETA predictions can trigger customer-facing service failures.",
            "Tool sprawl can create fragmented incident response when multiple copilots own adjacent workflows.",
        ],
    }


@function_tool
@step()
def assemble_evidence_brief(public_pack: str, counterarguments: str) -> dict[str, Any]:
    logger.info("Assembling evidence brief from upstream specialist outputs")
    return {
        "evidence_summary": [
            "Operators are interested in copilots when they reduce dispatcher workload without changing customer SLAs.",
            "Pilot success depends on clean workflow instrumentation, exception review, and clear human override paths.",
            "ROI is strongest when copilots improve the speed of triage rather than attempt full autonomy immediately.",
        ],
        "public_pack_excerpt": public_pack[:500],
        "counterarguments_excerpt": counterarguments[:500],
        "recommended_memo_shape": [
            "Current market signal",
            "Adoption constraints",
            "Operational safeguards",
            "Recommendation and open risks",
        ],
    }


def _handoff_callback(target_agent_name: str):
    def callback(_ctx: Any) -> None:
        workflow_id = DBOS.workflow_id
        if workflow_id:
            _crash_once_during_handoff(workflow_id, target_agent_name)

    return callback


source_collector = Agent(
    name="source_collector",
    instructions=(
        "You are the source collection specialist for long-running deep research. "
        "Gather grounded evidence using the available tools, organize it for downstream "
        "agents, and clearly separate observed evidence from open questions."
    ),
    tools=[search_public_sources, gather_counterarguments],
)

synthesis_writer = Agent(
    name="synthesis_writer",
    instructions=(
        "You are the synthesis specialist. Build a crisp research memo that cites the "
        "evidence provided by prior agents, highlights disagreements, and ends with a "
        "decision-ready recommendation plus unresolved risks."
    ),
    tools=[assemble_evidence_brief],
)

research_coordinator = Agent(
    name="research_coordinator",
    instructions=(
        "You orchestrate durable deep research across specialist agents. First hand off "
        "to the source collector to gather evidence and counterarguments. Then hand off "
        "to the synthesis writer to produce the final memo. Do not answer directly until "
        "the specialist chain has completed."
    ),
    handoffs=[
        handoff(
            source_collector,
            tool_name_override="delegate_source_collection",
            tool_description_override=(
                "Hand off to the source collection specialist for evidence gathering."
            ),
            on_handoff=_handoff_callback(source_collector.name),
        ),
        handoff(
            synthesis_writer,
            tool_name_override="delegate_synthesis",
            tool_description_override=(
                "Hand off to the synthesis specialist for memo writing."
            ),
            on_handoff=_handoff_callback(synthesis_writer.name),
        ),
    ],
)


@workflow()
async def run_agent(message: str) -> dict[str, Any]:
    result = await agentic_runner(
        starting_agent=research_coordinator,
        input=message,
    )
    return {
        "workflow_id": DBOS.workflow_id,
        "output": result.final_output,
        "note": HANDOFF_NOTE,
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    sdk_init(APP_NAME, db_url=DB_URL)
    yield


app = FastAPI(title="DBOS Research Handoff Agent", lifespan=lifespan)


class RunResponse(BaseModel):
    workflow_id: str
    status: str
    output: str | None = None
    note: str | None = None


class ResumeResponse(BaseModel):
    workflow_id: str
    status: str
    output: str | None = None
    note: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/agent/{workflow_id}", response_model=RunResponse)
async def run_agent_workflow(
    workflow_id: str,
    message: str = Query(SAMPLE_MESSAGE),
    crash_during_handoff: bool = Query(
        False,
        description=(
            "Crash the process once during the later synthesis handoff callback. The "
            "workflow should remain recoverable, but the handoff event is best-effort "
            "and may be missing."
        ),
    ),
):
    if crash_during_handoff:
        _request_handoff_crash(workflow_id)

    try:
        existing = await DBOS.retrieve_workflow_async(workflow_id)
        result = await existing.get_result()
        return RunResponse(
            workflow_id=workflow_id,
            status="reconnected",
            output=result.get("output"),
            note=result.get("note"),
        )
    except DBOSNonExistentWorkflowError:
        pass

    with SetWorkflowID(workflow_id):
        handle = await DBOS.start_workflow_async(run_agent, message)
    return RunResponse(
        workflow_id=handle.get_workflow_id(),
        status="started",
        note=HANDOFF_NOTE,
    )


@app.post("/demo/agent/{workflow_id}", response_model=RunResponse)
async def run_demo_agent_workflow(
    workflow_id: str,
    crash_during_handoff: bool = Query(
        False,
        description="Enable the one-time crash path during the later synthesis handoff.",
    ),
):
    return await run_agent_workflow(
        workflow_id=workflow_id,
        message=SAMPLE_MESSAGE,
        crash_during_handoff=crash_during_handoff,
    )


@app.post("/resume/{workflow_id}", response_model=ResumeResponse)
async def resume_workflow(workflow_id: str):
    try:
        handle = await DBOS.retrieve_workflow_async(workflow_id)
        result = await handle.get_result()
        return ResumeResponse(
            workflow_id=workflow_id,
            status="completed",
            output=result.get("output"),
            note=result.get("note"),
        )
    except DBOSNonExistentWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        logger.exception("Resume failed for workflow %s", workflow_id)
        return ResumeResponse(
            workflow_id=workflow_id,
            status="pending",
            output=json.dumps(
                {
                    "workflow_id": workflow_id,
                    "status": "pending",
                    "error": "Workflow still pending or crashed again",
                }
            ),
            note=HANDOFF_NOTE,
        )
