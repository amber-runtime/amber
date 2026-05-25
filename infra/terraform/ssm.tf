# =============================================================================
# SSM Parameter Store — secrets the app needs at runtime
# =============================================================================
# Set these after apply:
#   aws ssm put-parameter --name /aws-group-project/dev/openai-api-key \
#       --value "sk-..." --type SecureString --overwrite
#   aws ssm put-parameter --name /aws-group-project/dev/dbos-conductor-key \
#       --value "dbos..." --type SecureString --overwrite
# =============================================================================

resource "aws_ssm_parameter" "openai_api_key" {
  name        = "/app/${var.project_name}/${var.environment}/openai-api-key"
  description = "OpenAI API key for the research agent"
  type        = "SecureString"
  value       = "placeholder-set-me-after-apply"

  lifecycle {
    ignore_changes = [value] # don't overwrite on every apply
  }

  tags = { Name = "${var.project_name}-${var.environment}-openai-api-key" }
}

resource "aws_ssm_parameter" "dbos_conductor_key" {
  name        = "/app/${var.project_name}/${var.environment}/dbos-conductor-key"
  description = "DBOS Conductor key for durable execution"
  type        = "SecureString"
  value       = "placeholder-set-me-after-apply"

  lifecycle {
    ignore_changes = [value]
  }

  tags = { Name = "${var.project_name}-${var.environment}-dbos-conductor-key" }
}
