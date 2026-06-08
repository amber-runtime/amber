# Amber SDK

`amber-sdk` is the Python library for defining durable Amber agent workflows in
your agent applications. It provides the runtime object used by API and worker
processes, plus decorators for durable workflows and steps.

## Install

If you are deploying with Amber, install the full product package:

```bash
pip install amber-runtime
```

`amber-runtime` includes the `amber` CLI and depends on `amber-sdk`, so
application code can use `from amber import ...`.

Install `amber-sdk` directly only when you need the Python library without the
CLI:

```bash
pip install amber-sdk
```

## DB URL

Durable execution requires a Postgres database. Amber uses this database to store
workflow state so queued runs, steps, and sleeps can recover cleanly after
restarts. Set `DB_URL` in both the API and worker environments.

## Public API

Most agent applications use these imports from the `amber` module:

```python
from amber import (
    AgentRuntime,
    agent_runner,
    register_agent,
    sleep,
    step,
    workflow,
)
```

`AgentRuntime` is the recommended entry point for agent applications. The API
process uses it to enqueue agent runs, and the worker process uses it to execute
those queued runs.

`agent_runner` runs OpenAI Agents SDK agents inside Amber workflows. Use it from
registered agents or workflow/step code when invoking an OpenAI agent. Amber
wraps the call so agent execution fits the same durable workflow model as the
rest of the app.

`@register_agent`, `@workflow`, and `@step` mark durable units of work, while
`sleep` provides durable sleeps that recover cleanly after restarts.

## Application Shape

Amber applications define a normal Python app and an agent runtime target, then
deploy with the `amber` CLI.

```python
from fastapi import FastAPI
from amber import AgentRuntime, register_agent, step

agent_runtime = AgentRuntime(
    queue_name="agent-runs",
)

app = FastAPI(lifespan=agent_runtime.api_lifespan())


@step()
async def draft_answer(prompt: str) -> str:
    return f"Draft answer for: {prompt}"


@register_agent(name="support-agent")
async def support_agent(prompt: str) -> str:
    return await draft_answer(prompt)


@app.post("/runs")
async def start_run(payload: dict[str, str]) -> dict[str, str]:
    handle = await agent_runtime.agents.start(
        "support-agent",
        payload["input"],
    )
    return {"workflow_id": handle.workflow_id}
```

If agents are defined in the same module as `agent_runtime`, no `agent_modules`
setting is needed. If agents live in separate files, import those modules in the
backend module so `@register_agent` runs before API requests enqueue work, and
list the same modules in `AgentRuntime(agent_modules=[...])` so the worker
imports them when it starts.

```python
# my_app/agents.py
from amber import register_agent


@register_agent(name="research-assistant")
async def research(topic: str) -> str:
    ...
```

```python
# my_app/main.py
from fastapi import FastAPI
from amber import AgentRuntime
from . import agents  # registers @register_agent workflows

agent_runtime = AgentRuntime(
    agent_modules=["my_app.agents"],
    queue_name="agent-runs",
)

app = FastAPI(lifespan=agent_runtime.api_lifespan())
```

Use `agent_runner` inside registered agents when calling an OpenAI agent. This
code usually lives in the separate agent module:

```python
# my_app/separate_agent_file.py
from agents import Agent
from amber import agent_runner, register_agent

research_agent = Agent(
    name="Research Agent",
    instructions="Research the user request and return a concise answer.",
)


@register_agent(name="research-assistant")
async def research(topic: str) -> str:
    result = await agent_runner(
        starting_agent=research_agent,
        input=f"Research this topic: {topic}",
    )
    return str(result.final_output)
```

Run the API process with your ASGI server:

```bash
uvicorn my_app.main:app
```

Run a worker process against the same `AgentRuntime` target:

```bash
python -m amber.worker my_app.main:agent_runtime
```

## Worker Concurrency

`worker_concurrency` defaults to `8`. To change how many workflows each worker
process can run at once, set `worker_concurrency=<number>` on `AgentRuntime`.

`queue_concurrency` defaults to `None`, meaning there is no global cap for the
queue. Set `queue_concurrency=<number>` only when you need a maximum concurrency
across workers.

The number of worker processes is controlled by however you run or deploy
workers, not by SDK queue settings.

```python
agent_runtime = AgentRuntime(
    queue_name="agent-runs",
    worker_concurrency=16,
    queue_concurrency=64,
)
```

## Deploying

Use `amber-runtime` for the end-to-end product workflow:

```bash
pip install amber-runtime
amber init
amber deploy
```

See the `amber-runtime` package documentation for deployment, dashboard access,
and workflow visibility.
