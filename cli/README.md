# Amber CLI

> **Package name: `amber-runtime`.**
> This folder contains the CLI code. Users install the package, run the `amber`
> command, and write application code with `from amber import ...` via the SDK
> dependency.

Deploy durable AI agents to customer-owned AWS with one product command:

```bash
amber deploy
```

## Product Flow

Users install the package from PyPI, initialize a repo, review `amber.yaml`, and
deploy.

```bash
pip install amber-runtime
amber init
$EDITOR amber.yaml
amber auth setup
amber config set openai-api-key
amber deploy
amber admin create-user --email dev@example.com
amber status
```

Create the first dashboard admin user after `amber deploy`; the command reads
Terraform outputs from the deployed stack. Cognito sends the invite email with a
temporary password for `/admin/`.

`amber.yaml` is the user-facing deployment config. End users should not edit
Terraform variables directly for the normal product path. During deploy, the CLI
copies the bundled Terraform template into `.amber/terraform/` and generates
`.amber/terraform/terraform.tfvars` from `amber.yaml`.

```yaml
name: my-project

app: my_app.main:app
worker: my_app.main:agent_runtime
environment: dev

# Optional overrides:
# region: us-east-1
# profile: amber
# dashboard: true
# path_prefix: ""  # optional; current ASGI/Jinja apps own /
```

`environment: dev` keeps disposable defaults for local demos and testing.
`environment: prod` uses safer Terraform defaults for buckets, secrets, and RDS,
but still uses local Terraform state in this beta path.

### React frontend (optional)

By default the customer container owns `/` and serves its own UI (e.g. a
server-rendered Jinja app). If your product UI is a React single-page app instead,
keep it in a subdirectory with a `package.json` that declares `react`:

```
my-project/
  my_app/        # FastAPI app + AgentRuntime
  frontend/      # React SPA (package.json, vite.config.ts, src/, ...)
  amber.yaml
```

`amber init` detects it and records a `frontend:` block:

```yaml
frontend:
  type: react
  path: frontend       # frontend dir, relative to the repo root
  build: npm run build
  output: dist         # build output dir (vite -> dist, CRA -> build)
path_prefix: /api      # required for react: your API is served under /api
```

On `amber deploy` the SPA is built in a throwaway `node:20` container (so only
Docker is required — no host Node), then served at `/` from S3/CloudFront. Your
FastAPI app is reached under `/api/*`; the `/api` prefix is stripped before your
app, so you still write routes at the root (`/runs`, `/health`). Have the React
client call the API at `/api/...` — the build sets `VITE_BASE_PATH=/` and
`VITE_API_BASE_URL=/api`.

Route ownership stays separate from the Amber admin surface:

- `/` serves the customer app, or the customer React SPA when `frontend:` is set.
- `/api/*` is the developer app's public API surface behind CloudFront/ALB; the
  ALB blocks direct origin access with Amber's CloudFront origin verification
  header, but these routes are still reachable through the app's CloudFront URL.
- `/admin/*` serves the Amber admin React frontend.
- `/admin/api/*` serves the Amber dashboard backend, which enforces Cognito
  bearer auth before returning protected dashboard data.

Amber does not automatically wrap the developer app's `/api` routes in dashboard
Cognito auth, because many customer apps need public endpoints. If your `/api`
routes expose private data or mutations, enforce auth inside your app.

## Maintainer Flow

When changing the CLI package or bundled deploy assets, refresh assets before
building a wheel.

```bash
make cli-assets
make cli-wheelhouse
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

For release validation, publish `amber-sdk` first and then `amber-runtime` to
TestPyPI. Install from TestPyPI with real PyPI as the dependency fallback:

```bash
pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  amber-runtime
```

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
| `amber admin create-user --email <email>` | Create a Cognito dashboard admin user |
| `amber admin login` | Sign in for CLI workflow queries |
| `amber admin logout` | Clear the cached CLI dashboard session |
| `amber deploy` | Build and deploy to AWS |
| `amber destroy` | Tear down deployed AWS resources |
| `amber config list` | Show project info and secret status |
| `amber config set <key>` | Set a secret in AWS |
| `amber status` | Show ECS health and deployed URLs |
| `amber workflows list` | List deployed workflows |
| `amber workflows queued` | List queued workflows |
| `amber workflows show <workflow_id>` | Show workflow summary, steps, and events |

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

## Workflow Visibility

After deployment and first admin creation, sign in once for terminal workflow
queries:

```bash
amber admin login
amber workflows list
amber workflows queued
amber workflows show <workflow_id>
```

These commands read through the Cognito-protected dashboard API. Use `--json`
with workflow commands when another script or coding agent should consume the
raw response.

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
