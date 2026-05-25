# =============================================================================
# CloudFront — CDN: S3 frontend + ALB backend
# =============================================================================
# Default origin: S3 bucket (built React frontend)
# /api/* and /dashboard/*: forwarded to ALB (path-based routing to ECS services)
#
# This provides:
#   - HTTPS termination (CloudFront's default *.cloudfront.net cert)
#   - Static frontend served from S3
#   - API traffic routed to ECS via ALB
# =============================================================================

# --- Origin Access Control for S3 ---

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-${var.environment}-s3-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --- S3 bucket policy: public read for website hosting ---

data "aws_iam_policy_document" "frontend_bucket_policy" {
  statement {
    sid    = "PublicReadGetObject"
    effect = "Allow"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket_policy.json
}

# --- Distribution ---

resource "aws_cloudfront_distribution" "main" {
  enabled         = true
  is_ipv6_enabled = true
  price_class     = "PriceClass_100" # US, Canada, Europe — cheapest tier

  # Default origin: S3 website endpoint (frontend static files)
  origin {
    domain_name = "${aws_s3_bucket.frontend.id}.s3-website-${var.region}.amazonaws.com"
    origin_id   = "s3"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # ALB origin (API + dashboard backend)
  origin {
    domain_name = aws_lb.main.dns_name
    origin_id   = "alb"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # ALB is HTTP-only
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = "X-Forwarded-Host"
      value = aws_lb.main.dns_name
    }
  }

  # /api/* → ALB → customer-app
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "alb"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]

    forwarded_values {
      query_string = true
      headers      = ["Host", "Authorization", "Accept", "Content-Type"]

      cookies { forward = "all" }
    }

    min_ttl = 0
    default_ttl = 0
    max_ttl = 0
  }

  # /dashboard/* → ALB → dashboard-api
  ordered_cache_behavior {
    path_pattern           = "/dashboard/*"
    target_origin_id       = "alb"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]

    forwarded_values {
      query_string = true
      headers      = ["Host", "Authorization", "Accept"]

      cookies { forward = "all" }
    }

    min_ttl = 0
    default_ttl = 0
    max_ttl = 0
  }

  # Default: S3 frontend (SPA)
  default_cache_behavior {
    target_origin_id       = "s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]

    forwarded_values {
      query_string = false
      headers      = []
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 3600  # 1 hour for static assets
    max_ttl     = 86400 # 1 day
  }

  # SPA fallback: serve index.html for client-side routes
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { Name = "${var.project_name}-${var.environment}-cdn" }
}
