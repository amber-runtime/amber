import importlib
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient


os.environ.setdefault("DB_URL", "postgresql://db")

dashboard_backend = importlib.import_module("admin_control_plane.dashboard_backend")


class DashboardBackendTests(unittest.TestCase):
    def test_fork_workflow_endpoint_forwards_request(self):
        fake_client = mock.Mock()
        fake_client.get_workflow = mock.AsyncMock(
            return_value={"workflow_id": "wf-1", "queue_name": "agent-runs"}
        )
        fake_client.fork_workflow = mock.AsyncMock(
            return_value={
                "workflow_id": "wf-1",
                "forked_workflow_id": "wf-2",
                "start_step": 7,
                "action": "fork",
                "accepted": True,
            }
        )

        with mock.patch.object(
            dashboard_backend, "get_dashboard_client", return_value=fake_client
        ), mock.patch.object(dashboard_backend, "ensure_pricing_table"):
            with TestClient(dashboard_backend.app) as client:
                response = client.post("/workflows/wf-1/fork", json={"start_step": 7})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "workflow_id": "wf-1",
                "forked_workflow_id": "wf-2",
                "start_step": 7,
                "action": "fork",
                "accepted": True,
            },
        )
        fake_client.get_workflow.assert_awaited_once_with("wf-1")
        fake_client.fork_workflow.assert_awaited_once_with(
            "wf-1",
            7,
            queue_name="agent-runs",
        )

    def test_fork_workflow_endpoint_returns_404_when_missing(self):
        fake_client = mock.Mock()
        fake_client.get_workflow = mock.AsyncMock(return_value=None)
        fake_client.fork_workflow = mock.AsyncMock()

        with mock.patch.object(
            dashboard_backend, "get_dashboard_client", return_value=fake_client
        ), mock.patch.object(dashboard_backend, "ensure_pricing_table"):
            with TestClient(dashboard_backend.app) as client:
                response = client.post("/workflows/wf-missing/fork", json={"start_step": 7})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Workflow 'wf-missing' not found"})
        fake_client.get_workflow.assert_awaited_once_with("wf-missing")
        fake_client.fork_workflow.assert_not_called()

    def test_delete_workflows_endpoint_forwards_request(self):
        fake_client = mock.Mock()
        fake_client.delete_workflows = mock.AsyncMock(
            return_value={"deleted": 2, "action": "delete", "accepted": True}
        )

        with mock.patch.object(
            dashboard_backend, "get_dashboard_client", return_value=fake_client
        ), mock.patch.object(dashboard_backend, "ensure_pricing_table"):
            with TestClient(dashboard_backend.app) as client:
                response = client.post(
                    "/workflows/delete", json={"workflow_ids": ["wf-1", "wf-2"]}
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"deleted": 2, "action": "delete", "accepted": True}
        )
        fake_client.delete_workflows.assert_awaited_once_with(["wf-1", "wf-2"])

    def test_delete_workflows_endpoint_rejects_empty_list(self):
        fake_client = mock.Mock()
        fake_client.delete_workflows = mock.AsyncMock()

        with mock.patch.object(
            dashboard_backend, "get_dashboard_client", return_value=fake_client
        ), mock.patch.object(dashboard_backend, "ensure_pricing_table"):
            with TestClient(dashboard_backend.app) as client:
                response = client.post("/workflows/delete", json={"workflow_ids": []})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "workflow_ids must not be empty"})
        fake_client.delete_workflows.assert_not_called()

    def test_fork_workflow_endpoint_rejects_invalid_step(self):
        fake_client = mock.Mock()
        fake_client.get_workflow = mock.AsyncMock()
        fake_client.fork_workflow = mock.AsyncMock()

        with mock.patch.object(
            dashboard_backend, "get_dashboard_client", return_value=fake_client
        ), mock.patch.object(dashboard_backend, "ensure_pricing_table"):
            with TestClient(dashboard_backend.app) as client:
                response = client.post("/workflows/wf-1/fork", json={"start_step": 0})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "start_step must be >= 1"})
        fake_client.fork_workflow.assert_not_called()
