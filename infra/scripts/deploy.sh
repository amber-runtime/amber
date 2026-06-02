#!/usr/bin/env bash
# =============================================================================
# Full deploy: Terraform apply + Docker build/push + ECS restart + frontend
# =============================================================================
# Usage:
#   ./infra/scripts/deploy.sh [plan|apply|full]
#
#   plan   → terraform plan only (default)
#   apply  → terraform apply (infra only)
#   full   → terraform apply + build/push images + restart ECS + deploy frontend
# =============================================================================

set -euo pipefail

ACTION="${1:-plan}"
TF_DIR="infra/terraform"

cd "$(git rev-parse --show-toplevel)"

echo "==> Working in: $(pwd)"

terraform_output() {
  terraform -chdir="$TF_DIR" output -raw "$1"
}

# ── Terraform ─────────────────────────────────────────────────────────────────

echo "==> Initializing Terraform..."
terraform -chdir="$TF_DIR" init -upgrade

case "$ACTION" in
  plan)
    echo "==> Running terraform plan..."
    terraform -chdir="$TF_DIR" plan
    echo "==> Plan complete. No changes applied."
    ;;
  apply)
    echo "==> Running terraform apply..."
    terraform -chdir="$TF_DIR" apply -auto-approve
    echo "==> Infrastructure updated."
    ;;
  full)
    # Build/push FIRST so the SHA-tagged images exist before Terraform points the
    # task definitions at them. TAG is the git short SHA, shared with build-push.
    TAG="$(git rev-parse --short HEAD)"
    echo "==> Building and pushing Docker images (tag: $TAG)..."
    IMAGE_TAG="$TAG" bash infra/scripts/build-push.sh all

    echo "==> Running terraform apply (image_tag=$TAG)..."
    terraform -chdir="$TF_DIR" apply -auto-approve -var "image_tag=$TAG"

    # A new image_tag already bumps the task-def revision (triggering a deploy);
    # force-new-deployment additionally guarantees rollout when the SHA is
    # unchanged (e.g. rebuilding the same commit).
    echo "==> Forcing new ECS deployments..."
    CLUSTER="$(terraform_output ecs_cluster_name)"
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$(terraform_output dashboard_api_service_name)" \
      --force-new-deployment --no-cli-pager
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$(terraform_output customer_app_service_name)" \
      --force-new-deployment --no-cli-pager
    aws ecs update-service \
      --cluster "$CLUSTER" \
      --service "$(terraform_output customer_worker_service_name)" \
      --force-new-deployment --no-cli-pager

    echo "==> Deploying frontend..."
    bash infra/scripts/deploy-frontend.sh

    echo ""
    echo "==> Full deploy complete!"
    terraform -chdir="$TF_DIR" output cloudfront_domain
    ;;
  *)
    echo "Usage: $0 [plan|apply|full]"
    exit 1
    ;;
esac
