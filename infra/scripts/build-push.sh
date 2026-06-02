#!/usr/bin/env bash
# =============================================================================
# Build and push Docker images to ECR
# =============================================================================
# Usage:
#   ./infra/scripts/build-push.sh [dashboard-api|customer-app|customer-worker|all]
#
# Prerequisites:
#   - AWS CLI configured with ECR permissions
#   - Docker running
#   - Run from repo root
# =============================================================================

set -euo pipefail

SERVICE="${1:-all}"
REGION="${AWS_REGION:-us-east-1}"
TF_DIR="infra/terraform"

cd "$(git rev-parse --show-toplevel)"

# Immutable image tag = git short SHA, so each build is a distinct, rollback-able
# revision. Also push :latest as a convenience pointer. Override with IMAGE_TAG.
TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

REPOS=(
  "dashboard-api"
  "customer-app"
  "customer-worker"
)

# Determine which services to build
if [ "$SERVICE" = "all" ]; then
  BUILD_SERVICES=("${REPOS[@]}")
else
  BUILD_SERVICES=("$SERVICE")
fi

terraform_output() {
  terraform -chdir="$TF_DIR" output -raw "$1"
}

ecr_repo_for() {
  case "$1" in
    dashboard-api)
      terraform_output ecr_dashboard_api_url
      ;;
    customer-app)
      terraform_output ecr_customer_app_url
      ;;
    customer-worker)
      terraform_output ecr_customer_worker_url
      ;;
    *)
      echo "ERROR: Unknown service '$1'. Expected dashboard-api, customer-app, customer-worker, or all." >&2
      exit 1
      ;;
  esac
}

echo "==> Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

for svc in "${BUILD_SERVICES[@]}"; do
  ECR_REPO="$(ecr_repo_for "$svc")"
  DOCKERFILE="infra/docker/Dockerfile.${svc}"

  if [ ! -f "$DOCKERFILE" ]; then
    echo "ERROR: Dockerfile not found at $DOCKERFILE"
    exit 1
  fi

  echo ""
  echo "==> Building ${svc} (${TAG})..."
  docker build --platform linux/amd64 -f "$DOCKERFILE" \
    -t "${ECR_REPO}:${TAG}" -t "${ECR_REPO}:latest" .

  echo "==> Pushing ${svc}..."
  docker push "${ECR_REPO}:${TAG}"
  docker push "${ECR_REPO}:latest"

  echo "==> ${svc} done: ${ECR_REPO}:${TAG}"
done

echo ""
echo "==> All images built and pushed (tag: ${TAG})."
