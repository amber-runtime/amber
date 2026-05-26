# Durable Execution Playground

## Testing dashboard backend (without phoenix + using postgres)
Setup
  1. Make sure `.env` has:
     DBOS_SYSTEM_DATABASE_URL=postgresql://...
     OPENAI_API_KEY=...

 Run
 Run the agent (pick any topic)
  uv run tests/research_agent.py "your topic here"

  Start the backend
  uv run uvicorn dashboard.dashboard_backend:app --reload --port 8001

Test
   Open http://localhost:8001/docs
   GET /workflows?limit=1   → grab the workflow_uuid
   GET /workflows/{uuid}    → see the full JOIN with LLM + step data

A development space for building and testing our SDK — a durable execution wrapper over DBOS for agents and agentic workflows.

## Structure

```
playground/
├── sdk/          # the SDK library (edit this to develop)
│   └── src/sdk/
│       ├── __init__.py
│       ├── decorators.py   # workflow, step, sleep, register_agent
│       ├── runtime.py      # Runtime, AgentService, WorkerService
│       └── dashboard/      # dashboard backend helpers
├── tests/        # test scripts that use the SDK
└── deprecated/   # prior reference implementations (Inngest, raw DBOS)
```

## Prerequisites

**1. Install uv**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2a. Create env file**
```bash
cp env.example .env

```

**2b. Set your OpenAI key**
```bash
OPENAI_API_KEY=sk-...
```

**3. Install dependencies**
```bash
cd playground

// activate virtual env
source .venv/bin/activate

uv sync

// To deactivate virtual env
deactivate
```



This installs all dependencies including the `sdk` package in editable mode — changes to `sdk/` are reflected immediately without reinstalling.

## Running Tests

All test scripts are in `tests/`. Run them with `uv run` from the `playground/` root:

```bash
# Two steps and a durable sleep
uv run python tests/counter.py

# Test a workflow
uv run python tests/event_booking.py
```

> By default, tests use SQLite as the system database (no setup needed). A file named `[app-name].sqlite` is created in the directory you run from.

## Developing the SDK

The SDK lives in `sdk/src/sdk/`. Since it's installed as an editable package, you can edit it and re-run tests without any reinstall step.

**Current public API:**

```python
from sdk import Runtime, AgentService, WorkerService, workflow, step, sleep, agent_runner
```

| Function | What it does |
|---|---|
| `@workflow()` | Mark a function as a durable workflow |
| `@step()` | Mark a function as a checkpointed step |
| `sleep(seconds)` | Durable sleep — skips elapsed time on crash recovery |
| `agent_runner(agent, prompt)` | Run an OpenAI Agents SDK agent through DBOS |
| `Runtime.start()` | Configure and launch DBOS once for the current process |
| `AgentService.run(agent_name, input)` | Start a registered orchestration workflow immediately |
| `AgentService.enqueue(agent_name, input)` | Submit a registered orchestration workflow to the default DBOS queue |
| `WorkerService.run()` | Launch a queue worker for registered orchestration workflows |

Agent workflows are registered when their modules are imported. In an app,
import the modules that define `@register_agent` workflows during startup.

## Queueing Agents

Use `AgentService.run(...)` when the API process should start work immediately.
Use `AgentService.enqueue(...)` when the API should return quickly and let a
worker process drain queued work. In a split deployment, initialize the API
runtime with `listen_queues=[]` so it can enqueue work without draining user
queues. `AgentService.enqueue(...)` lazily ensures the queue exists so app/API
processes can submit background work before any worker has started. Queue
configuration is still owned by the worker runtime; enqueue submission does not
require an active worker, but queued work will not execute until a worker
runtime is running and listening on the queue.

API-side enqueue:

```python
from sdk import AgentService, Runtime

runtime = Runtime()
runtime.start(listen_queues=[])
agents = AgentService(runtime)

handle = await agents.enqueue("research-handoff-agent", user_input)
return {"workflow_id": handle.workflow_id}
```

Worker-side template:

```python
from sdk import Runtime, WorkerService

worker = WorkerService(
    runtime=Runtime(),
    agent_modules=[
        "my_app.agents.single_agent_demo",
        "my_app.agents.multi_agent_demo",
        "my_app.agents.queued_multi_agent_demo",
    ],
    queue_name="agent-runs",
    worker_concurrency=1,
)
worker.run()
```

In split deployments, the API and worker should import the same registered
workflow modules so DBOS computes the same application version. Queue listening
still controls what the worker drains: the worker only listens to `agent-runs`.

`worker_concurrency` limits how many queued workflows each worker process runs at
once. The optional `concurrency` argument sets a global queue cap across all
workers. Worker count itself is deployment-owned: for ECS/Fargate, Terraform or
Application Auto Scaling controls how many worker tasks are running.

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
uv run python -m example_customer_app.worker
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
- Worker service runs `python -m example_customer_app.worker`.
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
from sdk import Runtime, workflow, step

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
