from __future__ import annotations

import re

from sdk import logger, register_agent, sleep

SAMPLE_MESSAGE = "sleep=5"
DEFAULT_SLEEP_SECONDS = 5
MAX_SLEEP_SECONDS = 300


def parse_sleep_seconds(message: str) -> int:
    match = re.search(r"\bsleep\s*=\s*(\d+)\b", message)
    if match is None:
        return DEFAULT_SLEEP_SECONDS
    return max(0, min(int(match.group(1)), MAX_SLEEP_SECONDS))


@register_agent(name="synthetic-queue-agent")
async def run_agent(message: str) -> str:
    sleep_seconds = parse_sleep_seconds(message)
    logger.info("synthetic-queue-agent sleeping for %s seconds", sleep_seconds)
    await sleep(sleep_seconds)
    return f"synthetic queue run completed after {sleep_seconds} seconds"
