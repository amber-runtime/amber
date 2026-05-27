"""
Load-test queue worker.

Run:
  uv run python -m tests.load_testing.load_worker
"""

import os

from sdk import Runtime, WorkerService
from tests.load_testing.config import load_load_test_config


def main() -> None:
    load_test_config = load_load_test_config()
    worker_concurrency = int(os.getenv("WORKER_CONCURRENCY", "1"))
    queue_concurrency = os.getenv("QUEUE_CONCURRENCY")
    concurrency = int(queue_concurrency) if queue_concurrency else None

    runtime = Runtime(
        name=load_test_config.runtime_name,
        db_url=load_test_config.db_url,
    )
    worker = WorkerService(
        runtime=runtime,
        agent_modules=[
            "tests.load_testing.synthetic_queue_agent",
        ],
        queue_name="agent-runs",
        worker_concurrency=worker_concurrency,
        concurrency=concurrency,
    )
    worker.run()


if __name__ == "__main__":
    main()
