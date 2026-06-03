# =============================================================================
# ECS Service Auto Scaling — customer-worker
# =============================================================================

locals {
  effective_worker_max_tasks = coalesce(var.worker_max_tasks, var.environment == "prod" ? 4 : 2)
}

resource "aws_appautoscaling_target" "customer_worker" {
  count = var.worker_autoscaling_enabled ? 1 : 0

  max_capacity       = local.effective_worker_max_tasks
  min_capacity       = var.worker_min_tasks
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.customer_worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "customer_worker_queue_backlog" {
  count = var.worker_autoscaling_enabled ? 1 : 0

  name               = "${var.project_name}-${var.environment}-customer-worker-queue-backlog"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.customer_worker[0].resource_id
  scalable_dimension = aws_appautoscaling_target.customer_worker[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.customer_worker[0].service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = var.worker_backlog_target
    scale_in_cooldown  = var.worker_scale_in_cooldown_seconds
    scale_out_cooldown = var.worker_scale_out_cooldown_seconds

    customized_metric_specification {
      metric_name = "QueueBacklog"
      namespace   = "Amber/Queues"
      statistic   = "Average"
      unit        = "Count"

      dimensions {
        name  = "QueueName"
        value = var.worker_queue_name
      }

      dimensions {
        name  = "Project"
        value = var.project_name
      }

      dimensions {
        name  = "Environment"
        value = var.environment
      }

      dimensions {
        name  = "Service"
        value = "customer-worker"
      }
    }
  }
}
