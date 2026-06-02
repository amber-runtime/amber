# =============================================================================
# S3 — CloudFront origin bucket
# =============================================================================
# Holds your team's frontend static assets (HTML, JS, CSS, images).
# Bucket is private — CloudFront accesses it via OAC (Origin Access Control).
# =============================================================================

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "frontend" {
  bucket        = "${var.project_name}-${var.environment}-${data.aws_caller_identity.current.account_id}-frontend"
  force_destroy = var.frontend_bucket_force_destroy
}

# Keep the bucket private. CloudFront reads objects through OAC and the scoped
# bucket policy in cloudfront.tf.
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}
