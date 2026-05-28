"""
Customer app using our SDK

Run API:
  uv run uvicorn example_customer_app.main:app --port 8003

Run worker in another terminal:
  uv run python -m sdk.worker example_customer_app.main:agent_runtime
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# Import agent modules so their @register_agent workflows are registered.
from .user_agents import (
    multi_agent_demo,
    queued_multi_agent_demo,
    single_agent_demo,  # noqa: F401
)
from sdk import (
    AgentRuntime,
    get_workflow,
    list_registered_agents,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class RunRequest(BaseModel):
    agent: str = Field(
        examples=[
            "research-assistant",
            "travel-concierge",
            "research-handoff-agent",
        ]
    )
    input: str


class RunResponse(BaseModel):
    workflow_id: str
    agent: str


class RunStatusResponse(BaseModel):
    agent: str
    status: str
    output: str | None


class RegisteredAgentResponse(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    sample_input: str
    is_known: bool


KNOWN_AGENT_CAPABILITIES = {
    "research-assistant": {
        "display_name": "Market Research",
        "description": "Gather market, competitor, vendor, or industry context.",
        "category": "Research",
        "sample_input": "Research AI dispatch software vendors for midsize logistics operators.",
    },
    "research-handoff-agent": {
        "display_name": "Decision Memo",
        "description": "Prepare an evidence-backed recommendation with risks and counterarguments.",
        "category": "Memo",
        "sample_input": queued_multi_agent_demo.SAMPLE_MESSAGE,
    },
    "travel-concierge": {
        "display_name": "Site Visit Planner",
        "description": "Plan business travel for customer visits, vendor meetings, and site inspections.",
        "category": "Travel",
        "sample_input": (
            "Plan a 3-night vendor site visit to Tokyo from SFO for 2 people, "
            "departing 2026-07-10 and returning 2026-07-13, budget $3000."
        ),
    },
}


def _humanize_agent_name(name: str) -> str:
    return " ".join(
        part.capitalize() for part in name.replace("_", "-").split("-") if part
    )


def _agent_capability(name: str) -> RegisteredAgentResponse:
    metadata = KNOWN_AGENT_CAPABILITIES.get(name)
    if metadata:
        return RegisteredAgentResponse(name=name, is_known=True, **metadata)

    display_name = _humanize_agent_name(name) or name
    return RegisteredAgentResponse(
        name=name,
        display_name=display_name,
        description="Run an additional operations workflow for this request.",
        category="Additional Workflow",
        sample_input="",
        is_known=False,
    )


def _should_arm_travel_crash(agent: str, *, crash_during_hotel: bool) -> bool:
    if agent != "travel-concierge":
        return False
    return crash_during_hotel


agent_runtime = AgentRuntime()

app = FastAPI(
    title="Customer App with Checkpoint SDK",
    version="0.1.0",
    lifespan=agent_runtime.api_lifespan(),
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "Operations Research Hub",
            "subtitle": (
                "Research vendors, prepare decision memos, and plan business travel "
                "from one AI workspace."
            ),
        },
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
        _agent_capability(registered_agent.name)
        for registered_agent in list_registered_agents()
    ]


@app.get("/runs/{workflow_id}", response_model=RunStatusResponse)
async def get_run(workflow_id: str) -> RunStatusResponse:
    workflow = await get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Request not found")

    return RunStatusResponse(
        agent=str(workflow.get("name") or ""),
        status=str(workflow.get("status") or ""),
        output=workflow.get("output"),
    )


@app.post("/runs", response_model=RunResponse)
async def create_run(
    request: RunRequest,
    crash_during_hotel: bool = Query(
        default=False,
        description=(
            "Demo-only: intentionally terminate the process once during "
            "travel-concierge hotel quote lookup."
        ),
    ),
) -> RunResponse:
    run_input = request.input
    if _should_arm_travel_crash(
        request.agent,
        crash_during_hotel=crash_during_hotel,
    ):
        run_input = multi_agent_demo.request_hotel_crash_demo(run_input)

    handle = await agent_runtime.agents.start(request.agent, run_input)
    return RunResponse(workflow_id=handle.workflow_id, agent=request.agent)
