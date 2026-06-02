#!/usr/bin/env bash
# =============================================================================
# Build and deploy the React frontend to S3
# =============================================================================
# Usage:
#   ./infra/scripts/deploy-frontend.sh
#
# Prerequisites:
#   - Node.js + npm installed
#   - AWS CLI configured with S3 write access
#   - Run from repo root
# =============================================================================

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
TF_DIR="infra/terraform"
VITE_API_BASE_URL="${VITE_API_BASE_URL:-/dashboard}"
VITE_CUSTOMER_APP_URL="${VITE_CUSTOMER_APP_URL:-/api}"

cd "$(git rev-parse --show-toplevel)"

BUCKET="$(terraform -chdir="$TF_DIR" output -raw frontend_bucket_name)"
DIST_ID="$(terraform -chdir="$TF_DIR" output -raw cloudfront_distribution_id)"

echo "==> Installing dashboard dependencies..."
cd dashboard
npm ci

echo "==> Building dashboard..."
VITE_API_BASE_URL="$VITE_API_BASE_URL" \
VITE_CUSTOMER_APP_URL="$VITE_CUSTOMER_APP_URL" \
  npm run build

echo "==> Syncing to S3..."
aws s3 sync dist/ "s3://${BUCKET}/" --delete

echo "==> Invalidating CloudFront cache..."
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*"
echo "==> CloudFront invalidation created."

echo "==> Frontend deployed to s3://${BUCKET}/"
