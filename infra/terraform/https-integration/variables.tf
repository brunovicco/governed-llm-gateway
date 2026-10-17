variable "target_account_id" {
  description = "Twelve-digit AWS account ID allowed to receive these resources."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.target_account_id))
    error_message = "target_account_id must be a twelve-digit AWS account ID."
  }
}

variable "vpc_cidr" {
  description = "Non-overlapping CIDR for the new isolated integration VPC."
  type        = string
  default     = "10.72.0.0/16"
}

variable "enable_private_egress" {
  description = "Create one NAT gateway per AZ for private workload egress only when runtime deployment is ready."
  type        = bool
  default     = false
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs for the two selected Availability Zones; used only for NAT gateways."
  type        = map(string)
  default = {
    a = "10.72.0.0/24"
    b = "10.72.1.0/24"
  }
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs for RDS, internal ALB and later workloads."
  type        = map(string)
  default = {
    a = "10.72.10.0/24"
    b = "10.72.11.0/24"
  }
}

variable "pdp_target_port" {
  description = "HTTP port on the separately deployed Policy Model Router service."
  type        = number
  default     = 8000

  validation {
    condition     = var.pdp_target_port >= 1 && var.pdp_target_port <= 65535
    error_message = "pdp_target_port must be a TCP port."
  }
}

variable "database_instance_class" {
  description = "Reviewed RDS instance class for the integration environment."
  type        = string
  default     = "db.t4g.small"
}

variable "database_engine_version" {
  description = "Reviewed PostgreSQL engine version supported in sa-east-1."
  type        = string
  default     = "17.11"
}

variable "database_allocated_storage_gib" {
  description = "Encrypted gp3 RDS allocated storage in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.database_allocated_storage_gib >= 20
    error_message = "Provide at least 20 GiB of database storage."
  }
}

variable "provider_credential_names" {
  description = "Approved secret container names. No secret values or versions are managed here."
  type        = set(string)
  default     = []
}
