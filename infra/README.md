# Infrastructure

Canonical Terraform template for Amber's AWS deploy path.

The supported full deployment path is `amber deploy`. This directory remains
useful for validating and reviewing the AWS resources the CLI packages, but it
does not build Docker images, push to ECR, restart ECS services, or sync the
frontend. The CLI owns those product deployment steps.

## Architecture

```
                    CloudFront (HTTPS)
                           |
              +------------+------------+
              |            |            |
          / (root)    /admin/*    /admin/api/*, /api/*
              |            |            |
              v            v            v
             ALB        S3 SPA         ALB
              |        (admin)          |
              |            +------------+
              |            |
              v            v
       customer-app:8003   dashboard-api:8001
 (FastAPI + DBOS + OpenAI Agents)  (FastAPI + DBOS)
                    |                   |
                    |        customer-worker:8004
                    |     (DBOS queue consumer)
                    |                   |
                    +---------+---------+
                              v
                          RDS Proxy
                              |
                              v
                        RDS Postgres 16

                    customer-worker:8004
                              |
                              v
                   CloudWatch Logs + Metrics
               QueueBacklog / QueueActive / QueueOpen
```

- **CloudFront** terminates HTTPS and routes by path prefix
- **ALB** forwards root traffic to the customer app, `/admin/api/*` to the dashboard API, and keeps `/api/*` reserved for customer backend traffic
- **S3** serves the Amber admin React SPA under `/admin/*`
- **ECS Fargate** runs the dashboard API, customer app, and customer worker
- **customer-worker** drains the DBOS `agent-runs` queue
- **RDS Proxy** pools ECS database connections before RDS
- **RDS Postgres 16** stores DBOS state and dashboard data
- **CloudWatch Logs + Metrics** receives worker queue observability metrics

## Directory Layout

```
infra/
├── README.md
└── terraform/
    ├── main.tf
    ├── vpc.tf
    ├── alb.tf
    ├── ecs.tf
    ├── rds.tf
    ├── rds_proxy.tf
    ├── ecr.tf
    ├── s3.tf
    ├── cloudfront.tf
    ├── security_groups.tf
    ├── ssm.tf
    ├── secrets.tf
    ├── variables.tf
    ├── outputs.tf
    └── terraform.tfvars.example
```

Docker templates and entrypoint helpers used by the product CLI live under
`cli/amber_cli/asset_sources/docker/`. The packaged CLI copies this Terraform
directory with `make cli-assets`.

## Manual Terraform Validation

Use this flow when reviewing or debugging the Terraform template itself.

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan
```

For manual Terraform testing, copy the example variables file and edit it for
the disposable stack you are validating.

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
$EDITOR infra/terraform/terraform.tfvars
terraform -chdir=infra/terraform apply
```

`infra/terraform/terraform.tfvars` is only for manual Terraform testing. End
users running `amber deploy` edit `amber.yaml`; the CLI generates
`.amber/terraform/terraform.tfvars`.

## Product Deploy Path

The product path is:

```bash
amber init
$EDITOR amber.yaml
amber deploy
```

`amber deploy` packages this Terraform template into `.amber/terraform/`, builds
and pushes images, applies infrastructure, syncs frontend assets, and prints the
deployed URLs.

For the current local/beta CLI path, Terraform state remains local at
`.amber/terraform/terraform.tfstate`. AWS-backed remote state is intentionally
deferred until the production/multi-user story is ready.

`environment: prod` makes the CLI generate safer Terraform variables for S3,
Secrets Manager, and RDS. It does not enable remote Terraform state yet.

Terraform by itself creates infrastructure only. It does not:

- build Docker images
- push images to ECR
- restart ECS services after image changes
- build or sync dashboard frontend assets
- invalidate CloudFront

## Secrets

Terraform creates the AWS secret locations used by ECS tasks:

| Secret | Location | Key/Name |
|--------|----------|----------|
| OpenAI API key | SSM Parameter Store | `/app/<project_name>/<environment>/openai-api-key` |
| Database connection URL | Secrets Manager | `<project_name>-<environment>/db` |
| RDS Proxy credentials | Secrets Manager | `<project_name>-<environment>/db-credentials` |

For product deploys, use:

```bash
amber init
amber config set openai-api-key
amber deploy
```

If services are already running and you rotate the key, restart tasks so ECS
reads the new SSM value:

```bash
amber config set openai-api-key
amber deploy --no-build
```

For manual Terraform testing, replace the placeholder SSM parameter after the
first apply. The command reads the parameter name and region from Terraform
outputs.

```bash
OPENAI_PARAMETER_NAME="$(terraform -chdir=infra/terraform output -raw openai_api_key_parameter_name)"
REGION="$(terraform -chdir=infra/terraform output -raw aws_region)"

aws ssm put-parameter \
  --region "$REGION" \
  --name "$OPENAI_PARAMETER_NAME" \
  --type "SecureString" \
  --value "sk-replace-me" \
  --overwrite
```

ECS tasks read secrets at startup, so redeploy or restart services after
changing secret values.

## Teardown

For manual Terraform testing:

```bash
terraform -chdir=infra/terraform destroy
```

For `amber deploy` stacks today:

```bash
cd .amber/terraform
terraform destroy
```

CloudFront distribution deletion can take several minutes. Disposable dev
stacks default the frontend bucket to force destroy so Terraform can remove
uploaded assets and S3 object versions.
