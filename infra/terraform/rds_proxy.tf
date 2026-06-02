# =============================================================================
# RDS Proxy
# =============================================================================
# ECS tasks connect to this proxy endpoint. The proxy pools database connections
# before forwarding traffic to the private RDS Postgres instance.
# =============================================================================

resource "aws_iam_role" "rds_proxy" {
  name = "${var.project_name}-${var.environment}-rds-proxy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "rds.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "rds_proxy_secrets" {
  name = "${var.project_name}-${var.environment}-rds-proxy-secrets"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = [aws_secretsmanager_secret.db_credentials.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = ["*"]
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "rds_proxy_secrets" {
  role       = aws_iam_role.rds_proxy.name
  policy_arn = aws_iam_policy.rds_proxy_secrets.arn
}

resource "aws_db_proxy" "main" {
  name                   = "${var.project_name}-${var.environment}-rds-proxy"
  debug_logging          = false
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = 1800
  require_tls            = false
  role_arn               = aws_iam_role.rds_proxy.arn
  vpc_security_group_ids = [aws_security_group.rds_proxy.id]
  vpc_subnet_ids         = module.vpc.private_subnets

  auth {
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_secretsmanager_secret.db_credentials.arn
  }

  depends_on = [
    aws_iam_role_policy_attachment.rds_proxy_secrets,
    aws_secretsmanager_secret_version.db_credentials,
  ]

  tags = { Name = "${var.project_name}-${var.environment}-rds-proxy" }
}

resource "aws_db_proxy_default_target_group" "main" {
  db_proxy_name = aws_db_proxy.main.name

  connection_pool_config {
    connection_borrow_timeout    = 120
    max_connections_percent      = 90
    max_idle_connections_percent = 50
  }
}

resource "aws_db_proxy_target" "main" {
  db_instance_identifier = module.rds.db_instance_identifier
  db_proxy_name          = aws_db_proxy.main.name
  target_group_name      = aws_db_proxy_default_target_group.main.name
}
