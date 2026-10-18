# Dedicated Terraform state bucket

**Portfolio status:** validated reference; deployment deferred under
[ADR-0028](../../../docs/adr/ADR-0028-portfolio-scope-and-evidence.md). No state bucket is needed to
run the portfolio's local demonstrations or credential-free Terraform validation.

The [terraform-validate workflow](../../../.github/workflows/terraform-validate.yml) checks this
root and the integration root with read-only GitHub permissions and no AWS credentials. From this
directory, reproduce its Terraform checks with:

```sh
terraform fmt -check -recursive
terraform init -backend=false -input=false -lockfile=readonly -no-color
terraform validate -no-color
```

These checks validate configuration, not a deployed bucket. The remaining instructions apply only
if a future deployment is explicitly resumed.

This separate Terraform root defines a versioned S3 bucket in `sa-east-1`, encrypted with a
rotating KMS key, with public access blocked, TLS-only bucket policy and deletion protection.
Its state is **local during bootstrap**. Neither this root nor the integration root has been
applied. The bucket name is derived from `target_account_id`; S3 bucket names are global, so a
name collision would require a reviewed naming change.

From this directory, after checking the AWS profile and account:

```sh
terraform init
AWS_PROFILE=governed-sao-paulo terraform plan \
  -var='target_account_id=<approved-12-digit-account-id>' -out=tfplan.bootstrap
terraform show tfplan.bootstrap
```

Review KMS/S3 permissions, bucket name, account, region, recurring KMS costs and the plan before
any apply. Keep `terraform.tfstate`, its backups and plan files out of Git. This root does not grant
IAM access: a dedicated Terraform role later needs scoped S3 and KMS permissions, including lockfile
object operations. Preserve and back up its local state; do not recreate the bucket from a lost state
without an import/reconciliation plan. Once the bucket exists, configure the integration root's S3
backend with its output. Do not share the existing OpsLens state bucket or its state namespace.
