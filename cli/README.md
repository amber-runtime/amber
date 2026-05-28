# Amber CLI

Deploy and manage durable AI agents.

## Install

```bash
cd cli/
pip install -e .
```

## Usage

```bash
# Initialize a project (creates amber.yaml)
amber init --name my-project

# Set secrets
amber config set openai-api-key
amber config set dbos-conductor-key

# Check what's configured
amber config list

# Full deploy (terraform + docker build + ECS restart + frontend)
amber deploy

# Check everything is healthy
amber status

# Partial deploys
amber deploy --no-infra       # skip terraform
amber deploy --no-build       # skip docker build/push
amber deploy --no-frontend    # skip dashboard frontend
amber deploy --service customer-app  # build one service only
```

## Commands

| Command | Description |
|---------|-------------|
| `amber init` | Create amber.yaml with sensible defaults |
| `amber deploy` | Build and deploy to AWS |
| `amber config list` | Show project info and secrets status |
| `amber config set <key>` | Set a secret (SSM/Secrets Manager) |
|| `amber status` | Show ECS health, registered agents, URLs | |

## amber.yaml

The single source of truth for project configuration:

```yaml
name: my-project

# Agents are auto-detected from @agent decorators.
# Override here if needed:
# agents:
#   - my-agent

# Optional overrides (sensible defaults provided):
# region: us-east-1
# environment: dev
# dashboard: true
```

## Secrets

The CLI manages these secrets in AWS:

| Key | Store | Description |
|-----|-------|-------------|
| `openai-api-key` | SSM | OpenAI API key for LLM calls |
| `dbos-conductor-key` | SSM | DBOS Conductor token |
| `db` | Secrets Manager | Database connection (read-only, AWS-managed) |

## Deploy Pipeline

`amber deploy` runs four steps in order:

1. **Terraform** — apply infrastructure changes
2. **Docker** — build images and push to ECR
3. **ECS** — force new deployment for both services
4. **Frontend** — build React dashboard, sync to S3, invalidate CloudFront

The deploy command also auto-updates `dashboard/.env.production` with the current
CloudFront domain from terraform output, so fresh deploys always get the right URLs.
