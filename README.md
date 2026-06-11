# Amber

Amber deploys durable AI agents to developer owned AWS environments. It packages
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
  |-- /              -> Developer UI or app server
  |-- /api/*         -> Developer FastAPI app on ECS
  |-- /admin/*       -> Amber dashboard SPA on S3
  |-- /admin/api/*   -> Amber dashboard API on ECS
                           |
                           v
                     Cognito-protected
                     operator access

ECS Fargate
  |-- Developer-app    -> FastAPI + AgentRuntime
  |-- Developer-worker -> private queue worker
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

First, make your agent app Amber-ready with the SDK: define an `AgentRuntime`,
register agent workflows with `@register_agent`, and expose the runtime target
your worker will use. See [`sdk/README.md`](sdk/README.md) for copyable FastAPI
and agent examples. Once your app has that shape, use the CLI to initialize and
deploy it.

```bash
pip install amber-runtime

# Run from the repo that contains your Amber-ready FastAPI app
amber init

# Review amber.yaml

amber auth setup
amber config set openai-api-key
amber deploy
amber admin create-user --email dev@example.com
amber status
```

For command details, deployment config, dashboard admin setup, and workflow
inspection, see [`cli/README.md`](cli/README.md).

`amber deploy` builds and deploys your application API, queue worker, Amber
dashboard, database, and AWS infrastructure. Create the first dashboard admin
user after `amber deploy`; the command reads Terraform outputs from the deployed
stack and Cognito sends the invite email.

For a complete runnable app that already has the SDK shape and deploy config, use
[`amber-example-app`](https://github.com/amber-runtime/amber-example-app)

## Development

This repository contains the Amber SDK, CLI, dashboard, infrastructure template,
and tests. Product users should start with the quickstart above and if you want
more details you can use the package-specific READMEs for deeper implementation details:

- [`cli/README.md`](cli/README.md) - CLI commands, deploy pipeline, auth, and state
- [`sdk/README.md`](sdk/README.md) - Python SDK API and application shape
- [`infra/README.md`](infra/README.md) - Terraform template and AWS architecture

The published package names are:

- `amber-sdk` - Python library installed as the `amber` module
- `amber-runtime` - Product package that installs the `amber` CLI and depends on `amber-sdk`
