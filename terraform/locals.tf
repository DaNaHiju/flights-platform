locals {
  app_name    = var.app_name
  environment = var.environment

  name_prefix = "${local.app_name}-${local.environment}"

  cluster_name = "${local.name_prefix}-eks"

  common_tags = {
    Application = local.app_name
    Environment = local.environment
    ManagedBy   = "terraform"
  }

  # Availability zones: first two in the selected region
  azs = [
    "${var.aws_region}a",
    "${var.aws_region}b",
  ]

  public_subnets = [
    cidrsubnet(var.vpc_cidr, 8, 0),
    cidrsubnet(var.vpc_cidr, 8, 1),
  ]

  private_subnets = [
    cidrsubnet(var.vpc_cidr, 8, 10),
    cidrsubnet(var.vpc_cidr, 8, 11),
  ]
}
