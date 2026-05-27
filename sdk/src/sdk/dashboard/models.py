from typing import Any, Optional

from pydantic import BaseModel


class WorkflowSummary(BaseModel):
    workflow_id: str
    name: str
    status: str
    created_at: Optional[int]
    completed_at: Optional[int]
    recovery_attempts: Optional[int]


class WorkflowRecord(BaseModel):
    workflow_id: str
    name: str
    status: str
    created_at: Optional[int]
    updated_at: Optional[int]
    recovery_attempts: Optional[int]
    output: Optional[str] = None


class StepRecord(BaseModel):
    step_id: Optional[int]
    function_name: Optional[str]
    event_type: str
    status: str
    duration_ms: Optional[int]
    started_at_epoch_ms: Optional[int] = None
    completed_at_epoch_ms: Optional[int] = None
    display_started_at_epoch_ms: Optional[int] = None
    display_completed_at_epoch_ms: Optional[int] = None
    display_duration_ms: Optional[int] = None
    step_output: Any | None = None
    agent_name: Optional[str] = None
    llm_model: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    llm_input: Any | None = None
    llm_output: Any | None = None
    tool_name: Optional[str]
    tool_args: Any | None
    tool_result: Optional[str] = None
    captured_at: Any | None = None


class AgentEvent(BaseModel):
    span_id: str
    step_id: Optional[int]
    event_type: str
    agent_name: Optional[str] = None
    model: Optional[str]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    provider_response_id: Optional[str]
    llm_input: Any | None = None
    llm_output: Any | None = None
    tool_name: Optional[str]
    tool_args: Any | None
    tool_result: Optional[str]
    from_agent: Optional[str]
    to_agent: Optional[str]
    captured_at: Any


class WorkflowDetail(BaseModel):
    workflow: WorkflowRecord
    steps: list[StepRecord]
    events: list[AgentEvent]
