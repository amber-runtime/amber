"""
Customer app using our SDK

Run:
  uv run uvicorn example_customer_app.main:app --port 8003
"""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import agent modules so their @register_agent workflows are registered.
import user_agents.multi_agent_demo
import user_agents.single_agent_demo  # noqa: F401
from sdk import ensure_initialized, list_registered_agents, start_agent

load_dotenv()


class RunRequest(BaseModel):
    agent: str = Field(examples=["research-assistant", "travel-concierge"])
    input: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_initialized()
    yield


class RunResponse(BaseModel):
    workflow_id: str
    agent: str


class RegisteredAgentResponse(BaseModel):
    name: str


app = FastAPI(
    title="Customer App with Embedded Checkpoint SDK",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "registered_agents": [agent.name for agent in list_registered_agents()],
    }


@app.get("/agents", response_model=list[RegisteredAgentResponse])
async def get_agents() -> list[RegisteredAgentResponse]:
    return [
        RegisteredAgentResponse(name=registered_agent.name)
        for registered_agent in list_registered_agents()
    ]


RUN_REQUEST_EXAMPLES = {
    "travel_concierge_simple": {
        "summary": "Travel concierge, simple",
        "description": "Use demo defaults to plan a Tokyo trip.",
        "value": {
            "agent": "travel-concierge",
            "input": "book me a trip to tokyo",
        },
    },
    "travel_concierge_complete": {
        "summary": "Travel concierge, complete",
        "description": "Explicit origin, dates, guests, and budget.",
        "value": {
            "agent": "travel-concierge",
            "input": (
                "Book me a 3-night trip to Tokyo from SFO for 2 people, "
                "departing 2026-07-10 and returning 2026-07-13, budget $3000."
            ),
        },
    },
    "research_assistant": {
        "summary": "Research assistant",
        "description": "Run the single-agent research demo.",
        "value": {
            "agent": "research-assistant",
            "input": "research Tokyo travel trends",
        },
    },
}


@app.post("/runs", response_model=RunResponse)
async def create_run(
    request: RunRequest = Body(openapi_examples=RUN_REQUEST_EXAMPLES),
    crash_during_hotel: bool = Query(
        default=False,
        description=(
            "Demo-only: intentionally terminate the process once during "
            "travel-concierge hotel quote lookup."
        ),
    ),
) -> RunResponse:
    run_input = request.input
    if crash_during_hotel and request.agent == "travel-concierge":
        run_input = user_agents.multi_agent_demo.request_hotel_crash_demo(run_input)

    handle = await start_agent(request.agent, run_input)
    return RunResponse(workflow_id=handle.workflow_id, agent=request.agent)
