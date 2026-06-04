# Amber SDK

`amber-sdk` is the Python library for defining durable Amber agent workflows in
customer applications. It provides the runtime object used by API and worker
processes, decorators for durable workflows and steps, and helpers for querying
workflow data.

## Install

```bash
pip install amber-sdk
```

Most deployment users install the full Amber CLI package instead:

```bash
pip install amber-runtime
```

`amber-runtime` depends on `amber-sdk`, so application code can use the SDK after
installing the CLI package.

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

Durable execution requires a DBOS system database. Set either `DB_URL` or
`DBOS_SYSTEM_DATABASE_URL` in the API and worker environments.

## Deploying

Use `amber-runtime` for the end-to-end product workflow:

```bash
pip install amber-runtime
amber init
amber deploy
```

See the repository README and CLI package documentation for the full deploy and
dashboard workflow.
