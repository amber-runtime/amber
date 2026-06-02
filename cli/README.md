# Amber CLI

> **Published to PyPI as `amber-runtime`.**
> This folder contains the CLI code. The package is named `amber-runtime` because
> `pip install amber-runtime` is the single install command users run to get both
> the CLI (`amber` command) and the SDK (`from amber import ...`) via its dependency on `amber-sdk`.

Deploy durable AI agents to customer-owned AWS with one product command:

```bash
amber deploy
```

## Product Flow

Beta users install the built wheel, initialize a repo, edit `amber.yaml`, and
deploy.

```bash
amber init
$EDITOR amber.yaml
amber auth setup
amber deploy
amber status
amber destroy
```

`amber.yaml` is the user-facing deployment config. End users should not edit
Terraform variables directly for the normal product path. During deploy, the CLI
copies the bundled Terraform template into `.amber/terraform/` and generates
`.amber/terraform/terraform.tfvars` from `amber.yaml`.

```yaml
name: my-project

app: my_app.main:app
worker: my_app.main:agent_runtime
path_prefix: /api

# Optional overrides:
# region: us-east-1
# environment: dev
# profile: amber
# dashboard: true
```

## Maintainer Flow

When changing the CLI package or bundled deploy assets, refresh assets before
building a wheel.

```bash
make cli-assets
cd cli
uv build
```

For a local product smoke test from this repo:

```bash
make cli-assets
uv run amber deploy
```

The packaged assets include Terraform, Docker templates, Docker entrypoints,
the SDK wheel, the dashboard frontend dist, and the manual IAM helper
CloudFormation template.

## Deploy Pipeline

`amber deploy` runs five steps:

1. **ECR bootstrap** - create the ECR repositories before image push
2. **Docker** - stage contexts, build images, and push to ECR
3. **Terraform apply** - deploy the full AWS stack with a fresh image tag so ECS rolls onto the current code
4. **Frontend** - sync bundled React dashboard assets to S3 and invalidate CloudFront
5. **Summary** - print dashboard and API URLs

Partial flags exist for development, but the supported full deploy path is
`amber deploy`.

```bash
amber deploy --no-infra
amber deploy --no-build
amber deploy --no-frontend
amber deploy --service customer-app
```

## Commands

| Command | Description |
|---------|-------------|
| `amber init` | Create `amber.yaml` with app and worker entrypoints |
| `amber auth setup` | Configure AWS access for deploys |
| `amber auth login` | Refresh the saved AWS SSO session |
| `amber auth check` | Verify the configured AWS profile |
| `amber deploy` | Build and deploy to AWS |
| `amber destroy` | Tear down deployed AWS resources |
| `amber config list` | Show project info and secret status |
| `amber config set <key>` | Set a secret in AWS |
| `amber status` | Show ECS health and deployed URLs |

## AWS Credentials

`amber auth setup` is the friendly AWS setup command. It recommends AWS SSO /
IAM Identity Center, can guide users through the bundled CloudFormation IAM
helper when they only have AWS Console admin access, and can verify an existing
AWS profile.

```bash
amber auth setup
```

For returning SSO users whose session expired:

```bash
amber auth login
```

To check the currently configured profile:

```bash
amber auth check
```

`amber auth setup` writes the selected `profile` and `region` into `amber.yaml`.
It never writes secrets into `amber.yaml`.

## Secrets

The CLI manages these secrets in AWS:

| Key | Store | Description |
|-----|-------|-------------|
| `openai-api-key` | SSM | OpenAI API key for LLM calls |
| `db` | Secrets Manager | Database connection URL managed by Terraform |

```bash
amber init
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
destroying cloud resources, run `rm amber.yaml && rm -rf .amber`.
