from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from dbos import DBOSClient

OPEN_QUEUE_STATUSES = ("ENQUEUED", "PENDING")
DEFAULT_METRIC_NAMESPACE = "Amber/Queues"
DEFAULT_METRIC_INTERVAL_SECONDS = 60.0
DEFAULT_PAGE_SIZE = 1000


async def count_open_queue_workflows(
    *,
    db_url: str,
    queue_name: str,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Counter[str]:
    client = DBOSClient(system_database_url=db_url)
    try:
        counts: Counter[str] = Counter()
        for status in OPEN_QUEUE_STATUSES:
            counts[status] = await _count_queue_workflows_by_status(
                client,
                queue_name=queue_name,
                status=status,
                page_size=page_size,
            )
        return counts
    finally:
        client.destroy()


async def _count_queue_workflows_by_status(
    client: DBOSClient,
    *,
    queue_name: str,
    status: str,
    page_size: int,
) -> int:
    count = 0
    offset = 0
    while True:
        page = await client.list_workflows_async(
            queue_name=queue_name,
            status=status,
            limit=page_size,
            offset=offset,
            sort_desc=False,
            load_input=False,
            load_output=False,
        )
        count += len(page)
        if len(page) < page_size:
            return count
        offset += page_size


def build_queue_metric_payload(
    *,
    queue_name: str,
    counts: Mapping[str, int],
    namespace: str = DEFAULT_METRIC_NAMESPACE,
    dimensions: Mapping[str, str] | None = None,
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    backlog = int(counts.get("ENQUEUED", 0))
    active = int(counts.get("PENDING", 0))
    dimension_values = {
        "QueueName": queue_name,
        **(dict(dimensions or {})),
    }

    return {
        "_aws": {
            "Timestamp": timestamp_ms or int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [list(dimension_values.keys())],
                    "Metrics": [
                        {"Name": "QueueBacklog", "Unit": "Count"},
                        {"Name": "QueueActive", "Unit": "Count"},
                        {"Name": "QueueOpen", "Unit": "Count"},
                    ],
                }
            ],
        },
        **dimension_values,
        "QueueBacklog": backlog,
        "QueueActive": active,
        "QueueOpen": backlog + active,
    }


def start_queue_metrics_publisher(
    *,
    db_url: str,
    queue_name: str,
    namespace: str = DEFAULT_METRIC_NAMESPACE,
    interval_seconds: float = DEFAULT_METRIC_INTERVAL_SECONDS,
    dimensions: Mapping[str, str] | None = None,
) -> threading.Thread:
    thread = threading.Thread(
        target=_run_queue_metrics_publisher,
        kwargs={
            "db_url": db_url,
            "queue_name": queue_name,
            "namespace": namespace,
            "interval_seconds": interval_seconds,
            "dimensions": dict(dimensions or {}),
        },
        name="queue-metrics-publisher",
        daemon=True,
    )
    thread.start()
    return thread


def _run_queue_metrics_publisher(
    *,
    db_url: str,
    queue_name: str,
    namespace: str,
    interval_seconds: float,
    dimensions: Mapping[str, str],
) -> None:
    while True:
        try:
            counts = asyncio.run(
                count_open_queue_workflows(db_url=db_url, queue_name=queue_name)
            )
            payload = build_queue_metric_payload(
                queue_name=queue_name,
                counts=counts,
                namespace=namespace,
                dimensions=dimensions,
            )
            print(json.dumps(payload, sort_keys=True), flush=True)
        except Exception as exc:
            error_payload = {
                "level": "error",
                "message": "failed to publish queue metrics",
                "queue_name": queue_name,
                "error": str(exc),
                "timestamp": datetime.now(tz=UTC).isoformat(),
            }
            print(json.dumps(error_payload, sort_keys=True), file=sys.stderr, flush=True)
        time.sleep(interval_seconds)


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

