import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = ROOT / "sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from sdk.dashboard import DashboardClient  # noqa: E402


class DashboardClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_destroy_forwards_to_dbos_client(self):
        client = DashboardClient.__new__(DashboardClient)
        client._client = mock.Mock()

        client.destroy()

        client._client.destroy.assert_called_once_with()

    async def test_list_workflows_forwards_expected_flags(self):
        client = DashboardClient.__new__(DashboardClient)
        client._db_url = "postgresql://db"
        client._client = mock.Mock()
        client._client.list_workflows_async = mock.AsyncMock(
            return_value=[
                SimpleNamespace(
                    workflow_id="wf-1",
                    name="agent",
                    status="SUCCESS",
                    created_at=1,
                    updated_at=2,
                )
            ]
        )

        rows = await client.list_workflows(status="SUCCESS", limit=10)

        self.assertEqual(rows[0]["workflow_id"], "wf-1")
        client._client.list_workflows_async.assert_awaited_once_with(
            limit=10,
            sort_desc=True,
            load_input=False,
            load_output=False,
            status="SUCCESS",
        )

    async def test_get_workflow_includes_output(self):
        client = DashboardClient.__new__(DashboardClient)
        client._db_url = "postgresql://db"
        client._client = mock.Mock()
        client._client.list_workflows_async = mock.AsyncMock(
            return_value=[
                SimpleNamespace(
                    workflow_id="wf-1",
                    name="agent",
                    status="SUCCESS",
                    created_at=1,
                    updated_at=2,
                    output={"done": True},
                )
            ]
        )

        workflow = await client.get_workflow("wf-1")

        self.assertEqual(workflow["output"], "{'done': True}")
        client._client.list_workflows_async.assert_awaited_once_with(
            workflow_ids=["wf-1"],
            load_input=False,
            load_output=True,
        )

    async def test_get_workflow_detail_data_enriches_steps(self):
        client = DashboardClient.__new__(DashboardClient)
        client._db_url = "postgresql://db"
        client.get_workflow = mock.AsyncMock(
            return_value={
                "workflow_id": "wf-1",
                "name": "agent",
                "status": "SUCCESS",
                "created_at": 1,
                "updated_at": 2,
                "output": None,
                "recovery_attempts": None,
            }
        )
        client.get_steps = mock.AsyncMock(return_value=[{"function_id": 1, "error": None}])

        with (
            mock.patch(
                "sdk.dashboard.client.fetch_agent_events_for_dashboard",
                mock.AsyncMock(return_value=[{"event_type": "tool_call", "step_id": 1}]),
            ) as fetch_events,
            mock.patch(
                "sdk.dashboard.client.build_step_records",
                return_value=[{"step_id": 1, "event_type": "tool_call"}],
            ) as build_records,
        ):
            workflow, steps, events = await client.get_workflow_detail_data("wf-1")

        self.assertEqual(workflow["workflow_id"], "wf-1")
        self.assertEqual(steps, [{"step_id": 1, "event_type": "tool_call"}])
        self.assertEqual(events, [{"event_type": "tool_call", "step_id": 1}])
        fetch_events.assert_awaited_once_with("wf-1", "postgresql://db")
        build_records.assert_called_once_with(
            [{"function_id": 1, "error": None}],
            [{"event_type": "tool_call", "step_id": 1}],
        )

    async def test_resume_workflow_returns_action_payload(self):
        client = DashboardClient.__new__(DashboardClient)
        client._db_url = "postgresql://db"
        client._client = mock.Mock()
        client._client.resume_workflow_async = mock.AsyncMock()

        result = await client.resume_workflow("wf-1", queue_name="q1")

        self.assertEqual(
            result, {"workflow_id": "wf-1", "action": "resume", "accepted": True}
        )
        client._client.resume_workflow_async.assert_awaited_once_with(
            "wf-1", queue_name="q1"
        )

    async def test_cancel_workflow_returns_action_payload(self):
        client = DashboardClient.__new__(DashboardClient)
        client._db_url = "postgresql://db"
        client._client = mock.Mock()
        client._client.cancel_workflow_async = mock.AsyncMock()

        result = await client.cancel_workflow("wf-1")

        self.assertEqual(
            result, {"workflow_id": "wf-1", "action": "cancel", "accepted": True}
        )
        client._client.cancel_workflow_async.assert_awaited_once_with("wf-1")
