# Amber SDK

`amber-sdk` is the Python library for defining durable Amber agent workflows in
customer applications. It provides the runtime object used by API and worker
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

## Public API

The package installs the `amber` Python module:

```python
from amber import (
    AgentRuntime,
    Runtime,
    WorkerService,
    agent_runner,
    register_agent,
    sleep,
    step,
    workflow,
)
```

`AgentRuntime` is the high-level API and worker runtime for agent apps.
`@register_agent`, `@workflow`, and `@step` mark durable units of work, while
`sleep` provides durable sleeps that recover cleanly after restarts.

## Application Shape

Amber applications define a normal Python app and an agent runtime target, then
deploy with the `amber` CLI.

```python
from fastapi import FastAPI
from amber import AgentRuntime, register_agent, step

agent_runtime = AgentRuntime(
    agent_modules=["my_app.agents"],
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

Run the API process with your ASGI server:

```bash
uvicorn my_app.main:app
```

Run a worker process against the same `AgentRuntime` target:

```bash
python -m amber.worker my_app.main:agent_runtime
```

Durable execution requires a Postgres database for DBOS state. Set `DB_URL` in
both the API and worker environments.

## Deploying

Use `amber-runtime` for the end-to-end product workflow:

```bash
pip install amber-runtime
amber init
amber deploy
```

See the `amber-runtime` package documentation for deployment, dashboard access,
and workflow visibility.
