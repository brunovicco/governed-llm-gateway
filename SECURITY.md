# Security Policy

## Supported versions

Only the latest release is supported. Fixes land on `main` and go out in the next tag; there are no
maintenance branches for older versions.

| Version | Supported |
| --- | --- |
| 1.1.x | Yes |
| < 1.1 | No |

## Reporting a vulnerability

Report privately through GitHub: **Security → Report a vulnerability** on this repository, which opens
a private advisory visible only to the maintainer. Please do not open a public issue, discussion or
pull request for a suspected vulnerability.

Useful in a report: what boundary you believe is crossed, the smallest sequence that reproduces it, and
the configuration it needs. This is a personal open-source project, so expect a best-effort reply within
a few days rather than a guaranteed response window. There is no bug bounty.

## What this project treats as a vulnerability

The security properties this repository claims are specified in
[`docs/project/SECURITY_MODEL.md`](docs/project/SECURITY_MODEL.md) and
[`docs/project/THREAT_MODEL.md`](docs/project/THREAT_MODEL.md). A defect in any of them is in scope,
in particular:

- any path that lets the Gateway execute outside what the Policy Model Router authorized, or that lets
  runtime evidence, health, ranking, retry or fallback act as an authorization source;
- a provider credential, prompt or customer payload reaching a log, span, benchmark artifact, cached
  entry or committed file;
- a cached response served under an authorization context other than the one that produced it;
- an operations or evidence surface returning state to a credential not granted it;
- a spend ceiling or fail-closed startup check that can be bypassed;
- a secret-scanning or quality gate that can be made to pass while the defect it exists to catch is
  present.

## What is out of scope

This is a reference implementation meant to be run locally and read, not production infrastructure.
The absences listed under [Scope](README.md#scope) in the README are deliberate and documented, not
vulnerabilities: no TLS termination, no production IAM/SSO, no browser session handling, no rate
limiting, no CSRF policy. Also out of scope: the local shared secrets that the demo profiles ask you to
invent, third-party provider outages or model behavior, and findings that require an attacker to
already control the Gateway deployment's own environment or configuration artifacts.
