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
                    └───────┬───────────┘
                            ▼
                      RDS Postgres 16
```

- **CloudFront** terminates HTTPS and routes by path prefix
- **ALB** forwards `/dashboard/*` to the dashboard API and `/api/*` to the customer app
- **S3** serves the React SPA for the root path
- **ECS Fargate** runs both backend services
- **RDS Postgres 16** shared database

## Directory Layout

```
infra/
├── terraform/          # Infrastructure as code
│   ├── main.tf         # Provider config
│   ├── vpc.tf          # VPC, subnets, NAT gateway
│   ├── alb.tf          # Application Load Balancer + listeners
│   ├── ecs.tf          # ECS cluster + Fargate services
│   ├── rds.tf          # Postgres 16 instance
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
│   └── strip_prefix.py   # Middleware to strip ALB path prefixes
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
# Edit terraform.tfvars if you need to change defaults
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

### 3. Build and push Docker images

```bash
# Both services:
./infra/scripts/build-push.sh all

# Or just one:
./infra/scripts/build-push.sh dashboard-api
./infra/scripts/build-push.sh customer-app
```

### 4. Deploy the frontend

```bash
./infra/scripts/deploy-frontend.sh
```

### 5. Do everything at once

```bash
./infra/scripts/deploy.sh full
```

This runs Terraform apply, builds/pushes both Docker images, restarts ECS services, and deploys the frontend.

## Useful Commands

```bash
# Check what Terraform would change (safe, no modifications)
./infra/scripts/deploy.sh plan

# Get outputs after apply (ALB DNS, CloudFront domain, ECR URLs, etc.)
cd infra/terraform && terraform output

# View sensitive outputs (RDS endpoint, secret ARN)
terraform output -json

# Restart ECS services (pick up new Docker images)
aws ecs update-service \
  --cluster aws-group-project-dev \
  --service aws-group-project-dev-dashboard-api \
  --force-new-deployment

aws ecs update-service \
  --cluster aws-group-project-dev \
  --service aws-group-project-dev-customer-app \
  --force-new-deployment

# Invalidate CloudFront cache after frontend changes
aws cloudfront create-invalidation \
  --distribution-id <DIST_ID> \
  --paths "/*"
```

## Teardown

```bash
# Empty the S3 bucket first (Terraform can't delete non-empty buckets)
aws s3 rm s3://aws-group-project-dev-frontend --recursive

# Destroy all infrastructure
cd infra/terraform
terraform destroy
```

Note: CloudFront distribution deletion takes ~10-15 minutes. Terraform will wait.

## Secrets

Secrets are stored in AWS and are NOT committed to the repo:

| Secret | Location | Key/Name |
|--------|----------|----------|
| OpenAI API key | SSM Parameter Store | `/app/aws-group-project/dev/openai-api-key` |
| DBOS Conductor key | SSM Parameter Store | `/app/aws-group-project/dev/dbos-conductor-key` |
| Database connection URL | Secrets Manager | `aws-group-project-dev-db-url` |

ECS tasks fetch these at startup via IAM role permissions.
