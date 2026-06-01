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
amber deploy
amber status
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
3. **Terraform apply** - deploy the full AWS stack with the pushed image tag
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
| `amber deploy` | Build and deploy to AWS |
| `amber config list` | Show project info and secret status |
| `amber config set <key>` | Set a secret in AWS |
| `amber status` | Show ECS health and deployed URLs |

## AWS Credentials

`amber deploy` uses the normal AWS credential chain through boto3, Terraform,
Docker ECR login, and the AWS APIs it calls. For AWS SSO, sign in with your
normal profile and put that profile in `amber.yaml`.

```bash
aws sso login --profile <your-profile>
```

```yaml
profile: <your-profile>
```

For pre-release testing, the bundled CloudFormation template can create a
manual IAM user and access key for deploys. It is a manual helper template, not
AWS SSO and not an `amber bootstrap` command.

```bash
aws configure --profile amber
```

```yaml
profile: amber
```

## Secrets

The CLI manages these secrets in AWS:

| Key | Store | Description |
|-----|-------|-------------|
| `openai-api-key` | SSM | OpenAI API key for LLM calls |
| `db` | Secrets Manager | Database connection URL managed by Terraform |

```bash
amber config set openai-api-key
amber config list
```

## Teardown Today

There is no `amber destroy` command in this cleanup pass. Destroy the generated
Terraform workspace directly:

```bash
cd .amber/terraform
terraform destroy
```
