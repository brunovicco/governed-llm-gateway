# AWS São Paulo HTTPS integration foundation

**Portfolio status:** validated infrastructure reference; deployment deferred under
[ADR-0028](../../../docs/adr/ADR-0028-portfolio-scope-and-evidence.md). The active next step is the
[local demonstration plan](../../../docs/project/PORTFOLIO_DEMO_PLAN.md). The preparation and
deployment instructions below are retained for conditional future use.

This Terraform root is a reviewable **foundation**, not an activated PDP or credential/spend
control. It creates an isolated two-AZ VPC and private subnets, with one NAT gateway per AZ only
when `enable_private_egress = true`, plus a private
Route 53 zone, an ACM certificate validated through the existing public `viccolabs.com.br` zone,
optional empty Secrets Manager containers for approved binding names, private encrypted Multi-AZ
PostgreSQL RDS, and an internal HTTPS
ALB/target group/private DNS name in `sa-east-1`. It creates no secret
versions, database schema/application role, IAM workload role, Redis, Gateway, Policy Model Router
service, Governance Runtime Control, provider inference or runtime feature flag. See
[ADR-0027](../../../docs/adr/ADR-0027-aws-sao-paulo-readiness-infrastructure.md) and the
[post-core readiness plan](../../../docs/project/POST_CORE_READINESS.md).

## Inputs and state

The selected account has only a default VPC with public subnets, a public `viccolabs.com.br` hosted
zone, and no issued ACM certificate in `sa-east-1` (read-only inspection, 2026-10-17). This root
therefore creates a dedicated private network and certificate. Confirm the default `10.72.0.0/16`
CIDR does not overlap any planned peering/VPN/corporate network. The public subnets are reserved for
NAT gateways; workload and ALB subnets do not auto-assign public IPs. NAT is off by default because
no Gateway/Router workload exists yet. Private workloads will need reviewed egress before image
pulls, AWS API access or provider calls. Turning on `enable_private_egress` creates one NAT gateway
and one public IPv4 per AZ for same-AZ egress paths, with material recurring cost.

The ALB terminates HTTPS; its target group uses private HTTP to the separately deployed Router.
If end-to-end TLS is required, review a Router TLS target design before applying this root. The
exported Router target security group allows inbound traffic from the ALB only; the Router
deployment must separately define egress to its approved Redis and Governance dependencies.

Prepare the dedicated encrypted, versioned S3 state bucket with the separate
[state bootstrap root](../state-bootstrap/README.md). Review its local state and IAM before using
it. Keep `backend.hcl`, `.tfvars`, plans, state, credential values and secret versions out of Git.
Example **shape**, with placeholders only:

```hcl
# backend.hcl (local, ignored)
bucket = "<approved-private-state-bucket>"
key    = "governed-llm-gateway/https-integration/terraform.tfstate"
region = "sa-east-1"
encrypt = true
kms_key_id = "<state-kms-key-arn>"
```

```hcl
# integration.auto.tfvars (local, ignored)
target_account_id              = "<12-digit-account-id>"
vpc_cidr                       = "10.72.0.0/16"
enable_private_egress          = false
database_instance_class        = "db.t4g.small"
database_engine_version        = "17.11"
provider_credential_names      = []
```

Use the `governed-sao-paulo` profile for review. It currently reuses the existing
`OpsLensBootstrapAdmin` SSO role; replace that with a role scoped to this deployment before apply.
`allowed_account_ids` blocks an accidental plan/apply against another account. Review state and its access separately:
the state contains infrastructure metadata and a database master-secret ARN, even though it does
not contain provider secret values or a plaintext RDS master password. If no profile exists, follow
the [step-by-step AWS profile setup](../../../docs/project/AWS_PROFILE_SETUP.md) before preparing
the plan.

## Validate and review

The [terraform-validate workflow](../../../.github/workflows/terraform-validate.yml) checks both
Terraform roots on relevant pull requests and `main` pushes, and supports manual dispatch. It uses
Terraform 1.15.8, committed provider locks, `contents: read`, and no cloud credentials. Run its
configuration checks locally from this directory:

```sh
terraform fmt -check -recursive
terraform init -backend=false -input=false -lockfile=readonly -no-color
terraform validate -no-color
```

Initialization may download providers, but it does not initialize the S3 backend. Validation does
not query AWS or prove a deployed endpoint, database, IAM policy or cost. CI contains no plan/apply.
See the [Terraform validation contract](https://developer.hashicorp.com/terraform/cli/commands/validate).

With the state bucket and scoped Terraform role ready, the operator can prepare a saved plan:

```sh
AWS_PROFILE=governed-sao-paulo terraform init -backend-config=backend.hcl
AWS_PROFILE=governed-sao-paulo terraform plan -out=tfplan.review
terraform show tfplan.review
```

Review account, region, CIDR overlap, private egress, DNS/certificate match, IAM, database sizing, monthly cost and
resource changes before any apply. The plan file is sensitive and ignored. No `terraform apply` is
part of this repository validation.

The ALB will have no healthy target until a separately reviewed Router service is attached. The
Router also needs a pinned image, policy artifact, replay store and its environment's Governance
Runtime Control projection. Do not point a Gateway at this URL until `/route` authorization,
denial, replay, TLS and signed-envelope composition have been proven. The Gateway's deadline and
PDP pool remain separate opt-ins; credential/spend serving stays disabled until durable backend
conformance and controlled real traffic evidence are complete. The default
`provider_credential_names = []` creates no provider secret containers.
