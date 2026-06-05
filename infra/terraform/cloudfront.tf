# =============================================================================
# CloudFront — CDN: customer app + Amber admin frontend/API
# =============================================================================
# Default origin: ALB customer app
# /admin/*: S3 Amber admin React frontend
# /admin/api/*: ALB Amber admin API
# /api/*: reserved customer API path, currently forwarded to customer app
#
# This provides:
#   - HTTPS termination (CloudFront's default *.cloudfront.net cert)
#   - Customer app traffic routed to ECS via ALB
#   - Amber admin static frontend served from S3
# =============================================================================

# --- Origin Access Control for S3 ---

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-${var.environment}-s3-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --- S3 bucket policy: allow CloudFront OAC to read objects ---

data "aws_iam_policy_document" "frontend_bucket_policy" {
  statement {
    sid    = "AllowCloudFrontOAC"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudfront_distribution.main.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket_policy.json
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_function" "admin_spa_rewrite" {
  name    = "${var.project_name}-${var.environment}-admin-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite Amber admin SPA routes to /admin/index.html"
  publish = true
  code    = <<-EOT
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri === "/admin" || uri === "/admin/") {
    request.uri = "/admin/index.html";
    return request;
  }
  if (uri.indexOf("/admin/") === 0 && uri.indexOf(".") === -1) {
    request.uri = "/admin/index.html";
  }
  return request;
}
EOT
}

# Rewrites extension-less routes to /index.html so the customer React SPA can
# deep-link. Only attached to the default behavior (customer_frontend = "react"),
# so /admin/*, /admin/api/*, and /api/* are already handled by higher-priority
# ordered behaviors before this runs.
resource "aws_cloudfront_function" "customer_spa_rewrite" {
  name    = "${var.project_name}-${var.environment}-customer-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite customer SPA routes to /index.html"
  publish = true
  code    = <<-EOT
function handler(event) {
  var request = event.request;
  if (request.uri.indexOf(".") === -1) {
    request.uri = "/index.html";
  }
  return request;
}
EOT
}

# --- Distribution ---

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  price_class         = "PriceClass_100" # US, Canada, Europe — cheapest tier

  # S3 origin: Amber admin frontend static files, served via CloudFront OAC.
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # ALB origin (customer app + APIs)
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

    # Shared secret the ALB listener checks before forwarding. Keeps direct
    # hits to the ALB (or other CloudFront distributions) out of the backend.
    custom_header {
      name  = "X-Origin-Verify"
      value = random_password.origin_verify.result
    }
  }

  # /admin/api/* → ALB → dashboard-api
  ordered_cache_behavior {
    path_pattern             = "/admin/api/*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  # /admin/* → S3 Amber admin React SPA
  ordered_cache_behavior {
    path_pattern           = "/admin/*"
    target_origin_id       = "s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.admin_spa_rewrite.arn
    }
  }

  # /api/* → ALB → reserved customer API path
  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  # Default route. 'server' (default): customer app via ALB. 'react': customer
  # React SPA served from S3 (the FastAPI API is reached under /api/* above).
  default_cache_behavior {
    target_origin_id       = var.customer_frontend == "react" ? "s3" : "alb"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    cache_policy_id = (
      var.customer_frontend == "react"
      ? data.aws_cloudfront_cache_policy.caching_optimized.id
      : data.aws_cloudfront_cache_policy.caching_disabled.id
    )
    # Only the ALB origin needs viewer headers forwarded; S3 must not receive them.
    origin_request_policy_id = (
      var.customer_frontend == "react"
      ? null
      : data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    )
    compress = var.customer_frontend == "react"

    dynamic "function_association" {
      for_each = var.customer_frontend == "react" ? [1] : []
      content {
        event_type   = "viewer-request"
        function_arn = aws_cloudfront_function.customer_spa_rewrite.arn
      }
    }
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
