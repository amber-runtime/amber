from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sdk.dashboard import DashboardClient
from tests.load_testing.config import load_load_test_config

WATCH_STATUSES = ("ENQUEUED", "PENDING", "SUCCESS", "ERROR", "CANCELLED")
TERMINAL_STATUSES = {"SUCCESS", "ERROR", "CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"}


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _workflow_status(workflow) -> str:
    if isinstance(workflow, dict):
        return str(workflow.get("status") or "UNKNOWN")
    return str(getattr(workflow, "status", "UNKNOWN") or "UNKNOWN")


async def _list_workflows(
    client: DashboardClient,
    *,
    queue_name: str,
    start_time: str,
    page_size: int,
) -> list:
    workflows = []
    offset = 0
    while True:
        page = await client.list_queue_workflows(
            queue_name=queue_name,
            start_time=start_time,
            limit=page_size,
            offset=offset,
            sort_desc=False,
        )
        workflows.extend(page)
        if len(page) < page_size:
            return workflows
        offset += page_size


def _format_counts(counts: Counter[str]) -> str:
    return " ".join(f"{status}={counts.get(status, 0)}" for status in WATCH_STATUSES)


def _is_drained(statuses: Iterable[str], *, min_total: int) -> bool:
    statuses = list(statuses)
    if len(statuses) < min_total:
        return False
    return all(status in TERMINAL_STATUSES for status in statuses)


async def run_report(args: argparse.Namespace) -> int:
    if args.db_url:
        db_url = args.db_url
    else:
        try:
            db_url = load_load_test_config().db_url
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc

    start_time = args.start_time or _iso_now()
    started_at = time.monotonic()
    max_pending = 0
    first_seen_at: float | None = None
    drained_at: float | None = None

    client = DashboardClient(db_url=db_url)
    try:
        print(
            f"Watching queue={args.queue_name} start_time={start_time} "
            f"min_total={args.min_total} timeout={args.timeout}s"
        )
        while True:
            workflows = await _list_workflows(
                client,
                queue_name=args.queue_name,
                start_time=start_time,
                page_size=args.page_size,
            )
            statuses = [_workflow_status(workflow) for workflow in workflows]
            counts = Counter(statuses)
            total = len(workflows)
            pending = counts.get("PENDING", 0)
            max_pending = max(max_pending, pending)

            if total > 0 and first_seen_at is None:
                first_seen_at = time.monotonic()

            elapsed = time.monotonic() - started_at
            print(
                f"t={elapsed:6.1f}s total={total} {_format_counts(counts)} "
                f"max_pending={max_pending}"
            )

            if _is_drained(statuses, min_total=args.min_total):
                drained_at = time.monotonic()
                break

            if elapsed >= args.timeout:
                print("Timed out before queue drained")
                return 1

            await asyncio.sleep(args.poll_interval)
    finally:
        client.destroy()

    drain_seconds = (drained_at or time.monotonic()) - (first_seen_at or started_at)
    throughput = len(statuses) / drain_seconds if drain_seconds > 0 else 0.0
    error_count = sum(1 for status in statuses if status not in {"SUCCESS"})
    print(
        "Drain complete: "
        f"total={len(statuses)} max_pending={max_pending} "
        f"drain_seconds={drain_seconds:.1f} throughput={throughput:.2f}/s "
        f"non_success_terminal={error_count}"
    )
    return 0 if error_count == 0 or args.allow_errors else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report DBOS queue drain behavior.")
    parser.add_argument("--queue-name", default="agent-runs")
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--start-time", default=None, help="RFC3339 timestamp; defaults to now")
    parser.add_argument("--min-total", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--allow-errors", action="store_true")
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(run_report(parse_args())))


if __name__ == "__main__":
    main()
