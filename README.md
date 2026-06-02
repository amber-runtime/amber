# Durable Execution Playground

## Repo Structure

This is a monorepo containing two publishable packages (`sdk/` and `cli/`) plus supporting infrastructure and a reference app. The root `pyproject.toml` (`amber-workspace`) is the uv workspace container — it is never published.

### Publishable packages

#### `sdk/` → publishes as `amber-sdk` on PyPI
The core runtime library. This is what customer agent apps import.

```
sdk/
  amber/               ← Python module (import name is "amber", not "amber-sdk")
    __init__.py        ← exports AgentRuntime, register_agent, step, sleep, etc.
    runtime.py         ← AgentRuntime, WorkerService, AgentService
    decorators.py      ← @register_agent, @step, @workflow, sleep
    worker.py          ← entrypoint for python -m amber.worker
    tracing.py
    dashboard/         ← internal queries used by dashboard backend
  pyproject.toml       ← name="amber-sdk"
```

How customers use it:
```python
from amber import AgentRuntime, register_agent, step, sleep
```
```bash
python -m amber.worker your_app.main:agent_runtime
```

#### `cli/` → publishes as `amber-runtime` on PyPI
The user-facing product package. Named `amber-runtime` (not `amber-cli`) because `pip install amber-runtime` is the single install command for users — it delivers the `amber` CLI command and pulls in `amber-sdk` as a dependency automatically. The folder is called `cli/` as a team abstraction; see `cli/README.md` for the full explanation.

```
cli/
  amber_cli/           ← internal CLI module (users never import this)
    main.py            ← click app entry point
    commands/
      init.py          ← amber init
      deploy.py        ← amber deploy
      config.py        ← amber config set/list
      status.py        ← amber status
    config_loader.py   ← amber.yaml parsing
  pyproject.toml       ← name="amber-runtime", depends on amber-sdk
```

How customers use it:
```bash
pip install amber-runtime   # installs CLI + SDK in one shot
amber init
amber deploy
```

### Supporting directories (not published to PyPI)

| Directory | Purpose |
|---|---|
| `dashboard/` | Split dashboard app with `frontend/` React SPA and `backend/` FastAPI service for observing workflow runs |
| `infra/` | Terraform, Docker, deploy scripts. Direction: scripts migrate into CLI; `infra/` becomes Terraform-only |
| `example_customer_app/` | Reference FastAPI app showing how to wire up Amber. Used for integration testing and CLI development. Will move to its own repo as the public quickstart |
| `tests/` | Integration and reliability tests |

### Key naming facts

- **`amber-runtime` depends on `amber-sdk`.** Publishing order matters: `amber-sdk` first, then `amber-runtime`.
- **Local dev:** `uv sync` at repo root installs both packages as editable local installs from `sdk/` and `cli/`. No PyPI needed for development.

---

**Current public API:**

```python
from amber import AgentRuntime, register_agent, workflow, step, sleep, agent_runner
```

| Function | What it does |
|---|---|
| `AgentRuntime` | Configure the API runtime, queue settings, and worker startup for registered agents |
| `@register_agent(name=...)` | Register a durable agent workflow; normal starts are queued by default |
| `@workflow()` | Mark a function as a durable workflow |
| `@step()` | Mark a function as a checkpointed step |
| `sleep(seconds)` | Durable sleep — skips elapsed time on crash recovery |
| `agent_runner(agent, prompt)` | Run an OpenAI Agents SDK agent through DBOS |

Agent workflows are registered when their modules are imported. In an app,
import the modules that define `@register_agent` workflows during startup.

## Queue-First Agents

Registered agents are queued by default. The API process submits work and returns
quickly; a worker process drains the DBOS queue and executes workflows. Use a
single `AgentRuntime` object in the app module so the API and worker roles share
the same queue configuration.

```python
from fastapi import FastAPI
from amber import AgentRuntime

from .user_agents import research_agent, travel_concierge

agent_runtime = AgentRuntime(
    queue_name="agent-runs",
    worker_concurrency=4,
    queue_concurrency=None,
)

app = FastAPI(lifespan=agent_runtime.api_lifespan())
agents = agent_runtime.agents

handle = await agents.start("research-handoff-agent", user_input)
return {"workflow_id": handle.workflow_id}
```

The API process launches DBOS with queue listeners disabled. The worker process
loads the same `AgentRuntime` object and listens to `agent-runs`.

`worker_concurrency` limits how many workflows each worker process runs at once.
It defaults to `4`. `queue_concurrency` is optional and unset by default; set it
when you need a global cap across all workers. Worker count itself is
deployment-owned: for ECS/Fargate, Terraform or Application Auto Scaling
controls how many worker tasks are running.

Effective parallelism is:

```text
min(worker_count * worker_concurrency, global_concurrency)
```

### Local Queue Demo

Use a DBOS database both processes can reach, then start the API:

```bash
uv run uvicorn example_customer_app.main:app --port 8003
```

Start the queue worker in another terminal:

```bash
uv run python -m amber.worker example_customer_app.main:agent_runtime
```

The API process launches DBOS with user queue listeners disabled. The worker
process launches its own DBOS runtime and listens to `agent-runs`.

Submit queued work:

```bash
curl -X POST 'http://localhost:8003/runs' \
  -H 'Content-Type: application/json' \
  -d '{"agent":"research-handoff-agent","input":"Prepare a research memo on AI dispatch copilots."}'
```

Poll the returned workflow ID:

```bash
curl 'http://localhost:8003/runs/<workflow_id>'
```

To test backlog behavior, stop the worker, submit a burst of queued runs, then
restart the worker and confirm the runs drain:

```bash
for i in {1..20}; do
  curl -s -X POST 'http://localhost:8003/runs' \
    -H 'Content-Type: application/json' \
    -d "{\"agent\":\"research-handoff-agent\",\"input\":\"Local queue test $i\"}" &
done
wait
```

For repeatable local queue load testing with k6 and a DBOS drain reporter, see
[`tests/load_testing/README.md`](tests/load_testing/README.md).

### AWS/Staging Contract

The SDK does not create AWS infrastructure. The deployment contract is:

- API service runs the FastAPI app, for example `uvicorn example_customer_app.main:app`.
- Worker service runs `python -m amber.worker example_customer_app.main:agent_runtime`.
- API and worker use the same code image/version.
- API and worker use the same `DBOS_SYSTEM_DATABASE_URL` or `DB_URL`.
- API and worker import the same registered workflow modules so DBOS application versions match.
- API runtime disables user queue listeners; worker runtime listens to `agent-runs`.
- ECS/Terraform controls worker task count, CloudWatch metrics, alarms, and autoscaling.

For a first AWS validation, submit a manual burst of queued runs and watch the
CloudWatch/ECS metrics: API enqueue latency, queue backlog, worker task count,
worker logs, completed workflows, and backlog drain time.

**Writing a new test:**

```python
from amber import Runtime, workflow, step

@step()
def call_external_api():
    # anything with side effects goes in a step
    ...

@workflow()
def my_workflow():
    result = call_external_api()
    return result

if __name__ == "__main__":
    runtime = Runtime(name="my-test")
    runtime.start()
    my_workflow()
```


## Using Postgres (optional)

By default the SDK uses SQLite, which is fine for local development. To use Postgres:

```bash
export CHECKPOINT_DB_URL=postgresql://user:password@localhost:5432/mydb
uv run python tests/event_booking.py
```

Or pass it directly:

```python
runtime = Runtime(name="my-app", db_url="postgresql://...")
runtime.start()
```
