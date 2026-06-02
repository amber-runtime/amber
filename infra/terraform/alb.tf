# =============================================================================
# Application Load Balancer
# =============================================================================
# Path-based routing on port 80:
#   /dashboard/*  → dashboard-api  (port 8001)
#   /api/*        → customer-app   (port 8003)
#   default       → customer-app   (port 8003)
#
# CloudFront sits in front and handles HTTPS termination.
# =============================================================================

resource "aws_lb" "main" {
  name               = "${var.project_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnets

  tags = { Name = "${var.project_name}-${var.environment}-alb" }
}

# --- ALB Security Group ---

# AWS-managed prefix list of CloudFront's origin-facing IP ranges. Restricting
# the ALB to these means the origin can only be reached from CloudFront, not the
# open internet. The secret header (below) further ensures it's *our* distribution.
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# Shared secret that CloudFront attaches as a custom header on every origin
# request. The ALB listener rejects anything without it, so traffic that reaches
# the ALB IPs directly (or via someone else's CloudFront distribution) gets a 403.
resource "random_password" "origin_verify" {
  length  = 40
  special = false
}

resource "aws_security_group" "alb" {
  name        = "${var.project_name}-${var.environment}-alb"
  description = "Allow HTTP from CloudFront origin-facing ranges only"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "HTTP from CloudFront only"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-${var.environment}-alb" }
}

# --- Target Groups ---

resource "aws_lb_target_group" "dashboard_api" {
  name        = "${var.project_name}-${var.environment}-dash-tg"
  port        = 8001
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 5
    matcher             = "200"
  }

  tags = { Name = "${var.project_name}-${var.environment}-dashboard-api-tg" }
}

resource "aws_lb_target_group" "customer_app" {
  name        = "${var.project_name}-${var.environment}-app-tg"
  port        = 8003
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 5
    matcher             = "200"
  }

  tags = { Name = "${var.project_name}-${var.environment}-customer-app-tg" }
}

# --- Listener (port 80) ---

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # Reject anything that doesn't carry the CloudFront origin-verify header.
  # All real routing happens in the rules below, which also gate on the header.
  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Forbidden"
      status_code  = "403"
    }
  }
}

# --- Listener Rules ---
# Every rule requires the origin-verify header in addition to its path, so only
# traffic proxied by our CloudFront distribution is forwarded to a target group.

# /dashboard/*  → dashboard-api
resource "aws_lb_listener_rule" "dashboard_api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.dashboard_api.arn
  }

  condition {
    path_pattern {
      values = ["/dashboard/*", "/dashboard"]
    }
  }

  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [random_password.origin_verify.result]
    }
  }
}

# /api/*  → customer-app
resource "aws_lb_listener_rule" "customer_app" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.customer_app.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/api"]
    }
  }

  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [random_password.origin_verify.result]
    }
  }
}

# /demo/*  → customer-app (demo frontend + agent API)
resource "aws_lb_listener_rule" "customer_app_demo" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 210

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.customer_app.arn
  }

  condition {
    path_pattern {
      values = ["/demo/*", "/demo"]
    }
  }

  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [random_password.origin_verify.result]
    }
  }
}

# Catch-all → customer-app. Replaces the old listener default_action (which
# forwarded everything) so native customer-app routes like /runs and /agents
# still work, while the header gate keeps direct ALB hits out.
resource "aws_lb_listener_rule" "customer_app_default" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 900

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.customer_app.arn
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }

  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [random_password.origin_verify.result]
    }
  }
}

# --- ALB → Service Security Group Rules ---

resource "aws_security_group_rule" "alb_to_dashboard_api" {
  type                     = "ingress"
  from_port                = 8001
  to_port                  = 8001
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
  security_group_id        = aws_security_group.dashboard_api.id
}

resource "aws_security_group_rule" "alb_to_customer_app" {
  type                     = "ingress"
  from_port                = 8003
  to_port                  = 8003
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
  security_group_id        = aws_security_group.customer_app.id
}
