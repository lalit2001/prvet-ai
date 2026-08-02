##
## AWS module — implemented in M5. This file exists so `terraform validate`
## in CI has something to lint and so plan.md §C2's structure is real.
##
## Real resources land in M5: VPC, RDS (pgvector), SQS + DLQ, Lambda + API GW,
## ECS Fargate cluster/service, S3 + CloudFront + OAC, Secrets Manager.
##

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

provider "aws" {
  region = var.region
}

# Placeholder resource so a `terraform init && terraform validate` passes.
# Removed and replaced with real resources in M5.
resource "null_resource" "placeholder" {
  triggers = { stack = var.stack_name }
}
