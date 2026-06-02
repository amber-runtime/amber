# =============================================================================
# Security Groups
# =============================================================================

# --- RDS Security Group ---
# Only allows Postgres traffic from the RDS Proxy.
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-${var.environment}-rds"
  description = "Allow Postgres from RDS Proxy"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "PostgreSQL from RDS Proxy"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.rds_proxy.id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-${var.environment}-rds" }
}

# --- RDS Proxy Security Group ---
resource "aws_security_group" "rds_proxy" {
  name        = "${var.project_name}-${var.environment}-rds-proxy"
  description = "Allow ECS services to connect to RDS Proxy"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL from ECS services"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    security_groups = [
      aws_security_group.dashboard_api.id,
      aws_security_group.customer_app.id,
      aws_security_group.customer_worker.id,
    ]
  }

  egress {
    description = "PostgreSQL to RDS"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  tags = { Name = "${var.project_name}-${var.environment}-rds-proxy" }
}

# --- Dashboard API Security Group ---
# Inbound is granted narrowly by aws_security_group_rule.alb_to_dashboard_api
# (source = ALB SG) in alb.tf, so no broad VPC-CIDR ingress here.
resource "aws_security_group" "dashboard_api" {
  name        = "${var.project_name}-${var.environment}-dashboard-api"
  description = "Dashboard API - read-only workflow viewer"
  vpc_id      = module.vpc.vpc_id

  egress {
    description = "Outbound internet (NAT)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-${var.environment}-dashboard-api" }
}

# --- Customer App Security Group ---
# Inbound is granted narrowly by aws_security_group_rule.alb_to_customer_app
# (source = ALB SG) in alb.tf, so no broad VPC-CIDR ingress here.
resource "aws_security_group" "customer_app" {
  name        = "${var.project_name}-${var.environment}-customer-app"
  description = "Customer App - agent runtime"
  vpc_id      = module.vpc.vpc_id

  egress {
    description = "Outbound internet (NAT)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-${var.environment}-customer-app" }
}

# --- Customer Worker Security Group ---
# No inbound rules: the worker is not behind the ALB and its ECS healthCheck runs
# inside the container (curl localhost:8004), so nothing connects to it inbound.
resource "aws_security_group" "customer_worker" {
  name        = "${var.project_name}-${var.environment}-customer-worker"
  description = "Customer Worker - queue consumer for agent runs"
  vpc_id      = module.vpc.vpc_id

  egress {
    description = "Outbound internet (NAT)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-${var.environment}-customer-worker" }
}
