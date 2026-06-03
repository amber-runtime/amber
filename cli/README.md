# Amber CLI

> **Current package name: `amber-runtime`.**
> This folder contains the CLI code. The team is still validating the final
> package naming, but local product packaging uses `amber-runtime`: users install
> the package, run the `amber` command, and write application code with
> `from amber import ...` via the SDK dependency.

Deploy durable AI agents to customer-owned AWS with one product command:

```bash
amber deploy
```

## Product Flow

Beta users install the built wheel, initialize a repo, review `amber.yaml`, and
deploy.

```bash
pip install amber-runtime
amber init
$EDITOR amber.yaml
amber auth setup
amber config set openai-api-key
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
environment: dev

# Optional overrides:
# region: us-east-1
# profile: amber
# dashboard: true
```

`environment: dev` keeps disposable defaults for local demos and testing.
`environment: prod` uses safer Terraform defaults for buckets, secrets, and RDS,
but still uses local Terraform state in this beta path.

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
the SDK wheel, and the dashboard frontend dist.

For a near-product local packaging smoke test:

```bash
AMBER_RUN_PACKAGE_SMOKE=1 uv run pytest cli/tests/test_local_package_smoke.py
```

This builds local wheels, installs `amber-runtime` into a fresh virtualenv, runs
`amber --help`, initializes a temporary customer repo, and confirms deploy
preflight starts from the installed package. It does not publish anything to
PyPI.

## Deploy Pipeline

`amber deploy` runs a preflight before mutating AWS. It validates `amber.yaml`,
local tools, packaged assets, importability of the configured app/worker targets,
AWS auth, and the OpenAI API key secret.

After preflight, `amber deploy` runs five steps:

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

`amber auth setup` is the first-time AWS SSO / IAM Identity Center setup
command. It runs the AWS CLI SSO wizard, signs in, verifies the selected
identity, and writes the selected `profile` and `region` into `amber.yaml`.

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

Prod stacks require an explicit testing escape hatch:

```bash
amber destroy --allow-prod-data-loss
```

This prevents accidental prod teardown while still allowing deliberate cleanup
of test prod stacks.

## Terraform State

For this local/beta phase, Terraform state lives in
`.amber/terraform/terraform.tfstate`. Keep `.amber/` around if you want the same
machine to run future deploys or destroys. AWS-backed remote state is deferred
until the production/multi-user deploy story is ready.
