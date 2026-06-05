# Amber CLI

Install `amber-runtime` to get the `amber` command for deploying durable AI
agents to customer-owned AWS. The package also installs `amber-sdk`, so your
application code can define agents with `from amber import ...`.

## Quickstart

Install the package, initialize a repo, review `amber.yaml`, configure AWS and
secrets, then deploy.

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

After setup, `amber deploy` runs the full deploy pipeline for your app, worker,
dashboard, database, and AWS infrastructure.

Create the first dashboard admin user after `amber deploy`; the command reads
Terraform outputs from the deployed stack. Cognito sends the invite email with a
temporary password for `/admin/`.

`amber.yaml` is the user-facing deployment config. End users should not edit
Terraform variables directly for the normal product path. During deploy, the CLI
copies the bundled Terraform template into `.amber/terraform/` and generates
`.amber/terraform/terraform.tfvars` from `amber.yaml`.

```amber.yaml
name: my-project

app: my_app.main:app
worker: my_app.main:agent_runtime
environment: dev

# Optional overrides:
# region: us-east-1
# profile: amber
# dashboard: true
# path_prefix: ""  # optional; server-rendered apps can serve / directly
```

`environment: dev` keeps disposable defaults for local demos and testing.
`environment: prod` uses safer Terraform defaults for buckets, secrets, and RDS,
but still uses local Terraform state in this path.

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

When `frontend:` is configured, `amber deploy` builds the React SPA in a
temporary `node:20` Docker container, so Docker is the only local build
requirement. The built SPA is served from S3/CloudFront at `/`.

Amber routes traffic by path:

- `/` serves the customer app or React SPA.
- `/api/*` reaches the customer FastAPI app. Amber strips the `/api` prefix, so
  app routes are still written as `/runs`, `/health`, and so on.
- `/admin/*` serves the Amber admin dashboard, which prompts admins to sign in with Cognito.
- `/admin/api/*` serves the Cognito-protected Amber dashboard API.

React clients should call the app API at `/api/...`. The frontend build sets
`VITE_BASE_PATH=/` and `VITE_API_BASE_URL=/api`.

Amber does not add dashboard Cognito auth to customer `/api` routes. If those
routes expose private data or mutations, enforce auth in your app.

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

Advanced deploy flags are available for development and troubleshooting, but the
supported full deploy path is `amber deploy`.

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
| `amber workflows list` | List deployed workflows for scripts and coding agents |
| `amber workflows queued` | List queued workflows for scripts and coding agents |
| `amber workflows show <workflow_id>` | Show workflow details for scripts and coding agents |

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

Coding agents can run the same read-only commands after `amber admin login` to
inspect deployed workflow state without direct AWS or database access:

```bash
amber workflows list --json
amber workflows queued --json
amber workflows show <workflow_id> --json
```

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

Destroying a prod stack requires an explicit confirmation flag:

```bash
amber destroy --allow-prod-data-loss
```

This prevents accidental prod teardown while still allowing deliberate cleanup
of test prod stacks.

## Terraform State

Amber stores Terraform state in `.amber/terraform/terraform.tfstate` for the
current project. Keep `.amber/` if you want this checkout to continue managing
the same deployed AWS stack, including future deploys and destroys.

If you delete `.amber/`, Amber loses the local Terraform state for that stack.
Use `amber destroy` before removing it when you want Amber to clean up the AWS
resources it created. Remote state support will be added when shared/team deploys
need it.
