terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
  }

  # Remote state backend. Backend blocks cannot reference variables or locals,
  # so these values must be filled in by hand using the outputs from
  # terraform/bootstrap (see that folder's README-style instructions):
  #   bucket         -> bootstrap output "state_bucket_name"
  #   dynamodb_table -> bootstrap output "lock_table_name"
  #   region         -> the aws_region used for bootstrap (e.g. "us-east-1")
  backend "s3" {
    bucket         = "REPLACE_WITH_state_bucket_name"
    key            = "eks-platform/terraform.tfstate"
    region         = "REPLACE_WITH_aws_region"
    dynamodb_table = "REPLACE_WITH_lock_table_name"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.app_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
