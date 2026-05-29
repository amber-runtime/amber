#!/usr/bin/env bash
# =============================================================================
# Build and push Docker images to ECR
# =============================================================================
# Usage:
#   ./infra/scripts/build-push.sh [dashboard-api|customer-app|all]
#
# Prerequisites:
#   - AWS CLI configured with ECR permissions
#   - Docker running
#   - Run from repo root
# =============================================================================

set -euo pipefail

SERVICE="${1:-all}"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

REPOS=(
  "dashboard-api"
  "customer-app"
)

# Determine which services to build
if [ "$SERVICE" = "all" ]; then
  BUILD_SERVICES=("${REPOS[@]}")
else
  BUILD_SERVICES=("$SERVICE")
fi

echo "==> Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

for svc in "${BUILD_SERVICES[@]}"; do
  ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/amber-dev-${svc}"
  DOCKERFILE="infra/docker/Dockerfile.${svc}"

  if [ ! -f "$DOCKERFILE" ]; then
    echo "ERROR: Dockerfile not found at $DOCKERFILE"
    exit 1
  fi

  echo ""
  echo "==> Building ${svc}..."
  docker build --platform linux/amd64 -f "$DOCKERFILE" -t "${ECR_REPO}:latest" .

  echo "==> Pushing ${svc}..."
  docker push "${ECR_REPO}:latest"

  echo "==> ${svc} done: ${ECR_REPO}:latest"
done

echo ""
echo "==> All images built and pushed."
echo "==> Update ECS services with:"
echo "    aws ecs update-service --cluster amber-dev --service amber-dev-dashboard-api --force-new-deployment"
echo "    aws ecs update-service --cluster amber-dev --service amber-dev-customer-app --force-new-deployment"
echo "    aws ecs update-service --cluster amber-dev --service amber-dev-customer-worker --force-new-deployment"
