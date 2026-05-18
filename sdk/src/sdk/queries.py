"""
Data-access utilities for the Checkpoint SDK.

Phase 1 keeps the dashboard backed by DBOS workflow and step records only.
Agent-specific observability is intentionally deferred until the durable event
log lands in a later phase.
"""

from typing import Optional


# ── DBOS API wrappers ─────────────────────────────────────────────────────────

def _wf_to_dict(w) -> dict:
    return {
        "workflow_id":       w.workflow_id,
        "name":              w.name,
        "status":            w.status,
        "created_at":        w.created_at,
        "updated_at":        w.updated_at,
        "recovery_attempts": None,  # not exposed in WorkflowStatus
    }


def list_workflows(status: Optional[str] = None, limit: int = 50) -> list[dict]:
    """List workflows from DBOS, newest first."""
    from dbos import DBOS
    kwargs: dict = {"limit": limit, "sort_desc": True, "load_input": False, "load_output": False}
    if status:
        kwargs["status"] = status
    results = DBOS.list_workflows(**kwargs)
    return [_wf_to_dict(w) for w in results]


def get_workflow(workflow_uuid: str) -> Optional[dict]:
    """Return a single workflow by ID, or None if not found."""
    from dbos import DBOS
    results = DBOS.list_workflows(
        workflow_ids=[workflow_uuid], load_input=False, load_output=False
    )
    return _wf_to_dict(results[0]) if results else None


def get_steps(workflow_uuid: str) -> list[dict]:
    """Return all step records for a workflow."""
    from dbos import DBOS
    return DBOS.list_workflow_steps(workflow_uuid)


# ── Step shaping ──────────────────────────────────────────────────────────────

def build_step_records(steps: list[dict]) -> list[dict]:
    """Shape DBOS step records for dashboard consumption."""
    records = []
    for step in steps:
        duration_ms = None
        if step.get("started_at_epoch_ms") and step.get("completed_at_epoch_ms"):
            duration_ms = step["completed_at_epoch_ms"] - step["started_at_epoch_ms"]

        records.append({
            "step_id":       step["function_id"],
            "function_name": step["function_name"],
            "status":        "SUCCESS" if step.get("error") is None else "ERROR",
            "duration_ms":   duration_ms,
        })
    return records
