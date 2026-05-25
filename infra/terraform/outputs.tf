# =============================================================================
# Outputs — run "terraform output" after apply for connection details
# =============================================================================

# --- VPC ---
output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnets — RDS, ECS tasks go here"
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = "Public subnets — ALB goes here"
  value       = module.vpc.public_subnets
}

# --- RDS ---
output "rds_endpoint" {
  description = "RDS Postgres hostname"
  value       = module.rds.db_instance_address
  sensitive   = true
}

output "rds_port" {
  description = "RDS Postgres port"
  value       = module.rds.db_instance_port
}

output "rds_db_name" {
  value = var.db_name
}

# --- Secrets ---
output "db_secret_arn" {
  description = "Secrets Manager ARN — fetch with AWS CLI or SDK"
  value       = aws_secretsmanager_secret.db.arn
}

# --- S3 ---
output "frontend_bucket_name" {
  description = "S3 bucket for frontend static assets"
  value       = aws_s3_bucket.frontend.id
}

# --- ALB ---
output "alb_dns_name" {
  description = "ALB endpoint — CloudFront forwards here"
  value       = aws_lb.main.dns_name
}

# --- CloudFront ---
output "cloudfront_domain" {
  description = "CloudFront URL — primary endpoint for the app"
  value       = aws_cloudfront_distribution.main.domain_name
}

# --- ECR ---
output "ecr_dashboard_api_url" {
  description = "ECR repo URL for dashboard-api image"
  value       = aws_ecr_repository.dashboard_api.repository_url
}

output "ecr_customer_app_url" {
  description = "ECR repo URL for customer-app image"
  value       = aws_ecr_repository.customer_app.repository_url
}
