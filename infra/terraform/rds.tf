# =============================================================================
# RDS Postgres
# =============================================================================
# Provisions on the database subnet tier. Password is stored in Secrets Manager
# so your team can fetch it programmatically without hardcoding.
# =============================================================================

resource "random_password" "db_master" {
  length  = 32
  special = true
  # RDS rejects: /  @  "  space
  override_special = "!#$%&*()+,-.:;<=>?[]^_{|}~"

  # Keepers force regeneration when secrets change
  keepers = {
    project = var.project_name
  }
}

# DB password — uses user-supplied value if set, otherwise generates one.
# Your team can override this in terraform.tfvars with a known password.
locals {
  db_password = var.db_password != "" ? var.db_password : random_password.db_master.result
}

module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.9"

  identifier = "${var.project_name}-${var.environment}"

  engine               = "postgres"
  engine_version       = var.db_engine_version
  family               = "postgres16"
  major_engine_version = "16"
  instance_class       = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  storage_encrypted     = true
  storage_type          = "gp3" # 3000 IOPS baseline included
  max_allocated_storage = 100   # auto-scaling cap (disable with 0 if unwanted)

  db_name  = var.db_name
  username = var.db_username
  password = local.db_password
  port     = 5432

  # Networking — multi-AZ = false for dev (saves ~2x cost)
  multi_az               = false
  db_subnet_group_name   = module.vpc.database_subnet_group
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  create_db_subnet_group = false # VPC module creates it

  # Maintenance
  manage_master_user_password = false # use our generated password instead
  maintenance_window          = "sun:05:00-sun:06:00"
  backup_window               = "03:00-04:00"
  backup_retention_period     = 7
  delete_automated_backups    = true
  deletion_protection         = false # true for production!
  skip_final_snapshot         = true  # false for production!
  copy_tags_to_snapshot       = true

  # Parameters
  parameters = [
    {
      name  = "log_connections"
      value = "1"
    },
    {
      name  = "log_disconnections"
      value = "1"
    },
  ]
}
