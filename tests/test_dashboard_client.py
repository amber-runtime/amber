import sys
import unittest
import importlib.util
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
            offset=0,
            sort_desc=True,
            load_input=False,
            load_output=False,
            status="SUCCESS",
        )

    async def test_list_queue_workflows_forwards_queue_filters_without_queues_only(self):
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
                    queue_name="agent-runs",
                )
            ]
        )

        rows = await client.list_queue_workflows(
            queue_name="agent-runs",
            start_time="2026-05-26T00:00:00Z",
            limit=10,
            offset=20,
            sort_desc=False,
        )

        self.assertEqual(rows[0]["workflow_id"], "wf-1")
        self.assertEqual(rows[0]["queue_name"], "agent-runs")
        client._client.list_workflows_async.assert_awaited_once_with(
            limit=10,
            offset=20,
            sort_desc=False,
            load_input=False,
            load_output=False,
            queue_name="agent-runs",
            start_time="2026-05-26T00:00:00Z",
        )

    async def test_get_workflow_includes_output_and_queue_name(self):
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
                    queue_name="agent-runs",
                )
            ]
        )

        workflow = await client.get_workflow("wf-1")

        self.assertEqual(workflow["output"], "{'done': True}")
        self.assertEqual(workflow["queue_name"], "agent-runs")
        client._client.list_workflows_async.assert_awaited_once_with(
            workflow_ids=["wf-1"],
            load_input=False,
            load_output=True,
        )

    async def test_get_workflow_returns_none_when_missing(self):
        client = DashboardClient.__new__(DashboardClient)
        client._db_url = "postgresql://db"
        client._client = mock.Mock()
        client._client.list_workflows_async = mock.AsyncMock(return_value=[])

        self.assertIsNone(await client.get_workflow("missing"))

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
                "forked_from": None,
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
            {
                "workflow_id": "wf-1",
                "name": "agent",
                "status": "SUCCESS",
                "created_at": 1,
                "updated_at": 2,
                "forked_from": None,
                "output": None,
                "recovery_attempts": None,
            },
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

    async def test_delete_workflows_calls_dbos_client_and_returns_payload(self):
        client = DashboardClient.__new__(DashboardClient)
        client._client = mock.Mock()
        client._client.delete_workflows_async = mock.AsyncMock()

        result = await client.delete_workflows(["wf-1", "wf-2"])

        self.assertEqual(result, {"deleted": 2, "action": "delete", "accepted": True})
        client._client.delete_workflows_async.assert_awaited_once_with(["wf-1", "wf-2"])

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

    async def test_fork_workflow_returns_action_payload(self):
        client = DashboardClient.__new__(DashboardClient)
        client._db_url = "postgresql://db"
        client._client = mock.Mock()
        handle = mock.Mock()
        handle.get_workflow_id.return_value = "wf-2"
        client._client.fork_workflow_async = mock.AsyncMock(return_value=handle)

        result = await client.fork_workflow("wf-1", 7, queue_name="agent-runs")

        self.assertEqual(
            result,
            {
                "workflow_id": "wf-1",
                "forked_workflow_id": "wf-2",
                "start_step": 7,
                "action": "fork",
                "accepted": True,
            },
        )
        client._client.fork_workflow_async.assert_awaited_once_with(
            "wf-1",
            7,
            queue_name="agent-runs",
        )


class QueueDrainReporterTests(unittest.IsolatedAsyncioTestCase):
    def load_reporter(self):
        spec = importlib.util.spec_from_file_location(
            "queue_drain_report_under_test",
            ROOT / "tests/load_testing/scripts/queue_drain_report.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    async def test_reporter_uses_dashboard_client(self):
        reporter = self.load_reporter()

        class FakeDashboardClient:
            instances = []

            def __init__(self, *, db_url: str):
                self.db_url = db_url
                self.destroyed = False
                FakeDashboardClient.instances.append(self)

            async def list_queue_workflows(self, **kwargs):
                self.last_kwargs = kwargs
                return [
                    {
                        "workflow_id": "wf-1",
                        "name": "synthetic-queue-agent",
                        "status": "SUCCESS",
                        "created_at": 1,
                        "updated_at": 2,
                        "queue_name": "agent-runs",
                    }
                ]

            def destroy(self):
                self.destroyed = True

        args = SimpleNamespace(
            db_url="postgresql://db",
            start_time="2026-05-26T00:00:00Z",
            queue_name="agent-runs",
            min_total=1,
            timeout=1.0,
            poll_interval=0.01,
            page_size=100,
            allow_errors=False,
        )

        with mock.patch.object(reporter, "DashboardClient", FakeDashboardClient):
            exit_code = await reporter.run_report(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeDashboardClient.instances[0].db_url, "postgresql://db")
        self.assertTrue(FakeDashboardClient.instances[0].destroyed)
        self.assertEqual(
            FakeDashboardClient.instances[0].last_kwargs,
            {
                "queue_name": "agent-runs",
                "start_time": "2026-05-26T00:00:00Z",
                "limit": 100,
                "offset": 0,
                "sort_desc": False,
            },
        )
