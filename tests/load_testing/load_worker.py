"""
Load-test queue worker.

Run:
  uv run python -m tests.load_testing.load_worker
"""

import os

from dotenv import load_dotenv

from sdk import Runtime, WorkerService

load_dotenv()


def main() -> None:
    worker_concurrency = int(os.getenv("WORKER_CONCURRENCY", "1"))
    queue_concurrency = os.getenv("QUEUE_CONCURRENCY")
    concurrency = int(queue_concurrency) if queue_concurrency else None

    runtime = Runtime()
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
