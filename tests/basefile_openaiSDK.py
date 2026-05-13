import os
from pathlib import Path

from agents import Agent
from dbos import DBOS, SetWorkflowID
from dbos._error import DBOSNonExistentWorkflowError
from dbos_openai_agents import DBOSRunner
from dotenv import load_dotenv
from fastapi import FastAPI, Path as FastAPIPath
from pydantic import BaseModel
from sdk import workflow, step, init

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

app = FastAPI()

agent = Agent(
    name="demo-agent",
    instructions="You are a helpful assistant. Keep responses short and clear.",
)


class AgentRequest(BaseModel):
    message: str


class AgentResponse(BaseModel):
    workflow_id: str
    output: str


@step()
def example_step(message: str) -> str:
    print(message)


@workflow()
async def run_agent(message: str) -> dict[str, str]:
    example_step("step one")
    result = await DBOSRunner.run(agent, message)
    return {
        "workflow_id": DBOS.workflow_id,
        "output": str(result.final_output),
    }


@app.on_event("startup")
async def startup() -> None:
    init(
        name=os.environ.get("DBOS_APP_NAME", "agent-demo"),
        db_url=os.environ.get("DBOS_SYSTEM_DATABASE_URL"),
        conductor_key=os.environ.get("DBOS_CONDUCTOR_KEY"),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


"""
The two functions on the bottom are for testing purpose on swagger. So you don't
have to curl responses and workflow id name.
"""


@app.post("/agent/{workflow_id}", response_model=AgentResponse)
async def agent_endpoint(
    request: AgentRequest,
    workflow_id: str = FastAPIPath(
        default=...,
        examples=["demo-1"],
        description="Use a new ID for each fresh workflow run.",
    ),
) -> AgentResponse:
    return await run_agent_workflow(workflow_id, request.message)


async def run_agent_workflow(workflow_id: str, message: str) -> AgentResponse:
    try:
        handle = await DBOS.retrieve_workflow_async(workflow_id)
    except DBOSNonExistentWorkflowError:
        with SetWorkflowID(workflow_id):
            handle = await DBOS.start_workflow_async(run_agent, message)

    result = await handle.get_result()
    return AgentResponse(**result)
