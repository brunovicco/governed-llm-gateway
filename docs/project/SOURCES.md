# Sources

## Normative project source

- `SOURCE_ROADMAP.txt` — user-supplied Governed LLM Gateway project plan, preserved verbatim in this
  repository and used as the normative phase/scope/architecture source.

## Development harness reference

- `brunovicco/codex-python-engineering-harness`, branch `main`, inspected 2026-08-31.
- Harness README documents the `workspace` profile as a virtual uv workspace with explicit members,
  and governance as an independent profile dimension including `agentic`.
- Workspace template `pyproject.toml` and `AGENTS.md` were used as structural guidance.

## Phase 4 Policy Model Router contract reference

- `brunovicco/policy-model-router`, branch `main`, inspected 2026-08-31 after the workload/model-group
  generalization dependency had been merged.
- `src/policy_model_router/domain/routing.py` defines the router request, accepted decision,
  rejection decision, and deterministic policy/deployment provenance carried by each outcome.
- `src/policy_model_router/application/route_model.py` defines the fail-closed routing use case and
  selected logical model-group semantics.
- `src/policy_model_router/domain/constraints.py` defines the ordered policy constraints and confirms
  that tool-calling authorization is derived from the workload rule rather than a per-request field.
- `src/policy_model_router/entrypoints/contracts.py` and
  `src/policy_model_router/entrypoints/http.py` define the versioned `POST /route` HTTP contract,
  authentication/error behavior, and response projection consumed by the gateway.
- `docs/adr/0009-policy-identity-and-decision-provenance.md` defines policy ID/version/digest,
  service/environment provenance, and the full provenance attached to accepted/rejected decisions.

These first-party sources bind Phase 4 to Policy Model Router wire schema `1.0`. The gateway does not
import the router's domain/application Python types into gateway contracts/domain; the versioned HTTP
boundary remains the integration contract.

## Phase 5 routing and explainability references

The normative Phase 5 requirements come from `SOURCE_ROADMAP.txt`, especially sections 17–18, 35,
and the Phase 5 implementation roadmap acceptance criteria. ADR-0006 records the resulting gateway
architecture decision.

Official framework documentation reviewed on 2026-08-31:

- FastAPI dependency injection: `https://fastapi.tiangolo.com/tutorial/dependencies/`
- FastAPI version guidance: `https://fastapi.tiangolo.com/deployment/versions/`
- Pydantic model configuration: `https://docs.pydantic.dev/latest/api/config/`
- Pydantic fields/constraints: `https://docs.pydantic.dev/latest/api/fields/`

The Phase 5 `gateway-api` package pins FastAPI `0.141.1` and Pydantic `2.13.5` in the workspace lock.
These frameworks are used only at the HTTP composition boundary. They do not define authorization or
ranking semantics and do not enter `gateway-contracts` or `gateway-core/domain`.

FastAPI's dependency-injection model is consistent with keeping authenticated/effective context
resolution as an injected API-boundary responsibility rather than accepting caller security claims as
trusted facts. Pydantic is used for closed request/response validation, including rejecting unknown
fields, unsupported schema versions, and invalid workload identifiers.

The ranking algorithm itself intentionally has no external model/provider source of truth in Phase 5.
Its static/versioned score policy is gateway-owned configuration. It must not be described as
benchmark-derived evidence before Phases 10–11.

## Phase 3 provider references

The following official provider documentation was reviewed on 2026-08-31. These references define
API-family wire behavior only; they do not grant provider/model authorization or registry approval.

### OpenAI

- Responses API reference: `https://platform.openai.com/docs/api-reference/responses`
- Used to validate the native `/v1/responses` adapter shape, `instructions`, input messages,
  `max_output_tokens`, output text blocks, response status, and usage metadata.

### Anthropic

- Messages API reference: `https://docs.anthropic.com/en/api/messages`
- Used to validate the native `/v1/messages` adapter shape, top-level `system`, `messages`,
  `max_tokens`, `x-api-key`, `anthropic-version`, text content blocks, stop reason, and usage.

### Google Gemini

- Gemini API overview: `https://ai.google.dev/gemini-api/docs`
- Interactions API overview: `https://ai.google.dev/gemini-api/docs/interactions-overview`
- `generateContent` API reference: `https://ai.google.dev/api/generate-content`

Google documents the Interactions API as the recommended/default interface for new projects as of
June 2026 while continuing to support `generateContent`. Phase 3 intentionally uses native
`generateContent` because the current provider-neutral request owns canonical message history but not
the exact model-generated Interaction steps required for lossless stateless Interactions history.
See `docs/project/PROVIDER_CONTRACT.md` for the architectural rationale.

## Internal migration-pattern reference

- `brunovicco/controlled-autonomy-lab`, branch `main`, inspected 2026-08-31.
- Its provider-port/error-boundary patterns were reviewed as migration guidance only.
- It is not a runtime or development dependency of the gateway; consumer-project dependency
  direction remains downstream-only.

## Source authority rule

Policy Model Router sources define authorization semantics and provenance. Provider documentation may
define transport fields, response shapes, and API behavior. FastAPI/Pydantic documentation defines
only the API framework/validation behavior. None of these sources may broaden PDP authorization.

Model/deployment operational eligibility is gateway-owned only after the upstream Policy Model Router
authorization boundary has been established.
