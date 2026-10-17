terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0.0, < 7.0.0"
    }
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

variable "target_account_id" {
  description = "Twelve-digit target AWS account ID."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.target_account_id))
    error_message = "target_account_id must be a twelve-digit AWS account ID."
  }
}
