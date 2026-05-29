"""
Customer app using our SDK

Run API:
  uv run uvicorn example_customer_app.main:app --port 8003

Run worker in another terminal:
  uv run python -m sdk.worker example_customer_app.main:agent_runtime
"""

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# Import agent modules so their @register_agent workflows are registered.
from .user_agents import (
    account_research_error_demo,
    another_multi_agent_demo,
    multi_agent_demo,
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
ASSET_VERSION = max(
    int((BASE_DIR / "static" / "app.js").stat().st_mtime),
    int((BASE_DIR / "static" / "styles.css").stat().st_mtime),
)


class RunRequest(BaseModel):
    agent: str = Field(
        examples=[
            "research-assistant",
            "travel-concierge",
            "research-handoff-agent",
            "account-research-error-demo",
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
        "sample_input": another_multi_agent_demo.SAMPLE_MESSAGE,
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
    "account-research-error-demo": {
        "display_name": "Account Research Error Demo",
        "description": (
            "A multi-agent pre-call research workflow that sends the AE brief, then "
            "takes a rare enterprise deep-scan branch and fails with ConnectionError "
            "until you fork, add logs, and add backoff."
        ),
        "category": "Ops Demo",
        "sample_input": account_research_error_demo.SAMPLE_INPUT,
    },
}
TRAVEL_AGENT_NAME = "travel-concierge"
_ACCOUNT_RESEARCH_DEMO_ERROR_TEXT = (
    "Error running tool scrape_deep_competitive_signals: "
    "Remote end closed connection without response"
)


def _is_account_research_demo_exception(exc: object) -> bool:
    return _ACCOUNT_RESEARCH_DEMO_ERROR_TEXT in str(exc)


class _SuppressAccountResearchDemoTraceback(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not record.exc_info:
            return True

        exc_type, exc, _tb = record.exc_info
        if exc_type is None or exc is None:
            return True

        if (
            record.getMessage().startswith("Exception encountered in asynchronous workflow")
            and _is_account_research_demo_exception(exc)
        ):
            return False

        return True


class _SuppressAccountResearchDemoAsyncioNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if not message.startswith("Future exception was never retrieved"):
            return True

        if _ACCOUNT_RESEARCH_DEMO_ERROR_TEXT in message:
            return False

        if record.exc_info and record.exc_info[1] and _is_account_research_demo_exception(record.exc_info[1]):
            return False

        return True


def _install_account_research_demo_log_filter() -> None:
    traceback_filter = _SuppressAccountResearchDemoTraceback()
    asyncio_filter = _SuppressAccountResearchDemoAsyncioNoise()

    dbos_logger = logging.getLogger("dbos")
    if not getattr(dbos_logger, "_account_research_demo_filter_installed", False):
        dbos_logger.addFilter(traceback_filter)
        dbos_logger._account_research_demo_filter_installed = True

    asyncio_logger = logging.getLogger("asyncio")
    if not getattr(asyncio_logger, "_account_research_demo_filter_installed", False):
        asyncio_logger.addFilter(asyncio_filter)
        asyncio_logger._account_research_demo_filter_installed = True

    root_logger = logging.getLogger()
    if not getattr(root_logger, "_account_research_demo_filter_installed", False):
        for handler in root_logger.handlers:
            handler.addFilter(traceback_filter)
            handler.addFilter(asyncio_filter)
        root_logger._account_research_demo_filter_installed = True


def _install_account_research_demo_exception_suppression() -> None:
    _install_account_research_demo_log_filter()


_install_account_research_demo_exception_suppression()


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


def _arm_travel_crash_input(agent: str, run_input: str) -> str:
    if agent == TRAVEL_AGENT_NAME:
        return multi_agent_demo.request_hotel_crash_demo(run_input)
    return run_input


def _should_arm_account_research_ratelimit(
    agent: str,
    *,
    trigger_account_research_ratelimit: bool,
) -> bool:
    return agent == "account-research-error-demo" and trigger_account_research_ratelimit


def _arm_account_research_ratelimit_input(run_input: str) -> str:
    # Injects both the enterprise branch and the rate-limit simulation directives.
    # The rate-limit fires based on query timing inside the deep-scan step, so
    # forks with the logger uncommented still fail, and only forks with the
    # sleep uncommented succeed.
    return account_research_error_demo.enable_account_research_failure_demo(run_input)


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
                "Research vendors, prepare decision memos, plan business travel, and "
                "debug durable multi-agent workflows from one AI workspace."
            ),
            "asset_version": ASSET_VERSION,
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


RUN_REQUEST_EXAMPLES = {
    "market_research": {
        "summary": "Market research",
        "description": "Research vendor and market context for an operations decision.",
        "value": {
            "agent": "research-assistant",
            "input": "Research AI dispatch software vendors for midsize logistics operators.",
        },
    },
    "decision_memo": {
        "summary": "Decision memo",
        "description": "Prepare an evidence-backed recommendation with risks and counterarguments.",
        "value": {
            "agent": "research-handoff-agent",
            "input": another_multi_agent_demo.SAMPLE_MESSAGE,
        },
    },
    "site_visit_planner": {
        "summary": "Site visit planner",
        "description": "Plan business travel for a vendor, customer, or site visit.",
        "value": {
            "agent": "travel-concierge",
            "input": (
                "Plan a 3-night vendor site visit to Tokyo from SFO for 2 people, "
                "departing 2026-07-10 and returning 2026-07-13, budget $3000."
            ),
        },
    },
    "account_research_error_demo": {
        "summary": "Account research error demo",
        "description": (
            "Run the enterprise pre-call research workflow with an optional transient "
            "ConnectionError at the deep competitive scan step."
        ),
        "value": {
            "agent": "account-research-error-demo",
            "input": account_research_error_demo.SAMPLE_INPUT,
        },
    },
}


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
    trigger_account_research_ratelimit: bool = Query(
        default=False,
        description=(
            "Demo-only: force the enterprise branch and arm a one-shot "
            "ConnectionError at deep scan query 3 for the account-research demo."
        ),
    ),
) -> RunResponse:
    run_input = request.input
    if _should_arm_travel_crash(
        request.agent,
        crash_during_hotel=crash_during_hotel,
    ):
        run_input = _arm_travel_crash_input(request.agent, run_input)
    if _should_arm_account_research_ratelimit(
        request.agent,
        trigger_account_research_ratelimit=trigger_account_research_ratelimit,
    ):
        run_input = _arm_account_research_ratelimit_input(run_input)

    handle = await agent_runtime.agents.start(request.agent, run_input)
    return RunResponse(workflow_id=handle.workflow_id, agent=request.agent)
