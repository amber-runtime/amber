# =============================================================================
# ECR — container image repositories
# =============================================================================
# After apply:  docker tag + docker push + update ECS service
# =============================================================================

resource "aws_ecr_repository" "dashboard_api" {
  name = "${var.project_name}-${var.environment}-dashboard-api"

  image_scanning_configuration {
    scan_on_push = true
  }

  force_delete = true # dev only — protects against orphan images in prod

  tags = { Name = "${var.project_name}-${var.environment}-dashboard-api" }
}

resource "aws_ecr_repository" "customer_app" {
  name = "${var.project_name}-${var.environment}-customer-app"

  image_scanning_configuration {
    scan_on_push = true
  }

  force_delete = true

  tags = { Name = "${var.project_name}-${var.environment}-customer-app" }
}


