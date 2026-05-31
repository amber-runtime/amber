from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from sdk import queue_metrics


class FakeDBOSClient:
    instances: list["FakeDBOSClient"] = []

    def __init__(self, *, system_database_url: str):
        self.system_database_url = system_database_url
        self.destroyed = False
        FakeDBOSClient.instances.append(self)

    async def list_workflows_async(self, **kwargs):
        status = kwargs["status"]
        offset = kwargs["offset"]
        limit = kwargs["limit"]
        pages = {
            ("ENQUEUED", 0): [object(), object()],
            ("PENDING", 0): [object()],
        }
        return pages.get((status, offset), [])[:limit]

    def destroy(self) -> None:
        self.destroyed = True


class QueueMetricsTests(unittest.TestCase):
    def test_build_queue_metric_payload_uses_emf_shape(self):
        payload = queue_metrics.build_queue_metric_payload(
            queue_name="agent-runs",
            counts={"ENQUEUED": 3, "PENDING": 2},
            dimensions={
                "Project": "amber",
                "Environment": "dev",
                "Service": "customer-worker",
            },
            timestamp_ms=123,
        )

        self.assertEqual(payload["QueueBacklog"], 3)
        self.assertEqual(payload["QueueActive"], 2)
        self.assertEqual(payload["QueueOpen"], 5)
        self.assertEqual(payload["QueueName"], "agent-runs")
        self.assertEqual(payload["_aws"]["Timestamp"], 123)
        self.assertEqual(
            payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"],
            [["QueueName", "Project", "Environment", "Service"]],
        )

    def test_count_open_queue_workflows_counts_enqueued_and_pending(self):
        FakeDBOSClient.instances = []

        with patch.object(queue_metrics, "DBOSClient", FakeDBOSClient):
            counts = asyncio.run(
                queue_metrics.count_open_queue_workflows(
                    db_url="postgresql://db",
                    queue_name="agent-runs",
                )
            )

        self.assertEqual(counts["ENQUEUED"], 2)
        self.assertEqual(counts["PENDING"], 1)
        self.assertEqual(FakeDBOSClient.instances[0].system_database_url, "postgresql://db")
        self.assertTrue(FakeDBOSClient.instances[0].destroyed)


if __name__ == "__main__":
    unittest.main()
