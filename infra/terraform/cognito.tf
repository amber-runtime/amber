# =============================================================================
# Cognito — Amber dashboard operator authentication
# =============================================================================

resource "aws_cognito_user_pool" "dashboard_admin" {
  name = "${var.project_name}-${var.environment}-dashboard-admins"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  tags = { Name = "${var.project_name}-${var.environment}-dashboard-admins" }
}

resource "aws_cognito_user_pool_domain" "dashboard_admin" {
  domain       = "${var.project_name}-${var.environment}-${data.aws_caller_identity.current.account_id}-admin"
  user_pool_id = aws_cognito_user_pool.dashboard_admin.id
}

resource "aws_cognito_user_pool_client" "dashboard_spa" {
  name         = "${var.project_name}-${var.environment}-dashboard-spa"
  user_pool_id = aws_cognito_user_pool.dashboard_admin.id

  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  supported_identity_providers         = ["COGNITO"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls = [
    "https://${aws_cloudfront_distribution.main.domain_name}/admin/",
    "http://localhost:5173/",
    "http://localhost:8765/callback",
  ]
  logout_urls = [
    "https://${aws_cloudfront_distribution.main.domain_name}/admin/",
    "http://localhost:5173/",
    "http://localhost:8765/callback",
  ]
  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
