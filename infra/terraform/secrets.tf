# =============================================================================
# Secrets Manager — DB credentials
# =============================================================================
# Your team accesses this with:
#   aws secretsmanager get-secret-value --secret-id aws-group-project-dev/db
#
# Or from app code via AWS SDK — no hardcoded passwords.
# =============================================================================

resource "aws_secretsmanager_secret" "db" {
  name        = "${var.project_name}-${var.environment}/db"
  description = "RDS Postgres connection details for ${var.project_name} (${var.environment})"
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id     = aws_secretsmanager_secret.db.id
  secret_string = "postgresql://${var.db_username}:${local.db_password}@${module.rds.db_instance_address}:${module.rds.db_instance_port}/${var.db_name}"
}
