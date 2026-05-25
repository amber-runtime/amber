# =============================================================================
# S3 — CloudFront origin bucket
# =============================================================================
# Holds your team's frontend static assets (HTML, JS, CSS, images).
# CloudFront distribution will be added later once assets are ready.
# Bucket is private — CloudFront accesses it via OAC (Origin Access Control).
# =============================================================================

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-${var.environment}-frontend"
}

# Allow public read — S3 website hosting needs public access for CloudFront.
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Future: add aws_cloudfront_origin_access_control + aws_cloudfront_distribution
# once your team has the frontend assets ready.
