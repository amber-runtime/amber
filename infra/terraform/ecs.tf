# =============================================================================
# ECS Fargate — dashboard-api + customer-app + customer-worker
# =============================================================================
# Three services:
#   dashboard-api (port 8001) — read-only workflow viewer
#   customer-app  (port 8003) — agent runtime, triggers workflows
#   customer-worker (port 8004) — DBOS queue consumer + queue metrics emitter
#
# Both run in private subnets behind the ALB. Traffic comes through
# path-based routing on the ALB.
# =============================================================================

# ── IAM ────────────────────────────────────────────────────────────────────────

# Shared task execution role — allows ECS to pull images, write logs, read secrets
resource "aws_iam_role" "ecs_execution" {
  name = "${var.project_name}-${var.environment}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_base" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow reading secrets from Secrets Manager + SSM Parameter Store
resource "aws_iam_policy" "ecs_execution_secrets" {
  name = "${var.project_name}-${var.environment}-ecs-execution-secrets"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.db.arn]
      },
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = [
          aws_ssm_parameter.openai_api_key.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = ["*"]
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_secrets" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = aws_iam_policy.ecs_execution_secrets.arn
}

# ── Cluster ────────────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"
}

# ── Common secrets list (both services need DB + API keys) ─────────────────────

locals {
  common_secrets = [
    {
      name      = "DBOS_SYSTEM_DATABASE_URL"
      valueFrom = aws_secretsmanager_secret_version.db.arn
    },
    {
      name      = "DB_URL"
      valueFrom = aws_secretsmanager_secret_version.db.arn
    },
    {
      name      = "OPENAI_API_KEY"
      valueFrom = aws_ssm_parameter.openai_api_key.arn
    },
  ]
}

# ── Dashboard API (port 8001) ─────────────────────────────────────────────────

resource "aws_ecs_task_definition" "dashboard_api" {
  family                   = "${var.project_name}-${var.environment}-dashboard-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256" # 0.25 vCPU — lightweight read-only service
  memory                   = "512" # 0.5 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "dashboard-api"
    image = "${aws_ecr_repository.dashboard_api.repository_url}:${var.image_tag}"

    portMappings = [{
      containerPort = 8001
      protocol      = "tcp"
    }]

    environment = [
      {
        name  = "DBOS__VMID"
        value = "${var.project_name}-${var.environment}-dashboard-api"
      }
    ]
    secrets = local.common_secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.dashboard_api.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "dashboard-api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:8001/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_cloudwatch_log_group" "dashboard_api" {
  name              = "/ecs/${var.project_name}-${var.environment}/dashboard-api"
  retention_in_days = 30
}

resource "aws_ecs_service" "dashboard_api" {
  name            = "${var.project_name}-${var.environment}-dashboard-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.dashboard_api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.dashboard_api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.dashboard_api.arn
    container_name   = "dashboard-api"
    container_port   = 8001
  }

  depends_on = [aws_lb_listener.http]
}

# ── Customer App (port 8003) ──────────────────────────────────────────────────

resource "aws_ecs_task_definition" "customer_app" {
  family                   = "${var.project_name}-${var.environment}-customer-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"  # 0.5 vCPU — runs agents, needs more headroom
  memory                   = "1024" # 1 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "customer-app"
    image = "${aws_ecr_repository.customer_app.repository_url}:${var.image_tag}"

    portMappings = [{
      containerPort = 8003
      protocol      = "tcp"
    }]

    environment = [
      {
        name  = "DBOS__VMID"
        value = "${var.project_name}-${var.environment}-customer-app"
      }
    ]
    secrets = local.common_secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.customer_app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "customer-app"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:8003/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_cloudwatch_log_group" "customer_app" {
  name              = "/ecs/${var.project_name}-${var.environment}/customer-app"
  retention_in_days = 30
}

resource "aws_ecs_service" "customer_app" {
  name            = "${var.project_name}-${var.environment}-customer-app"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.customer_app.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.customer_app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.customer_app.arn
    container_name   = "customer-app"
    container_port   = 8003
  }

  depends_on = [aws_lb_listener.http]
}

# ── Customer Worker (port 8004, no ALB) ──────────────────────────────────────

resource "aws_ecs_task_definition" "customer_worker" {
  family                   = "${var.project_name}-${var.environment}-customer-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"  # 0.5 vCPU — runs agents, same as API
  memory                   = "1024" # 1 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "customer-worker"
    image = "${aws_ecr_repository.customer_worker.repository_url}:${var.image_tag}"

    portMappings = [{
      containerPort = 8004
      protocol      = "tcp"
    }]

    environment = [
      {
        name  = "DBOS__VMID"
        value = "${var.project_name}-${var.environment}-customer-worker"
      },
      {
        name  = "WORKER_CONCURRENCY"
        value = tostring(var.worker_concurrency)
      },
      {
        name  = "PROJECT_NAME"
        value = var.project_name
      },
      {
        name  = "ENVIRONMENT"
        value = var.environment
      },
      {
        name  = "SERVICE_NAME"
        value = "customer-worker"
      },
      {
        name  = "QUEUE_METRICS_ENABLED"
        value = "true"
      },
      {
        name  = "QUEUE_METRICS_NAMESPACE"
        value = "Amber/Queues"
      },
      {
        name  = "QUEUE_METRICS_INTERVAL_SECONDS"
        value = "60"
      }
    ]
    secrets = local.common_secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.customer_worker.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "customer-worker"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:8004/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_cloudwatch_log_group" "customer_worker" {
  name              = "/ecs/${var.project_name}-${var.environment}/customer-worker"
  retention_in_days = 30
}

resource "aws_ecs_service" "customer_worker" {
  name            = "${var.project_name}-${var.environment}-customer-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.customer_worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.customer_worker.id]
    assign_public_ip = false
  }

  # No load_balancer block — worker doesn't serve external traffic
}
