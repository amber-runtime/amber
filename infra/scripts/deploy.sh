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
    echo "==> Running terraform apply..."
    terraform -chdir="$TF_DIR" apply -auto-approve

    echo "==> Building and pushing Docker images..."
    bash infra/scripts/build-push.sh all

    echo "==> Restarting ECS services..."
    aws ecs update-service \
      --cluster amber-dev \
      --service amber-dev-dashboard-api \
      --force-new-deployment --no-cli-pager
    aws ecs update-service \
      --cluster amber-dev \
      --service amber-dev-customer-app \
      --force-new-deployment --no-cli-pager
    aws ecs update-service \
      --cluster amber-dev \
      --service amber-dev-customer-worker \
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
