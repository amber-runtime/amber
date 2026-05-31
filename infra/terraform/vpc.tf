# =============================================================================
# VPC — public + private subnets across 2 AZs
# =============================================================================
# Architecture:
#   Public subnets:  NAT gateway, future ALB (ingress)
#   Private subnets: RDS, future Fargate tasks or EC2 instances
#
# This works for BOTH Fargate and EC2 — private subnets are walled off from
# direct internet but reachable via NAT for outbound (pulling images, etc.).
# =============================================================================

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = "${var.project_name}-${var.environment}"
  cidr = var.vpc_cidr

  azs             = var.availability_zones
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  # Database subnets — dedicated tier for RDS (optional but best practice)
  database_subnets             = ["10.0.201.0/24", "10.0.202.0/24"]
  create_database_subnet_group = true

  enable_nat_gateway   = true
  single_nat_gateway   = true # one NAT for dev saves ~$33/mo. Use false for prod HA.
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    "kubernetes.io/role/elb" = "1" # for future ALB in public subnets
  }
}
