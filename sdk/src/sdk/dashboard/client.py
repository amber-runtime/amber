from __future__ import annotations

from typing import Optional

from dbos import DBOSClient

from .queries import build_step_records, fetch_agent_events_for_dashboard


def _wf_to_dict(
    workflow,
    *,
    include_output: bool = False,
    include_queue: bool = False,
) -> dict:
    record = {
        "workflow_id": workflow.workflow_id,
        "name": workflow.name,
        "status": workflow.status,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
        "recovery_attempts": getattr(workflow, "recovery_attempts", None),
        "forked_from": getattr(workflow, "forked_from", None),
    }
    if include_output:
        output = getattr(workflow, "output", None)
        record["output"] = None if output is None else str(output)
    if include_queue:
        record["queue_name"] = getattr(workflow, "queue_name", None)
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

    async def list_queued_workflows(
        self,
        *,
        queue_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        kwargs: dict = {
            "limit": limit,
            "offset": offset,
            "sort_desc": True,
            "load_input": False,
            "load_output": False,
            "queues_only": True,
        }
        if queue_name:
            kwargs["queue_name"] = queue_name
        workflows = await self._client.list_workflows_async(**kwargs)
        result = []
        for workflow in workflows:
            d = _wf_to_dict(workflow, include_queue=True)
            result.append(d)
        return result

    async def list_queue_workflows(
        self,
        *,
        queue_name: Optional[str] = None,
        start_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_desc: bool = False,
    ) -> list[dict]:
        kwargs: dict = {
            "limit": limit,
            "offset": offset,
            "sort_desc": sort_desc,
            "load_input": False,
            "load_output": False,
        }
        if queue_name:
            kwargs["queue_name"] = queue_name
        if start_time:
            kwargs["start_time"] = start_time
        workflows = await self._client.list_workflows_async(**kwargs)
        return [_wf_to_dict(workflow, include_queue=True) for workflow in workflows]

    async def get_workflow(self, workflow_id: str) -> Optional[dict]:
        workflows = await self._client.list_workflows_async(
            workflow_ids=[workflow_id],
            load_input=False,
            load_output=True,
        )
        if not workflows:
            return None
        return _wf_to_dict(
            workflows[0], include_output=True, include_queue=True
        )

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
        step_records = build_step_records(steps, agent_events, workflow)
        return workflow, step_records, agent_events

    async def resume_workflow(
        self,
        workflow_id: str,
        *,
        queue_name: str | None = None,
    ) -> dict[str, str | bool]:
        await self._client.resume_workflow_async(workflow_id, queue_name=queue_name)
        return {"workflow_id": workflow_id, "action": "resume", "accepted": True}

    async def delete_workflows(self, workflow_ids: list[str]) -> dict:
        await self._client.delete_workflows_async(workflow_ids)
        return {"deleted": len(workflow_ids), "action": "delete", "accepted": True}

    async def cancel_workflow(self, workflow_id: str) -> dict[str, str | bool]:
        await self._client.cancel_workflow_async(workflow_id)
        return {"workflow_id": workflow_id, "action": "cancel", "accepted": True}

    async def fork_workflow(
        self,
        workflow_id: str,
        start_step: int,
        *,
        queue_name: str | None = None,
    ) -> dict[str, str | int | bool]:
        handle = await self._client.fork_workflow_async(
            workflow_id,
            start_step,
            queue_name=queue_name,
        )
        return {
            "workflow_id": workflow_id,
            "forked_workflow_id": handle.get_workflow_id(),
            "start_step": start_step,
            "action": "fork",
            "accepted": True,
        }
