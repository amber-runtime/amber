# =============================================================================
# Security Groups
# =============================================================================

# --- RDS Security Group ---
# Only allows Postgres traffic from resources in the same VPC.
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-${var.environment}-rds"
  description = "Allow Postgres from within VPC"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL from VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
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

# --- Dashboard API Security Group ---
resource "aws_security_group" "dashboard_api" {
  name        = "${var.project_name}-${var.environment}-dashboard-api"
  description = "Dashboard API - read-only workflow viewer"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTP from ALB"
    from_port   = 8001
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

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
resource "aws_security_group" "customer_app" {
  name        = "${var.project_name}-${var.environment}-customer-app"
  description = "Customer App - agent runtime"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTP from ALB"
    from_port   = 8003
    to_port     = 8003
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

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
resource "aws_security_group" "customer_worker" {
  name        = "${var.project_name}-${var.environment}-customer-worker"
  description = "Customer Worker - queue consumer for agent runs"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "Health check from VPC"
    from_port   = 8004
    to_port     = 8004
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "Outbound internet (NAT)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-${var.environment}-customer-worker" }
}
