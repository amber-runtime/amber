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

resource "aws_security_group" "alb" {
  name        = "${var.project_name}-${var.environment}-alb"
  description = "Allow HTTP from CloudFront and internet"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
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
    path                = "/docs"
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

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.customer_app.arn
  }
}

# --- Listener Rules ---

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
