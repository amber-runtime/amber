# Local Queue Load Testing

This runbook validates the local DBOS queue path:

```text
k6 -> POST /runs -> DBOS queue -> tests.load_testing.load_worker -> workflow states
```

Use `synthetic-queue-agent` for load tests. It performs durable sleep work and
does not call OpenAI, so the test measures queue behavior instead of model
latency, rate limits, or token cost.
The load-test API and worker import only the synthetic agent from this folder;
they do not import the normal customer app agents.

## Prerequisites

Use one dedicated DBOS database for every load-test process. The load-test API,
worker, and reporter read `.env.load-test` so the normal customer app database
in `.env` is not used by accident.

### Option 1: Using .env.load-test (Recommended)

```bash
cd tests/load_testing
cp .env.load-test.example .env.load-test
```

Edit `tests/load_testing/.env.load-test` and set `LOAD_TEST_DB_URL` to a database
that is safe to fill with synthetic workflow history:

```bash
LOAD_TEST_DB_URL='postgresql://postgres:password@localhost:5432/dbos_load_test'
LOAD_TEST_RUNTIME_NAME=amber-load-test
```

### Option 2: Using Environment Variables

Alternatively, export environment variables for a single command:

```bash
export LOAD_TEST_DB_URL='postgresql://postgres:password@localhost:5432/dbos_load_test'
export LOAD_TEST_RUNTIME_NAME=amber-load-test
```

Install k6 if it is not already available:

```bash
brew install k6
```

## Start the API

Terminal 1:

```bash
uv run uvicorn tests.load_testing.load_app:app --port 8004
```

The load-test API registers `synthetic-queue-agent` and starts DBOS with queue
listeners disabled, so it can enqueue work but does not drain `agent-runs`.

## Watch Queue Drain

Terminal 2, start the reporter immediately before running k6:

```bash
uv run python tests/load_testing/scripts/queue_drain_report.py --min-total 20 --timeout 300
```

The reporter watches workflows created after it starts and prints counts for
`ENQUEUED`, `PENDING`, `SUCCESS`, `ERROR`, and `CANCELLED`.

## Generate Enqueue Load

Terminal 3:

```bash
API_URL=http://localhost:8004 k6 run tests/load_testing/k6/queue-enqueue.k6.js
```

Useful overrides:

```bash
API_URL=http://localhost:8004 REQUESTS=100 VUS=20 SLEEP_SECONDS=5 k6 run tests/load_testing/k6/queue-enqueue.k6.js
API_URL=http://localhost:8004 REQUESTS=50 k6 run tests/load_testing/k6/queue-enqueue.k6.js
```

k6 validates enqueue latency and response shape. The reporter validates DBOS
queue state and drain behavior.

## Worker Scenarios

No worker:

```bash
API_URL=http://localhost:8004 REQUESTS=20 k6 run tests/load_testing/k6/queue-enqueue.k6.js
```

Expected reporter behavior: submitted workflows remain `ENQUEUED`.

For normal app development, `example_customer_app.worker` is the clean worker
template. For load testing, use `tests.load_testing.load_worker`; it reads
concurrency settings from env vars so you can change them without editing the
template.

One load-test worker, one active workflow:

```bash
uv run python -m tests.load_testing.load_worker
```

Expected reporter behavior: max `PENDING` is about `1`.

Two load-test worker processes:

```bash
uv run python -m tests.load_testing.load_worker
uv run python -m tests.load_testing.load_worker
```

Expected reporter behavior: max `PENDING` is about `2`.

One load-test worker, higher per-worker concurrency:

```bash
WORKER_CONCURRENCY=3 uv run python -m tests.load_testing.load_worker
```

Expected reporter behavior: max `PENDING` is about `3`.

Multiple load-test workers with a global queue cap:

```bash
WORKER_CONCURRENCY=4 QUEUE_CONCURRENCY=4 uv run python -m tests.load_testing.load_worker
WORKER_CONCURRENCY=4 QUEUE_CONCURRENCY=4 uv run python -m tests.load_testing.load_worker
```

Expected reporter behavior: max `PENDING` stays around `4`.

`QUEUE_CONCURRENCY` is the global queue cap and must be greater than or equal
to `WORKER_CONCURRENCY`.

## Interpreting Results

The useful values are:

- `ENQUEUED`: backlog waiting for a worker.
- `PENDING`: actively running workflows.
- `SUCCESS`: completed workflows.
- `max_pending`: observed active concurrency.
- `drain_seconds`: time from first observed workflow to all watched workflows becoming terminal.
- `throughput`: completed workflows per second over the drain window.

For local queue correctness, `max_pending` should roughly match:

```text
min(worker_processes * WORKER_CONCURRENCY, QUEUE_CONCURRENCY if set)
```

For a worker restart check, enqueue work, stop a worker while workflows are
active, restart it, and confirm the reporter eventually reaches `SUCCESS`.
