# =============================================================================
# AWS Group Project — Infrastructure Foundation
# =============================================================================
# This sets up the networking and database layer. Dashboard compute (Fargate or
# EC2) and CloudFront are added later once your team has the app code ready.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Remote state — uncomment once you have an S3 bucket for state. For now,
  # state stays local while you iterate.
  #
  # backend "s3" {
  #   bucket = "aws-group-project-tfstate"
  #   key    = "terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
