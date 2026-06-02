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
  default     = 4

  validation {
    condition     = var.worker_concurrency >= 1 && var.worker_concurrency <= 100
    error_message = "worker_concurrency must be between 1 and 100."
  }
}
