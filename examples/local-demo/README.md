# Operations-only local demo artifacts

These artifacts exist only for the bounded PC-29 local Operations demo. They reuse the production-shaped
Gateway client-authentication and Operations-read access schemas without committing credential values.

## Files

- `client-auth.json` declares one `local-operations-demo` identity in `development` and references the
  runtime environment variable `GATEWAY_LOCAL_DEMO_API_KEY`.
- `operations-access.json` grants read-only Operations visibility to that exact identity.

The checked-in model registry, provider runtime and Policy Router runtime remain the existing empty,
non-executable baseline. PC-29 validates that state before resolving the local demo credential.

## Credential handling

Do not add a raw key to either JSON artifact. Supply an ephemeral value only in the local process
environment, for example:

```bash
export GATEWAY_LOCAL_DEMO_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

The value is used by the existing Gateway client-authentication resolver. It must not be copied into a
provider configuration, Policy Router configuration, URL, committed `.env` file, trace, log or persisted
browser storage.

## Authority boundary

The `allowed_workloads` field is required by the existing client-authentication schema, but the
operations-only application never attaches a workload-routing or inference endpoint. The Operations grant
is a separate exact visibility grant and does not confer model/deployment execution authority.

See `docs/project/LOCAL_OPERATIONS_DEMO.md` for the process boundary, startup command, validation contract
and non-claims.