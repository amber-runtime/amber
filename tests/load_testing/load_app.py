"""
Load-test API for synthetic queue runs.

Run:
  uv run uvicorn tests.load_testing.load_app:app --port 8004
"""

from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel

from sdk import AgentService, Runtime, list_registered_agents
from tests.load_testing.config import load_load_test_config
from tests.load_testing import synthetic_queue_agent

SYNTHETIC_AGENT_NAME = "synthetic-queue-agent"

load_test_config = load_load_test_config()
runtime = Runtime(
    name=load_test_config.runtime_name,
    db_url=load_test_config.db_url,
)
agents = AgentService(runtime)


class RunRequest(BaseModel):
    agent: str = SYNTHETIC_AGENT_NAME
    input: str = synthetic_queue_agent.SAMPLE_MESSAGE


class RunResponse(BaseModel):
    workflow_id: str
    agent: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.start(listen_queues=[])
    yield


app = FastAPI(
    title="Synthetic Queue Load Test API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "registered_agents": [agent.name for agent in list_registered_agents()],
    }


@app.post("/runs", response_model=RunResponse)
async def create_run(request: RunRequest = Body()) -> RunResponse:
    if request.agent != SYNTHETIC_AGENT_NAME:
        raise HTTPException(
            status_code=400,
            detail=f"Only {SYNTHETIC_AGENT_NAME!r} is supported by the load-test API.",
        )

    handle = await agents.enqueue(request.agent, request.input)
    return RunResponse(workflow_id=handle.workflow_id, agent=request.agent)
