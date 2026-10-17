# AWS São Paulo cost and access review

Status: read-only estimate, 2026-10-17. No AWS resource was created. This document is the next
review step after the [infrastructure preview](AWS_SAO_PAULO_INFRA_PLAN.md); it is not approval to
run `terraform apply` or activate a serving control.

## Estimated monthly baseline

The table shows the full-egress option using **730 running hours**, on-demand USD prices for
`sa-east-1`, two NAT gateways with
one public IPv4 each, one internal Application Load Balancer, one Multi-AZ PostgreSQL
`db.t4g.small`, 20 GiB gp3 storage, one private hosted zone, and one customer-managed KMS key.
The AWS Price List API was queried on 2026-10-17 for the regional hourly/storage SKUs. Route 53
and KMS use their public pricing pages. These are list prices, not an AWS Pricing Calculator quote,
an account-specific discount, or a spending ceiling.

| Component | Rate and assumption | Estimate / month |
| --- | ---: | ---: |
| Two NAT gateways | 2 × US$0.093/hour × 730 | US$135.78 |
| Two in-use public IPv4 addresses | 2 × US$0.005/hour × 730 | US$7.30 |
| RDS PostgreSQL Multi-AZ `db.t4g.small` | US$0.137/hour × 730 | US$100.01 |
| RDS gp3 storage | 20 GiB × US$0.438/GiB-month | US$8.76 |
| Application Load Balancer | US$0.034/hour × 730 | US$24.82 |
| Route 53 private hosted zone | First-zone monthly rate | US$0.50 |
| Customer-managed KMS key for state | Monthly key rate | US$1.00 |
| **Estimated baseline with private egress enabled** | | **US$278.17** |

NAT traffic processing (US$0.093/GB), ALB LCU usage (US$0.011/LCU-hour), data transfer,
additional database backup/storage/IOPS, S3 state storage/requests, KMS requests, DNS public-zone
queries, provider inference and taxes are **excluded**. A non-exportable public ACM certificate
used with the ALB has no separate certificate fee. The plan currently has no Gateway/Router
runtime, so this baseline would start accruing before it can serve a PDP request.

The Terraform default now defers NAT gateways and their IPv4 addresses until a runtime needs
private egress. The same arithmetic gives an estimated **US$135.09/month** for the remaining
always-on foundation.
Private workloads cannot fetch images, reach external APIs or providers through that VPC until an
egress design is enabled. This is a cost/availability choice, not a change to PDP authority.

Price references: [AWS VPC/NAT pricing](https://aws.amazon.com/vpc/pricing/),
[public IPv4 pricing](https://aws.amazon.com/vpc/pricing/),
[ALB pricing](https://aws.amazon.com/elasticloadbalancing/pricing/),
[RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/),
[Route 53 pricing](https://aws.amazon.com/route53/pricing/),
[KMS pricing](https://aws.amazon.com/kms/pricing/), and
[ACM pricing](https://aws.amazon.com/certificate-manager/pricing/).
Recheck the [AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html)
or Pricing Calculator just before deployment; prices and discounts can change.

## Terraform identity and state access

The local `governed-sao-paulo` profile currently reuses the SSO permission set
`OpsLensBootstrapAdmin`. It was sufficient for read-only discovery and plans, but is broader than
this project should retain for routine infrastructure work. A dedicated deployment permission set
or role should be reviewed before apply. Do not copy the existing OpsLens state bucket or grant
access to its objects.

For the **integration root's S3 backend**, the narrowly scoped state-access portion is:

- `s3:ListBucket` on the dedicated bucket, restricted to the exact state key prefix;
- `s3:GetObject` and `s3:PutObject` on the exact state object;
- `s3:GetObject`, `s3:PutObject` and `s3:DeleteObject` on the exact `.tflock` object;
- `kms:Encrypt`, `kms:Decrypt` and `kms:GenerateDataKey` on the dedicated state KMS key.

These actions follow the [Terraform S3 backend permission contract](https://developer.hashicorp.com/terraform/language/backend/s3).
They do not grant permission to create VPC, RDS, ALB, ACM, Route 53 or Secrets Manager resources.
The **apply role's resource permissions** need a separate, reviewed policy scoped to this
infrastructure; some create operations cannot be scoped to an ARN before the resource exists. Use
explicit account/region guards, project tags where supported, a short-lived SSO session, and a
reviewed saved plan. The bootstrap root needs one-time permissions to create its bucket, KMS key
and safety settings, then its local state must be preserved or migrated through a reviewed process.

No IAM permission set, role, policy, budget or resource has been changed by this review.
