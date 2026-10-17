# ADR-0027 — AWS São Paulo foundation for post-core readiness

## Status

Proposed for infrastructure review. AWS, `sa-east-1`, Terraform, a new isolated VPC and the private
`internal.viccolabs.com.br` domain were selected by the operator. An authenticated account and its
public `viccolabs.com.br` zone were inspected; no infrastructure was applied.

## Date

2026-10-17

## Context

Credential availability and spend admission have private contracts and process-local references,
but no shared durable authority or serving integration. The PDP transport comparison used synthetic
TLS, not an HTTPS Policy Model Router deployment. The current cross-repository composition proof
uses development mode and does not include the Governance Runtime Control projection required by
staging/production. These gaps are post-core work, outside the numbered phases.

## Decision

- Pin the infrastructure region to AWS `sa-east-1` and manage the reviewed foundation with Terraform.
  Create an isolated VPC with private workload subnets in two Availability Zones and separate
  public subnets reserved for NAT. Defer NAT by default until a reviewed runtime needs private
  egress; the explicit opt-in creates one NAT gateway per AZ. Use a separate Terraform bootstrap root for a
  dedicated encrypted/versioned S3 state bucket and KMS key. Do not let Terraform generate or
  store provider secret values. Review the VPC CIDR against future peering/VPN ranges before apply.
- Use AWS Secrets Manager secret containers for provider credential bindings. The future controller
  must publish an exact `VersionId`; the worker must fetch that version explicitly. `AWSCURRENT`,
  aliases and a mere successful secret fetch cannot assert credential availability.
- Use private, encrypted, Multi-AZ RDS PostgreSQL for future durable credential history/quarantine
  and all-scope spend reservation/journals. AWS manages the RDS master password in Secrets Manager;
  require PostgreSQL TLS. Terraform state must contain no plaintext database password. Separate application roles, schema,
  transactions, migrations, recovery/failover proof and access grants are later work.
- Provide an internal HTTPS Application Load Balancer, target group and
  `pdp.internal.viccolabs.com.br` private DNS name as the PDP
  ingress foundation. The target service, policy artifact, Redis replay state, Governance Runtime
  Control projection and Gateway-to-PDP credentials are not created by this foundation. Until they
  exist and pass composition tests, this endpoint is not an operational PDP or a staging claim.
  Obtain an ACM certificate by placing its validation CNAME in the existing public
  `viccolabs.com.br` zone; keep the PDP A record in the private zone only.
- Keep credential/spend serving controls and deadline/PDP-pool defaults off. Infrastructure does not
  grant policy authority; every Gateway request still requires a fresh, bound PDP decision.

## Alternatives considered

- DynamoDB could implement atomic conditional updates, but the current reference contracts need
  multi-scope reservation, journal and recovery semantics. PostgreSQL transactions are a closer
  implementation substrate; the actual schema and transaction protocol still need review.
- Redis is useful for transient/replay state but is not selected as the sole durable financial and
  credential-quarantine authority.
- A public PDP endpoint would simplify reachability but increase exposure. The selected endpoint
  is private within the VPC and restricted to Gateway security groups.
- Terraform-managed secret versions were rejected because secret material would enter plan/state.

## Consequences

The foundation has ongoing AWS cost when applied. RDS Multi-AZ, an internal ALB, the private hosted
zone and KMS key are cost drivers even without application traffic. Enabling two NAT gateways adds
substantial hourly and data-processing charges.
Terraform can validate the shape before deployment, but cannot establish application correctness,
PDP authorization, credential rotation safety or spend ceilings. Application migrations and
operational ownership must be reviewed separately.

## Security and privacy impact

RDS and the ALB are private. Public subnets are reserved for optional NAT gateways, not workloads.
The ACM validation
CNAME is public; the PDP service record is private. RDS storage and backups are encrypted and
deletion-protected. Secret
values stay out of Terraform. State must use encrypted, versioned S3 with restricted IAM and lockfile
locking. IAM for the eventual controller, worker and database roles must be least-privilege and
separate. Never log credentials, prompts, completions, tool data or raw provider/PDP bodies.
`Gateway allowed set ⊆ Policy Router authorized set` remains mandatory.

## Operational impact

The operator supplied a target AWS account/profile and selected the new VPC/domain. The inspected
region had only a default VPC with public subnets and no issued ACM certificate. The Terraform root
has no auto-apply. PostgreSQL 17.11 on `db.t4g.small`, gp3 and Multi-AZ was confirmed orderable in
the selected region; sizing and cost still need review. Destroying the RDS instance requires
explicit deletion-protection and final-snapshot decisions; credentials have a recovery window.
Region, account, CIDR, IAM and endpoint must be checked in a reviewed plan before apply. The
existing SSO profile uses a bootstrap admin role, which must be replaced by scoped deployment
permissions before apply.

## Follow-up

1. Review the isolated bootstrap and integration plans against the selected account. Provision the
   state bucket first, then initialize the integration backend; verify scoped IAM, CIDR and cost
   estimates before applying either plan. A temporary local-backend preview is not an applicable
   saved plan for the final S3 backend.
2. Deploy a pinned Policy Model Router image and policy through a separate reviewed runtime module,
   with durable Redis replay state and Governance Runtime Control as required by its environment.
   Prove private DNS/TLS, fresh authorization, denial and replay behavior before provider traffic.
3. Implement and test exact-version secret resolution plus durable credential state, including
   rotation, quarantine, concurrency, failover and scoped controller/worker permissions.
4. Implement PostgreSQL spend reservation/journal and qualified price/usage evidence; prove atomic
   all-scope admission, crash recovery and exact-attempt settlement before serving activation.
5. Repeat representative default-versus-opt-in deadline and PDP-pool tests on the real HTTPS path.
   Record metadata-only evidence and keep these options reversible.
