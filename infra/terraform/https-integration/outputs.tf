output "pdp_https_url" {
  description = "Private TLS URL. It is usable only after a separately deployed PDP registers healthy targets."
  value       = "https://${local.pdp_dns_name}/route"
}

output "vpc_id" {
  description = "Isolated sa-east-1 VPC created by this root."
  value       = aws_vpc.integration.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs for separately reviewed Gateway and Router workloads."
  value       = [for subnet in aws_subnet.private : subnet.id]
}

output "gateway_security_group_id" {
  description = "Attach to future Gateway workloads after their ingress and runtime IAM are reviewed."
  value       = aws_security_group.gateway.id
}

output "pdp_target_group_arn" {
  description = "Attach the separately reviewed PDP service to this target group."
  value       = aws_lb_target_group.pdp.arn
}

output "pdp_target_security_group_id" {
  description = "Attach this security group to the separately deployed PDP service."
  value       = aws_security_group.pdp_target.id
}

output "state_database_endpoint" {
  description = "Private RDS address; no schema or application role is created by this root."
  value       = aws_db_instance.state.address
}

output "state_database_master_secret_arn" {
  description = "AWS-managed RDS master secret; restrict access and create application roles separately."
  value       = aws_db_instance.state.master_user_secret[0].secret_arn
  sensitive   = true
}

output "provider_credential_secret_arns" {
  description = "Empty secret containers; exact versions are published outside Terraform."
  value       = { for name, secret in aws_secretsmanager_secret.provider_credential : name => secret.arn }
}
