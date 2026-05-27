from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_LOAD_TEST_RUNTIME_NAME = "amber-load-test"
ENV_FILE = Path(__file__).resolve().parent / ".env.load-test"


class LoadTestConfig:
    def __init__(self, *, db_url: str, runtime_name: str) -> None:
        self.db_url = db_url
        self.runtime_name = runtime_name


def load_load_test_config() -> LoadTestConfig:
    load_dotenv(ENV_FILE)

    db_url = os.environ.get("LOAD_TEST_DB_URL")
    if not db_url or not db_url.strip():
        raise RuntimeError(
            "LOAD_TEST_DB_URL is required for load testing. Set it in the "
            "environment or in .env.load-test so load tests cannot write to "
            "the normal customer app database."
        )

    runtime_name = (
        os.environ.get("LOAD_TEST_RUNTIME_NAME") or DEFAULT_LOAD_TEST_RUNTIME_NAME
    )
    return LoadTestConfig(db_url=db_url, runtime_name=runtime_name)
