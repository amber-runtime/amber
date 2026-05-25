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
BUCKET="aws-group-project-dev-frontend"
DIST_ID=""  # set after first terraform apply: grep for cloudfront_domain in outputs

echo "==> Installing dashboard dependencies..."
cd dashboard
npm ci

echo "==> Building dashboard..."
npm run build

echo "==> Syncing to S3..."
aws s3 sync dist/ "s3://${BUCKET}/" --delete

echo "==> Invalidating CloudFront cache..."
if [ -z "$DIST_ID" ]; then
  # Try to get the distribution ID automatically
  DIST_ID=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Comment==''].Id | [0]" \
    --output text 2>/dev/null || echo "")
fi

if [ -n "$DIST_ID" ] && [ "$DIST_ID" != "None" ]; then
  aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*"
  echo "==> CloudFront invalidation created."
else
  echo "==> WARNING: Could not determine CloudFront distribution ID."
  echo "    Run manually:"
  echo "    aws cloudfront create-invalidation --distribution-id <DIST_ID> --paths '/*'"
fi

echo "==> Frontend deployed to s3://${BUCKET}/"
