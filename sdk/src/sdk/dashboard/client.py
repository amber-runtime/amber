from __future__ import annotations

from typing import Optional

from dbos import DBOSClient

from .queries import build_step_records, fetch_agent_events_for_dashboard


def _wf_to_dict(workflow, *, include_output: bool = False) -> dict:
    record = {
        "workflow_id": workflow.workflow_id,
        "name": workflow.name,
        "status": workflow.status,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
        "recovery_attempts": getattr(workflow, "recovery_attempts", None),
    }
    if include_output:
        output = getattr(workflow, "output", None)
        record["output"] = None if output is None else str(output)
    return record


class DashboardClient:
    def __init__(
        self,
        *,
        db_url: str,
        dbos_system_schema: str = "dbos",
    ) -> None:
        self._db_url = db_url
        self._client = DBOSClient(
            system_database_url=db_url,
            dbos_system_schema=dbos_system_schema,
        )

    def destroy(self) -> None:
        self._client.destroy()

    async def list_workflows(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        kwargs: dict = {
            "limit": limit,
            "offset": offset,
            "sort_desc": True,
            "load_input": False,
            "load_output": False,
        }
        if status:
            kwargs["status"] = status
        workflows = await self._client.list_workflows_async(**kwargs)
        return [_wf_to_dict(workflow) for workflow in workflows]

    async def get_workflow(self, workflow_id: str) -> Optional[dict]:
        workflows = await self._client.list_workflows_async(
            workflow_ids=[workflow_id],
            load_input=False,
            load_output=True,
        )
        return _wf_to_dict(workflows[0], include_output=True) if workflows else None

    async def get_steps(self, workflow_id: str) -> list[dict]:
        return await self._client.list_workflow_steps_async(workflow_id)

    async def get_workflow_detail_data(
        self, workflow_id: str
    ) -> tuple[dict | None, list[dict], list[dict]]:
        workflow = await self.get_workflow(workflow_id)
        if workflow is None:
            return None, [], []

        steps = await self.get_steps(workflow_id)
        agent_events = await fetch_agent_events_for_dashboard(workflow_id, self._db_url)
        step_records = build_step_records(steps, agent_events)
        return workflow, step_records, agent_events

    async def resume_workflow(
        self,
        workflow_id: str,
        *,
        queue_name: str | None = None,
    ) -> dict[str, str | bool]:
        await self._client.resume_workflow_async(workflow_id, queue_name=queue_name)
        return {"workflow_id": workflow_id, "action": "resume", "accepted": True}

    async def cancel_workflow(self, workflow_id: str) -> dict[str, str | bool]:
        await self._client.cancel_workflow_async(workflow_id)
        return {"workflow_id": workflow_id, "action": "cancel", "accepted": True}
