# AWS São Paulo infrastructure review checkpoint

Status: Terraform plans reviewed locally on 2026-10-17; **nothing applied**. This is post-core
readiness infrastructure, not a new numbered phase or serving activation. See
[ADR-0027](../adr/ADR-0027-aws-sao-paulo-readiness-infrastructure.md), the
[state bootstrap](../../infra/terraform/state-bootstrap/README.md) and the
[HTTPS integration root](../../infra/terraform/https-integration/README.md).

## Read-only account findings

The authenticated `governed-sao-paulo` SSO profile resolves to the selected account and
`sa-east-1`. In that region, the inspected account has only its default VPC and three subnets that
auto-assign public IPs. Route 53 has the public `viccolabs.com.br` zone, but no private zone; ACM has
no issued certificate in São Paulo. The existing OpsLens state bucket is in another region and is
not selected for this project. No secret values or provider traffic were inspected.

The operator selected a **new isolated VPC** and the private domain
`internal.viccolabs.com.br`. The planned PDP name is `pdp.internal.viccolabs.com.br`. ACM DNS
validation will place a public CNAME under the existing zone; the PDP A record remains private.

## Plans generated

| Root | Preview result | Main resources |
| --- | --- | --- |
| `state-bootstrap` | 8 create, 0 change, 0 destroy | Dedicated S3 bucket, KMS key/alias, versioning, default KMS encryption, public-access block, ownership control and TLS-only policy. |
| `https-integration` (default) | 35 create, 0 change, 0 destroy | Two-AZ VPC, two private/two public subnets, routes/security groups, private zone, ACM certificate/validation, internal HTTPS ALB, private Multi-AZ PostgreSQL RDS. NAT is deferred. |

The bootstrap plan was made from its local-state root. The integration preview was made from a
temporary copy with only its S3 backend block removed, because the dedicated bucket does not yet
exist. **That preview is not an applicable saved plan for the committed S3-backed root.** Reinitialize
and regenerate it after the state bucket exists. Saved preview files under `/tmp` are local and
must not be published or applied.

The original two-NAT preview had 41 creates; after making egress an explicit opt-in, the refreshed
default preview has 35 creates. Neither plan was applied. The account's RDS catalog confirms
PostgreSQL 17.11 on `db.t4g.small` with gp3 and Multi-AZ support.
Those are integration sizing defaults, not a cost or capacity approval. RDS is private, encrypted,
deletion-protected, configured for TLS and an AWS-managed master secret. The plan has no provider
credential containers because no binding names have been approved; future secret versions remain
outside Terraform state.

## Before any apply

1. Review the `10.72.0.0/16` CIDR against expected peering, VPN and corporate networks; verify
   public-zone ownership and the private hostname. Confirm the default no-NAT posture, Multi-AZ RDS,
   ALB, hosted zone and KMS costs against the available budget.
2. Replace the SSO profile's reused `OpsLensBootstrapAdmin` role with scoped Terraform permissions
   for this deployment. Review S3/KMS state access and lockfile operations separately. The current
   role is not an approval for infrastructure creation.
3. Review and apply the bootstrap plan first, preserving its local Terraform state. Configure the
   integration root's S3 backend using the actual bucket and KMS outputs. Regenerate and review a
   fresh plan on that backend before applying the integration root.
4. Deploy the pinned Policy Model Router, Redis replay state, Governance Runtime Control projection
   and Gateway separately. The ALB without healthy Router targets cannot serve PDP requests; the
   database without reviewed schemas/transactions cannot enforce credential or spend controls.
5. Prove real private DNS/TLS and fresh PDP authorization, denial, signed-envelope replay safety,
   then representative default-versus-opt-in deadline/pool behavior and controlled provider traffic.
   Keep metadata-only evidence and reversible rollout records.

There is no `terraform apply` in this checkpoint. No production-readiness or spend-ceiling claim
follows from these plans.
