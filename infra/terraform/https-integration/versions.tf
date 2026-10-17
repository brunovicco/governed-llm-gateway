terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0.0, < 7.0.0"
    }
  }

  backend "s3" {
    use_lockfile = true
  }
}

provider "aws" {
  region              = "sa-east-1"
  allowed_account_ids = [var.target_account_id]

  default_tags {
    tags = {
      Project     = "governed-llm-gateway"
      Environment = "https-integration"
      ManagedBy   = "terraform"
    }
  }
}
