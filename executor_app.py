"""
Executor app — triggers and recovers workflows in a separate DBOS process.

## Run (on port 8002)
  uv run uvicorn executor_app:app --port 8002

## Endpoints
  POST /run   { "input": str, "agent_type": "research-assistant" | "email-campaign" }
              → { "workflow_id": str }
"""
import os
from contextlib import asynccontextmanager
from typing import Optional

from dbos import DBOS
from dbos._error import DBOSNonExistentWorkflowError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from mordec_ai_agents import run_agent, run_email_campaign
from sdk import init

load_dotenv()

DB_URL = (
    os.environ.get("DB_URL")
    or os.environ.get("DBOS_SYSTEM_DATABASE_URL")
    or ""
)


# ── Startup ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Importing the workflow functions above registers them with DBOS.
    # init() calls DBOS.launch(), which recovers any PENDING workflows.
    init(name="checkpoint-executor", db_url=DB_URL or None)
    yield


app = FastAPI(title="Agent Executor", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Models ────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    input: str
    agent_type: str


class WorkflowResult(BaseModel):
    workflow_id: str
    status: str
    output: Optional[str]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/run")
async def run(req: RunRequest) -> dict[str, str]:
    if req.agent_type == "research-assistant":
        handle = await DBOS.start_workflow_async(run_agent, req.input)
    elif req.agent_type == "email-campaign":
        handle = await DBOS.start_workflow_async(run_email_campaign, req.input)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent_type {req.agent_type!r}. Expected 'research-assistant' or 'email-campaign'.",
        )

    return {"workflow_id": handle.workflow_id}


@app.get("/result/{workflow_id}", response_model=WorkflowResult)
async def get_result(workflow_id: str) -> WorkflowResult:
    try:
        handle = await DBOS.retrieve_workflow_async(workflow_id)
    except DBOSNonExistentWorkflowError:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")

    status = (await handle.get_status()).status

    if status == "PENDING":
        return WorkflowResult(workflow_id=workflow_id, status="PENDING", output=None)

    output = await handle.get_result()
    return WorkflowResult(workflow_id=workflow_id, status=status, output=str(output))
