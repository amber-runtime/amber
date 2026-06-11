# Amber

Amber deploys durable AI agents to customer-owned AWS environments. It packages
your FastAPI app, queue worker, dashboard, database, and cloud infrastructure
behind one CLI workflow while keeping your application code in a normal Python
project.

Amber gives agent apps:

- Durable workflow execution with checkpointed steps and recoverable sleeps
- Queue-first agent runs with separate API and worker processes
- An operator dashboard protected by Cognito
- AWS deployment with ECS, RDS/RDS Proxy, CloudFront, S3, ECR, SSM, and Secrets Manager

## Architecture At A Glance

Amber deploys your agent app into your AWS account with a managed runtime shape:

```text
Users / Operators
      |
      v
CloudFront
  |-- /              -> Customer UI or app server
  |-- /api/*         -> Customer FastAPI app on ECS
  |-- /admin/*       -> Amber dashboard SPA on S3
  |-- /admin/api/*   -> Amber dashboard API on ECS
                           |
                           v
                     Cognito-protected
                     operator access

ECS Fargate
  |-- customer-app    -> FastAPI + AgentRuntime
  |-- customer-worker -> private queue worker
  |-- dashboard-api   -> workflow visibility + admin API

Data + Operations
  |-- RDS Proxy + Postgres       -> durable workflow state
  |-- SSM / Secrets Manager      -> app and database secrets
  |-- CloudWatch Metrics         -> queue observability
  |-- Application Auto Scaling   -> worker scaling
```

Your app owns its public routes. Amber adds the dashboard, queue worker,
database, secrets, and AWS infrastructure around it. For the full Terraform
resource map, see [`infra/README.md`](infra/README.md).

## Quickstart

Install the product package, initialize a repo, configure AWS and secrets, then
deploy.

```bash
pip install amber-runtime
amber init

# Review amber.yaml

amber auth setup
amber config set openai-api-key
amber deploy
amber admin create-user --email dev@example.com
amber status
```

`amber deploy` builds and deploys your application API, queue worker, Amber
dashboard, database, and AWS infrastructure. Create the first dashboard admin
user after `amber deploy`; the command reads Terraform outputs from the deployed
stack and Cognito sends the invite email.

For a complete runnable sample app, use
[`amber-example-app`](https://github.com/amber-runtime/amber-example-app) once it
is published and moved out of this repository.

## How Amber Works

Amber applications define one `AgentRuntime` in the app module. The API process
uses that runtime to enqueue agent workflows quickly; the worker process loads
the same runtime target and drains the durable queue.

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

For more details on how amber works please look at [`sdk/README.md`](sdk/README.md).

Run the API locally with your ASGI server:

```bash
uvicorn my_app.main:app
```

Run the worker against the same runtime target:

```bash
python -m amber.worker my_app.main:agent_runtime
```

Both processes need the same database URL. Use `DB_URL` as the public app
environment variable.

## Local Dashboard

For local development, serve the packaged Amber dashboard from the CLI:

```bash
export DB_URL=postgresql://...
uvicorn my_app.main:app
amber dashboard dev
```

Open the local dashboard at:

```text
http://localhost:8765/admin/
```

The local dashboard reads workflow data from `DB_URL` and does not use AWS,
Cognito, or CloudFront. The deployed dashboard is still created by
`amber deploy`, served at `/admin/`, and protected by Cognito.

## `amber.yaml`

`amber init` writes the user-facing deploy config:

```yaml
name: my-project

app: my_app.main:app
worker: my_app.main:agent_runtime
environment: dev

# Optional overrides:
# region: us-east-1
# profile: amber
# dashboard: true
# path_prefix: ""
```

End users should edit `amber.yaml`, not Terraform variables. During deploy,
Amber copies the bundled Terraform template into `.amber/terraform/` and
generates `.amber/terraform/terraform.tfvars` from `amber.yaml`.

`environment: dev` uses disposable defaults for demos and testing.
`environment: prod` uses safer defaults for buckets, secrets, and RDS, but the
current local/beta path still stores Terraform state in `.amber/terraform/`.

## React Frontend

By default your application container owns `/` and can serve its own UI. If your
product UI is a React single-page app, keep it in a subdirectory with a
`package.json` that declares `react`:

```text
my-project/
  my_app/        # FastAPI app + AgentRuntime
  frontend/      # React SPA
  amber.yaml
```

`amber init` detects the frontend and records:

```yaml
frontend:
  type: react
  path: frontend
  build: npm run build
  output: dist
path_prefix: /api
```

With a React frontend, Amber serves the built SPA from S3/CloudFront at `/` and
routes your FastAPI app under `/api/*`. Amber strips `/api` before requests reach
your app, so routes are still written as `/runs`, `/health`, and so on.

Amber routes:

- `/` serves your application UI or React SPA
- `/api/*` reaches your FastAPI app
- `/admin/*` serves the Amber dashboard
- `/admin/api/*` serves the Cognito-protected dashboard API

Amber does not add dashboard Cognito auth to your application `/api` routes. If
those routes expose private data or mutations, enforce auth in your app.

## Dashboard And Workflows

After deployment, create an admin user:

```bash
amber admin create-user --email dev@example.com
```

The dashboard is served at `/admin/` and uses Cognito for operator sign-in.

For terminal workflow visibility, sign in once and query through the same
Cognito-protected dashboard API:

```bash
amber admin login
amber workflows list
amber workflows queued
amber workflows show <workflow_id>
```

Use `--json` when another script or coding agent should consume the raw response.

## Secrets

The CLI manages deployment secrets in AWS:

| Key | Store | Description |
|-----|-------|-------------|
| `openai-api-key` | SSM Parameter Store | OpenAI API key for LLM calls |
| `db` | Secrets Manager | Database connection URL managed by Terraform |

Set the OpenAI key before deploy:

```bash
amber config set openai-api-key
amber deploy
```

After a deployment is already running, rotate or replace the key with:

```bash
amber config set openai-api-key
amber deploy --no-build
amber config list
```

## Teardown

Destroy the AWS resources created by `amber deploy`:

```bash
amber destroy
```

Use `amber destroy --yes` for non-interactive cleanup. The command keeps local
project config in `amber.yaml`; to fully reset local Amber config after
destroying cloud resources, remove `amber.yaml` and `.amber/`.

Destroying a prod stack requires an explicit confirmation flag:

```bash
amber destroy --allow-prod-data-loss
```

## Development

This repository contains the Amber SDK, CLI, dashboard, infrastructure template,
and tests. Product users should start with the quickstart above and if you want
more details you can use the package-specific READMEs for deeper implementation details:

- [`cli/README.md`](cli/README.md) - CLI commands, deploy pipeline, auth, and state
- [`sdk/README.md`](sdk/README.md) - Python SDK API and application shape
- [`infra/README.md`](infra/README.md) - Terraform template and AWS architecture

Local development uses the root `uv` workspace:

```bash
uv sync
```

The published package names are:

- `amber-sdk` - Python library installed as the `amber` module
- `amber-runtime` - Product package that installs the `amber` CLI and depends on `amber-sdk`
