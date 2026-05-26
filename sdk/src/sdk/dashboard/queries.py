"""
Data-access utilities for the Checkpoint SDK.

Two layers:
  1. DBOS API wrappers — list/get workflows and steps
  2. Agent events — fetch from agent_events table and enrich step records
"""

import asyncio
from datetime import UTC, datetime
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _wf_to_dict(w, *, include_output: bool = False) -> dict:
    record = {
        "workflow_id": w.workflow_id,
        "name": w.name,
        "status": w.status,
        "created_at": w.created_at,
        "updated_at": w.updated_at,
        "recovery_attempts": None,
    }
    if include_output:
        output = getattr(w, "output", None)
        record["output"] = None if output is None else str(output)
    return record


async def list_workflows(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List workflows from DBOS, newest first."""
    from dbos import DBOS

    kwargs: dict = {
        "limit": limit,
        "offset": offset,
        "sort_desc": True,
        "load_input": False,
        "load_output": False,
    }
    if status:
        kwargs["status"] = status
    results = await DBOS.list_workflows_async(**kwargs)
    return [_wf_to_dict(w) for w in results]


async def get_workflow(workflow_uuid: str) -> Optional[dict]:
    """Return a single workflow by ID, or None if not found."""
    from dbos import DBOS

    results = await DBOS.list_workflows_async(
        workflow_ids=[workflow_uuid], load_input=False, load_output=True
    )
    return _wf_to_dict(results[0], include_output=True) if results else None


async def get_steps(workflow_uuid: str) -> list[dict]:
    """Return all step records for a workflow."""
    from dbos import DBOS

    return await DBOS.list_workflow_steps_async(workflow_uuid)


def _to_dashboard_value(value):
    """Convert DBOS-native Python values into JSON-safe dashboard payloads."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_dashboard_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dashboard_value(item) for item in value]
    if isinstance(value, set):
        return [_to_dashboard_value(item) for item in sorted(value, key=repr)]
    return str(value)


def _epoch_ms_to_iso8601(epoch_ms: int | None) -> str | None:
    """Convert epoch milliseconds into an ISO-8601 UTC timestamp."""
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).isoformat().replace(
        "+00:00", "Z"
    )


def fetch_agent_events(workflow_id: str, db_url: str) -> list[dict]:
    """Return all agent_events rows for a workflow, ordered by capture time."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT span_id, step_id, event_type,
                       model, tokens_in, tokens_out, provider_response_id, agent_name,
                       llm_input, llm_output,
                       tool_name, tool_args, tool_result,
                       from_agent, to_agent, captured_at
                FROM agent_events
                WHERE workflow_id = %s
                ORDER BY captured_at, id
                """,
                (workflow_id,),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def fetch_agent_events_async(workflow_id: str, db_url: str) -> list[dict]:
    """Return workflow agent events without blocking the FastAPI event loop."""
    return await asyncio.to_thread(fetch_agent_events, workflow_id, db_url)


async def fetch_agent_events_for_dashboard(workflow_id: str, db_url: str) -> list[dict]:
    """Best-effort dashboard read; DBOS workflow/step data should still render on failure."""
    try:
        return await fetch_agent_events_async(workflow_id, db_url)
    except Exception:
        logger.exception("Failed to fetch agent_events for workflow %s", workflow_id)
        return []


def build_step_records(
    steps: list[dict],
    agent_events: list[dict] | None = None,
) -> list[dict]:
    """
    Shape DBOS step records for dashboard consumption.

    When agent_events are provided, enrich each step with LLM and tool data:
      - llm_response events are joined to steps by step_id
      - tool_call events are joined to steps by step_id
    DBOS-native step metadata is always preserved when present:
      - output from DBOS operation_outputs
    Falls back to DBOS-only shape when agent_events is None or empty.
    """
    llm_by_step: dict[int, dict] = {}
    tool_by_step: dict[int, dict] = {}
    unmatched_tools: dict[str, list[dict]] = {}
    if agent_events:
        for event in agent_events:
            sid = event.get("step_id")
            etype = event.get("event_type")
            if etype == "llm_response":
                if sid is not None and sid not in llm_by_step:
                    llm_by_step[sid] = event
            elif etype == "tool_call":
                if sid is not None and sid not in tool_by_step:
                    tool_by_step[sid] = event
                elif sid is None:
                    tool_name = event.get("tool_name")
                    if tool_name:
                        unmatched_tools.setdefault(tool_name, []).append(event)

    candidate_steps_by_name: dict[str, list[int]] = {}
    for step in steps:
        step_id = step.get("function_id")
        fn_name = step.get("function_name")
        if step_id is not None and fn_name and step_id not in tool_by_step:
            candidate_steps_by_name.setdefault(fn_name, []).append(step_id)

    for tool_name, events in unmatched_tools.items():
        candidates = candidate_steps_by_name.get(tool_name, [])
        if len(events) == 1 and len(candidates) == 1:
            tool_by_step[candidates[0]] = events[0]

    records = []
    for step in steps:
        step_id = step.get("function_id")
        fn_name = step.get("function_name")
        started_at_epoch_ms = step.get("started_at_epoch_ms")
        completed_at_epoch_ms = step.get("completed_at_epoch_ms")
        duration_ms = None
        if started_at_epoch_ms is not None and completed_at_epoch_ms is not None:
            duration_ms = completed_at_epoch_ms - started_at_epoch_ms

        llm = llm_by_step.get(step_id, {})
        tool = tool_by_step.get(step_id, {})
        event = llm if llm else tool
        fallback_captured_at = _epoch_ms_to_iso8601(
            completed_at_epoch_ms if completed_at_epoch_ms is not None else started_at_epoch_ms
        )
        event_type = "step"
        if llm:
            event_type = "llm_response"
        elif tool:
            event_type = "tool_call"

        records.append(
            {
                "step_id": step_id,
                "function_name": fn_name,
                "event_type": event_type,
                "status": "SUCCESS" if step.get("error") is None else "ERROR",
                "duration_ms": duration_ms,
                "started_at_epoch_ms": started_at_epoch_ms,
                "completed_at_epoch_ms": completed_at_epoch_ms,
                "step_output": _to_dashboard_value(step.get("output")),
                "llm_model": llm.get("model"),
                "tokens_in": llm.get("tokens_in"),
                "tokens_out": llm.get("tokens_out"),
                "agent_name": event.get("agent_name"),
                "llm_input": llm.get("llm_input"),
                "llm_output": llm.get("llm_output"),
                "tool_name": tool.get("tool_name") or fn_name,
                "tool_args": tool.get("tool_args"),
                "tool_result": tool.get("tool_result"),
                "captured_at": event.get("captured_at") or fallback_captured_at,
            }
        )
    return records
