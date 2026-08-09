# This folder intentionally uses LOCAL state: it creates the S3 bucket and
# DynamoDB table that the main config's remote backend depends on, so it
# cannot itself depend on that backend (bootstrap chicken-and-egg problem).

# ── S3 bucket for Terraform state ────────────────────────────────────────────
# Cost note: state files are a few KB each; S3 storage + request costs for this
# stay well within the AWS free tier (or a few cents/month after it expires).

resource "aws_s3_bucket" "tfstate" {
  bucket = "${var.project}-tfstate"

  tags = {
    Project   = var.project
    ManagedBy = "terraform"
    Purpose   = "terraform-remote-state"
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── DynamoDB table for state locking ─────────────────────────────────────────
# Cost note: PAY_PER_REQUEST billing means we only pay per lock/unlock request
# (a handful per terraform run) — effectively free tier / cents per month.

resource "aws_dynamodb_table" "tflock" {
  name         = "${var.project}-tflock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Project   = var.project
    ManagedBy = "terraform"
    Purpose   = "terraform-state-locking"
  }
}
