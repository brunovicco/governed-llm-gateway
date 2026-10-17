output "state_bucket_name" {
  value       = aws_s3_bucket.state.bucket
  description = "Dedicated encrypted, versioned state bucket for the integration root."
}

output "state_bucket_region" {
  value       = "sa-east-1"
  description = "Region for the integration root's backend.hcl."
}

output "state_kms_key_arn" {
  value       = aws_kms_key.state.arn
  description = "KMS key used for S3 state encryption."
}
