# Infrastructure

AWS infrastructure for the Playground app, managed with Terraform.

## Architecture

```
                    CloudFront (HTTPS)
                   d3t5zmenq8914z.cloudfront.net
                           │
              ┌────────────┼────────────┐
              │            │            │
          / (root)   /dashboard/*    /api/*
              │            │            │
              ▼            ▼            ▼
           S3 SPA        ALB ──────────┘
         (React)           │     │
                    ┌──────┘     └──────┐
                    ▼                   ▼
            dashboard-api:8001   customer-app:8003
            (FastAPI + DBOS)     (FastAPI + DBOS + OpenAI Agents)
                    │                   │
                    │                   │
                    │        customer-worker:8004
                    │     (DBOS queue consumer)
                    │                   │
                    └─────────┬─────────┘
                              ▼
                          RDS Proxy
                              │
                              ▼
                        RDS Postgres 16

                    customer-worker:8004
                              │
                              ▼
                   CloudWatch Logs + Metrics
               QueueBacklog / QueueActive / QueueOpen
```

- **CloudFront** terminates HTTPS and routes by path prefix
- **ALB** forwards `/dashboard/*` to the dashboard API and `/api/*` to the customer app
- **S3** serves the React SPA for the root path
- **ECS Fargate** runs the dashboard API, customer app, and customer worker
- **customer-worker** drains the DBOS `agent-runs` queue
- **RDS Proxy** pools ECS database connections before RDS
- **RDS Postgres 16** shared database
- **CloudWatch Logs + Metrics** receives worker-emitted queue observability metrics; these are not wired to ECS autoscaling yet

## Directory Layout

```
infra/
├── terraform/          # Infrastructure as code
│   ├── main.tf         # Provider config
│   ├── vpc.tf          # VPC, subnets, NAT gateway
│   ├── alb.tf          # Application Load Balancer + listeners
│   ├── ecs.tf          # ECS cluster + Fargate services
│   ├── rds.tf          # Postgres 16 instance
│   ├── rds_proxy.tf    # RDS Proxy connection pooling
│   ├── ecr.tf          # ECR repositories
│   ├── s3.tf           # S3 bucket for frontend
│   ├── cloudfront.tf   # CloudFront distribution
│   ├── security_groups.tf
│   ├── ssm.tf          # SSM Parameter Store (API keys)
│   ├── secrets.tf      # Secrets Manager (DB connection URL)
│   ├── variables.tf    # Input variables
│   ├── outputs.tf      # Useful outputs after apply
│   └── terraform.tfvars.example
├── docker/             # Container definitions
│   ├── Dockerfile.dashboard-api
│   ├── Dockerfile.customer-app
│   ├── Dockerfile.customer-worker
│   ├── run_worker.py      # Worker health endpoint + queue metrics publisher
│   └── strip_prefix.py    # Middleware to strip ALB path prefixes
└── scripts/            # Helper scripts (run from repo root)
    ├── build-push.sh      # Build + push Docker images to ECR
    ├── deploy.sh          # Terraform apply + full deploy
    └── deploy-frontend.sh # Build React app + sync to S3
```

## Prerequisites

- **AWS CLI** configured with appropriate credentials (`aws configure`)
- **Terraform** >= 1.5 ([install](https://developer.hashicorp.com/terraform/install))
- **Docker** running (for building images)
- **Node.js + npm** (for building the frontend)

## Quick Start

### 1. Set up Terraform variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# For teammate testing, set project_name, environment, and region.
```

Use a short, lowercase, hyphenated `project_name`, such as `amber-andy` or
`acme-demo`. The frontend S3 bucket includes your AWS account ID to reduce
global bucket-name collisions:

```text
<project_name>-<environment>-<aws_account_id>-frontend
```

If you use a named AWS CLI profile, export it once before running the infra
commands. Use your own profile name; it does not need to be `amber-dev`.

```bash
export AWS_PROFILE=<your-profile>
```

### 2. Create the infrastructure

```bash
# From the repo root:
./infra/scripts/deploy.sh apply
```

Or run Terraform directly:

```bash
cd infra/terraform
terraform init
terraform apply
```

### 3. Set the OpenAI API key

Terraform creates a placeholder SSM parameter during the first apply. Replace
that placeholder with your real OpenAI API key before running the app. This
command reads the SSM parameter name and AWS region from Terraform outputs, so
only change the `--value` field.

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

ECS tasks read secrets at startup, so restart or redeploy services after
changing this value. The future Amber CLI flow will hide this AWS command behind
`amber config set openai-api-key`.

### 4. Build and push Docker images

```bash
# Both services:
./infra/scripts/build-push.sh all

# Or just one:
./infra/scripts/build-push.sh dashboard-api
./infra/scripts/build-push.sh customer-app
./infra/scripts/build-push.sh customer-worker
```

### 5. Deploy the frontend

```bash
./infra/scripts/deploy-frontend.sh
```

### 6. Do everything at once

```bash
./infra/scripts/deploy.sh full
```

This runs Terraform apply, builds/pushes all backend Docker images, restarts ECS services, and deploys the frontend.

## Useful Commands

```bash
# Check what Terraform would change (safe, no modifications)
./infra/scripts/deploy.sh plan

# Get outputs after apply (ALB DNS, CloudFront domain, ECR URLs, etc.)
cd infra/terraform && terraform output

# View sensitive outputs (RDS endpoint, secret ARN)
terraform output -json

# Restart ECS services (pick up new Docker images)
REGION="$(terraform -chdir=infra/terraform output -raw aws_region)"
CLUSTER="$(terraform -chdir=infra/terraform output -raw ecs_cluster_name)"
aws ecs update-service \
  --region "$REGION" \
  --cluster "$CLUSTER" \
  --service "$(terraform -chdir=infra/terraform output -raw dashboard_api_service_name)" \
  --force-new-deployment

aws ecs update-service \
  --region "$REGION" \
  --cluster "$CLUSTER" \
  --service "$(terraform -chdir=infra/terraform output -raw customer_app_service_name)" \
  --force-new-deployment

aws ecs update-service \
  --region "$REGION" \
  --cluster "$CLUSTER" \
  --service "$(terraform -chdir=infra/terraform output -raw customer_worker_service_name)" \
  --force-new-deployment

# Invalidate CloudFront cache after frontend changes
aws cloudfront create-invalidation \
  --distribution-id "$(terraform -chdir=infra/terraform output -raw cloudfront_distribution_id)" \
  --paths "/*"
```

## Teardown

```bash
# Destroy all infrastructure. For disposable dev stacks, the frontend bucket
# uses frontend_bucket_force_destroy=true so Terraform can delete deployed
# assets and all S3 object versions automatically.
cd infra/terraform
terraform destroy
```

Set `frontend_bucket_force_destroy = false` for production-like stacks where
frontend asset versions should not be deleted automatically. In that mode,
destroying the stack requires explicitly deleting all S3 object versions and
delete markers before Terraform can remove the bucket.

Note: CloudFront distribution deletion takes ~10-15 minutes. Terraform will wait.

## Secrets

Secrets are stored in AWS and are NOT committed to the repo:

| Secret | Location | Key/Name |
|--------|----------|----------|
| OpenAI API key | SSM Parameter Store | `/app/<project_name>/<environment>/openai-api-key` |
| Database connection URL | Secrets Manager | `<project_name>-<environment>/db` |
| RDS Proxy credentials | Secrets Manager | `<project_name>-<environment>/db-credentials` |

ECS tasks fetch the app secrets at startup via IAM role permissions. RDS Proxy
uses its own IAM role to fetch the database credential secret.
