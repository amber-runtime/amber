# =============================================================================
# Variables
# =============================================================================

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "amber"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,24}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-26 lowercase letters, numbers, or hyphens, start with a letter, and end with a letter or number."
  }
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.region))
    error_message = "region must be an AWS region name such as us-east-1."
  }
}

variable "frontend_bucket_force_destroy" {
  description = "Allow terraform destroy to delete all frontend bucket objects and versions. Keep true for disposable dev stacks; set false for production-like stacks."
  type        = bool
  default     = true
}

variable "secrets_force_destroy" {
  description = "Skip the Secrets Manager recovery window so terraform destroy purges secrets immediately and names are instantly reusable. Keep true for disposable dev stacks; set false for production-like stacks."
  type        = bool
  default     = true
}

variable "image_tag" {
  description = "Container image tag the ECS task definitions pull. Defaults to 'latest'; deploy.sh passes the git short SHA so each deploy is a distinct, rollback-able revision."
  type        = string
  default     = "latest"
}

variable "asgi_app" {
  description = "Customer ASGI app target, for example my_app.main:app"
  type        = string
}

variable "worker_target" {
  description = "Customer AgentRuntime target, for example my_app.main:agent_runtime"
  type        = string
}

variable "path_prefix" {
  description = "Optional prefix stripped before the current customer ASGI app; leave empty for root-owned Jinja apps. /api is reserved for future customer API routing."
  type        = string
  default     = ""

  validation {
    condition     = var.path_prefix == "" || startswith(var.path_prefix, "/")
    error_message = "path_prefix must be empty or start with /."
  }
}

# -----------------------------------------------------------------------------
# VPC / Networking
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AZs to deploy into"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# -----------------------------------------------------------------------------
# RDS
# -----------------------------------------------------------------------------

variable "db_name" {
  description = "Database name (inside Postgres)"
  type        = string
  default     = "app"
}

variable "db_username" {
  description = "Master database username"
  type        = string
  default     = "dbadmin"
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance size"
  type        = string
  default     = "db.t4g.micro" # 2 vCPU, 1 GiB — fine for dev. Bump for prod.
}

variable "db_allocated_storage" {
  description = "RDS storage in GB"
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Run RDS in Multi-AZ mode. Amber CLI sets this true for prod."
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "Prevent accidental RDS deletion. Amber CLI sets this true for prod."
  type        = bool
  default     = false
}

variable "db_skip_final_snapshot" {
  description = "Skip final snapshot when deleting RDS. Amber CLI sets this false for prod."
  type        = bool
  default     = true
}

variable "db_delete_automated_backups" {
  description = "Delete automated backups with the RDS instance. Amber CLI sets this false for prod."
  type        = bool
  default     = true
}

variable "db_backup_retention_period" {
  description = "RDS backup retention in days. Amber CLI uses longer retention for prod."
  type        = number
  default     = 7
}

variable "db_password" {
  description = "Master database password (leave empty to auto-generate)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "db_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "16.3"
}

# -----------------------------------------------------------------------------
# Worker
# -----------------------------------------------------------------------------

variable "worker_concurrency" {
  description = "Number of workflows each customer-worker task can run concurrently"
  type        = number
  default     = 8

  validation {
    condition     = var.worker_concurrency >= 1 && var.worker_concurrency <= 100
    error_message = "worker_concurrency must be between 1 and 100."
  }
}

variable "worker_autoscaling_enabled" {
  description = "Enable ECS Service Auto Scaling for customer-worker tasks."
  type        = bool
  default     = true
}

variable "worker_min_tasks" {
  description = "Minimum number of customer-worker ECS tasks to keep running."
  type        = number
  default     = 1

  validation {
    condition     = var.worker_min_tasks >= 1 && var.worker_min_tasks <= 100
    error_message = "worker_min_tasks must be between 1 and 100."
  }
}

variable "worker_max_tasks" {
  description = "Maximum number of customer-worker ECS tasks. Defaults to 2 for dev/staging and 4 for prod."
  type        = number
  default     = null

  validation {
    condition     = var.worker_max_tasks == null || (var.worker_max_tasks >= 1 && var.worker_max_tasks <= 100)
    error_message = "worker_max_tasks must be between 1 and 100."
  }
}

variable "worker_backlog_target" {
  description = "Target QueueBacklog count for customer-worker ECS target tracking."
  type        = number
  default     = 8

  validation {
    condition     = var.worker_backlog_target >= 1
    error_message = "worker_backlog_target must be at least 1."
  }
}

variable "worker_scale_out_cooldown_seconds" {
  description = "Seconds ECS autoscaling waits between customer-worker scale-out actions."
  type        = number
  default     = 60

  validation {
    condition     = var.worker_scale_out_cooldown_seconds >= 0
    error_message = "worker_scale_out_cooldown_seconds must be non-negative."
  }
}

variable "worker_scale_in_cooldown_seconds" {
  description = "Seconds ECS autoscaling waits between customer-worker scale-in actions."
  type        = number
  default     = 300

  validation {
    condition     = var.worker_scale_in_cooldown_seconds >= 0
    error_message = "worker_scale_in_cooldown_seconds must be non-negative."
  }
}

variable "worker_queue_name" {
  description = "DBOS queue name emitted in customer-worker queue metrics."
  type        = string
  default     = "agent-runs"

  validation {
    condition     = length(trimspace(var.worker_queue_name)) > 0
    error_message = "worker_queue_name must not be empty."
  }
}
