variable "project" {
  description = "Project name used to build the state bucket and lock table names"
  type        = string
  default     = "flights-api"
}

variable "aws_region" {
  description = "AWS region for the backend resources (S3 bucket + DynamoDB table)"
  type        = string
  default     = "us-east-1"
}
