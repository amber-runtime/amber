"""
Crash-safe agent observability via the OpenAI Agents SDK native TracingProcessor.

Writes LLM, tool, and handoff events synchronously to Postgres inside the
executing DBOS step — before the step returns and before DBOS checkpoints it.
This makes llm_response and tool_call events durable by construction.

Durability by event type:
  llm_response  — fires inside _model_call_step            → durable
  tool_call     — fires inside the tool's DBOS step        → durable
  handoff       — fires in runner loop between steps        → best-effort

Observability failures are swallowed: a transient DB error logs and continues
rather than crashing the agent. The agent running correctly takes priority.
"""

import json
import logging
from typing import Any

import psycopg2
import psycopg2.extras
from agents.tracing.processor_interface import TracingProcessor
from agents.tracing.span_data import (
    FunctionSpanData,
    GenerationSpanData,
    HandoffSpanData,
    ResponseSpanData,
)
from dbos import DBOS

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS agent_events (
    id                   BIGSERIAL    PRIMARY KEY,
    span_id              TEXT         NOT NULL UNIQUE,
    workflow_id          TEXT         NOT NULL,
    step_id              INTEGER      NULL,
    event_type           TEXT         NOT NULL,
    model                TEXT         NULL,
    tokens_in            INTEGER      NULL,
    tokens_out           INTEGER      NULL,
    provider_response_id TEXT         NULL,
    tool_name            TEXT         NULL,
    tool_args            JSONB        NULL,
    tool_result          TEXT         NULL,
    from_agent           TEXT         NULL,
    to_agent             TEXT         NULL,
    captured_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_events_workflow_id ON agent_events (workflow_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_captured_at ON agent_events (captured_at DESC);
"""


def ensure_tables(db_url: str) -> None:
    """Create agent_events table if it does not exist. Called once at init."""
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(_DDL)
        conn.commit()
    finally:
        conn.close()


def _write_agent_event(db_url: str, record: dict[str, Any]) -> None:
    """Single synchronous INSERT — ON CONFLICT DO NOTHING for idempotency on step retry."""
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO agent_events (
                    span_id, workflow_id, step_id, event_type,
                    model, tokens_in, tokens_out, provider_response_id,
                    tool_name, tool_args, tool_result,
                    from_agent, to_agent
                ) VALUES %s
                ON CONFLICT (span_id) DO NOTHING
                """,
                [(
                    record["span_id"],
                    record["workflow_id"],
                    record.get("step_id"),
                    record["event_type"],
                    record.get("model"),
                    record.get("tokens_in"),
                    record.get("tokens_out"),
                    record.get("provider_response_id"),
                    record.get("tool_name"),
                    psycopg2.extras.Json(record["tool_args"]) if record.get("tool_args") is not None else None,
                    record.get("tool_result"),
                    record.get("from_agent"),
                    record.get("to_agent"),
                )],
            )
        conn.commit()
    finally:
        conn.close()


class CheckpointTracingProcessor(TracingProcessor):
    """
    OpenAI Agents SDK TracingProcessor that writes agent events to Postgres
    synchronously in on_span_end.

    Uses add_trace_processor() so it runs alongside any other processors
    (e.g. OpenInference) without interference.
    """

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    def on_trace_start(self, trace: Any) -> None:
        pass

    def on_trace_end(self, trace: Any) -> None:
        pass

    def on_span_start(self, span: Any) -> None:
        pass

    def on_span_end(self, span: Any) -> None:
        try:
            workflow_id = DBOS.workflow_id
            if not workflow_id:
                return  # outside a DBOS workflow context

            data = span.span_data
            record: dict[str, Any] | None = None

            if isinstance(data, GenerationSpanData):
                usage = data.usage or {}
                record = {
                    "event_type": "llm_response",
                    "model":      data.model,
                    "tokens_in":  usage.get("input_tokens"),
                    "tokens_out": usage.get("output_tokens"),
                }

            elif isinstance(data, ResponseSpanData):
                usage = data.usage or {}
                record = {
                    "event_type":           "llm_response",
                    "model":                getattr(data.response, "model", None) if data.response else None,
                    "tokens_in":            usage.get("input_tokens"),
                    "tokens_out":           usage.get("output_tokens"),
                    "provider_response_id": data.response.id if data.response else None,
                }

            elif isinstance(data, FunctionSpanData):
                tool_args = _parse_json_or_str(data.input)
                record = {
                    "event_type":  "tool_call",
                    "tool_name":   data.name,
                    "tool_args":   tool_args,
                    "tool_result": str(data.output or "")[:500],
                }

            elif isinstance(data, HandoffSpanData):
                record = {
                    "event_type": "handoff",
                    "from_agent": data.from_agent,
                    "to_agent":   data.to_agent,
                }

            if record is not None:
                record["span_id"]     = span.span_id
                record["workflow_id"] = workflow_id
                record["step_id"]     = DBOS.step_id
                _write_agent_event(self._db_url, record)

        except Exception:
            logger.exception("CheckpointTracingProcessor: failed to write event, continuing")

    def force_flush(self) -> None:
        pass  # writes are synchronous — nothing to flush

    def shutdown(self) -> None:
        pass  # no persistent connections to close


def _parse_json_or_str(value: str | None) -> Any:
    """Try to parse a JSON string into a dict/list; return raw string on failure."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
