# Create an AWS profile for Terraform in São Paulo

**Optional future deployment guide.** Under
[ADR-0028](../adr/ADR-0028-portfolio-scope-and-evidence.md), AWS remains an infrastructure reference.
The local portfolio demonstrations and Terraform CI need no AWS profile. Use this procedure only
when preparing a separately scoped AWS experiment or deployment.

This procedure creates a **local AWS CLI profile** to prepare a plan for the
[HTTPS integration infrastructure](../../infra/terraform/https-integration/README.md). Creating
the profile does not create AWS resources, activate LLM provider credentials, or run
`terraform apply`. Use the example name `governed-sao-paulo`, or choose another name and replace it
in every command.

## 1. Check the prerequisites

1. You need access to an AWS account and an authorized identity in that account. If you do not
   have an account yet, follow the [official AWS sign-up guide](https://docs.aws.amazon.com/accounts/latest/reference/sign-up-for-aws.html)
   or request access from your organization's administrator. A CLI profile does not create an
   account or grant permissions. For this project, request a role or permission set scoped to
   reviewing and, later, managing only the approved resources. Do not use the root identity for
   routine work.
2. Install or update **AWS CLI v2** using the
   [official guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
   Check the installation:

   ```sh
   aws --version
   ```

3. Check whether the profile already exists without printing keys:

   ```sh
   aws configure list-profiles
   ```

   Seeing a profile name does not prove that its session is authenticated. Do not copy
   `~/.aws/config`, `~/.aws/credentials`, tokens, or keys into this repository, tickets, or chats.

## 2. Choose a sign-in method

**If your organization uses IAM Identity Center (SSO), follow path A.** Ask the administrator for
the start URL (or issuer URL), the **Identity Center Region**, the account, and the approved
permission set. The Identity Center Region may differ from `sa-east-1`: it identifies the sign-in
directory. This profile's **default resource Region** will be `sa-east-1`.

**If you sign in directly to the AWS Console without Identity Center, follow path B.** It requires
AWS CLI v2.32.0 or later. Do not create long-lived access keys solely to run Terraform.

### Path A — IAM Identity Center

1. Start the wizard:

   ```sh
   aws configure sso --profile governed-sao-paulo
   ```

2. Answer its prompts using your organization's details:

   | Wizard prompt | Value to enter |
   | --- | --- |
   | SSO session name | A local name, such as `governed-sso` |
   | SSO start URL / issuer URL | URL supplied by the administrator |
   | SSO region | **Identity Center** Region supplied by the administrator |
   | SSO registration scopes | Accept `sso:account:access` if offered |
   | AWS account | Select the account approved for this deployment |
   | Role / permission set | Select the role approved for this work |
   | Default client Region | `sa-east-1` |
   | CLI default output format | `json` |
   | Profile name (if prompted) | `governed-sao-paulo`; the command already specifies it |

3. Sign in through the browser and verify your identity:

   ```sh
   aws sso login --profile governed-sao-paulo
   aws sts get-caller-identity --profile governed-sao-paulo
   ```

   The STS command returns `Account`, `Arn`, and `UserId`. Check **locally** that `Account` is the
   approved account. If the session expires, run `aws sso login` again. The flow and fields are
   described in the [AWS CLI IAM Identity Center guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html).

### Path B — sign in with an AWS Console session

1. Confirm that `aws --version` reports **2.32.0 or later**. Then run:

   ```sh
   aws login --profile governed-sao-paulo
   ```

2. If the CLI asks for the profile's Region, enter `sa-east-1`. Complete browser sign-in with the
   approved identity and account. Verify them:

   ```sh
   aws sts get-caller-identity --profile governed-sao-paulo
   ```

   Check `Account` locally. If the session expires, run
   `aws login --profile governed-sao-paulo` again. AWS documents the minimum CLI version, flow,
   and session lifetime in its [`aws login` guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).
   If your Terraform installation cannot use this session, prefer path A when available or use the
   `credential_process` described in the same guide. Do not export keys to work around the issue.

## 3. Confirm the Region and account before Terraform

Run these commands with the same profile you will use for the plan:

```sh
aws configure get region --profile governed-sao-paulo
aws configure list --profile governed-sao-paulo
aws sts get-caller-identity --profile governed-sao-paulo --query Account --output text
```

The first command shows the Region saved in the profile. The second command's `region` line shows
the effective Region and where that setting came from. Both should indicate `sa-east-1`. The STS
command should show the approved 12-digit AWS account ID. Use that ID as Terraform's
`target_account_id`. If the Region is wrong, update **only the chosen profile** and check again:

```sh
aws configure set region sa-east-1 --profile governed-sao-paulo
```

If the identity is still unexpected, stop before planning and use
`aws configure list --profile governed-sao-paulo` to identify the configuration source. AWS
environment variables can override profile settings; the
[AWS CLI precedence guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)
explains the order. Avoid printing `env` or exporting credentials in a recorded session.

## 4. Use the profile for this project's plan

After preparing the state S3 bucket and the `backend.hcl` and `integration.auto.tfvars` files
**outside Git**, as described in the [Terraform README](../../infra/terraform/https-integration/README.md),
go to the infrastructure directory:

```sh
cd infra/terraform/https-integration
AWS_PROFILE=governed-sao-paulo terraform init -backend-config=backend.hcl
AWS_PROFILE=governed-sao-paulo terraform plan -out=tfplan.review
AWS_PROFILE=governed-sao-paulo terraform show tfplan.review
```

Review the account, Region, resources, and estimated costs before any apply. The provider's
`allowed_account_ids` guard prevents a plan against another account but does not replace that
review. A plan file may contain sensitive data and is ignored by Git. This guide ends at the plan;
creating resources requires a separate deployment decision.

## Troubleshooting

| Symptom | What to check next |
| --- | --- |
| `NoCredentials` | Run `aws sso login` or `aws login` for the chosen profile, then repeat the STS check. |
| The profile exists, but STS shows another account | Check the selected account/role and the source shown by `aws configure list --profile governed-sao-paulo`; do not run Terraform. |
| `AccessDenied` | Ask the administrator for the approved role/permission set. Authentication does not imply permission for S3, VPC, RDS, ALB, Route 53, ACM, or Secrets Manager. |
| `aws login` is unavailable | Update AWS CLI v2 or use path A with IAM Identity Center. |
| The Region is empty or wrong | Set `sa-east-1` in the profile and check for overriding environment variables. |

Do not send tokens, access keys, secret keys, credential files, or the Terraform plan for
troubleshooting. The account ID, profile name, and **non-secret** network and certificate IDs are
sufficient for an infrastructure review.
