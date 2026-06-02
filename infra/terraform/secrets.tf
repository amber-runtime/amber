# =============================================================================
# Secrets Manager — DB credentials
# =============================================================================
# Your team accesses this with:
#   aws secretsmanager get-secret-value --secret-id amber-dev/db
#
# Or from app code via AWS SDK — no hardcoded passwords.
# =============================================================================

resource "aws_secretsmanager_secret" "db" {
  name                    = "${var.project_name}-${var.environment}/db"
  description             = "RDS Proxy Postgres connection URL for ${var.project_name} (${var.environment})"
  recovery_window_in_days = var.secrets_force_destroy ? 0 : 30
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id     = aws_secretsmanager_secret.db.id
  secret_string = "postgresql://${urlencode(var.db_username)}:${urlencode(local.db_password)}@${aws_db_proxy.main.endpoint}:${module.rds.db_instance_port}/${var.db_name}"
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.project_name}-${var.environment}/db-credentials"
  description             = "Database credentials for ${var.project_name} RDS Proxy auth (${var.environment})"
  recovery_window_in_days = var.secrets_force_destroy ? 0 : 30
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = local.db_password
    engine   = "postgres"
    host     = module.rds.db_instance_address
    port     = module.rds.db_instance_port
    dbname   = var.db_name
  })
}
