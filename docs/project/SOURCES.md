# Sources

## Normative project source

- `SOURCE_ROADMAP.txt` — user-supplied Governed LLM Gateway project plan, preserved verbatim and used
  as the normative phase/scope/architecture source.

## Development harness reference

- `brunovicco/codex-python-engineering-harness`, branch `main`, inspected 2026-08-31.
- Harness README documents the `workspace` profile and `agentic` governance profile.
- Workspace template structure remains guidance only, not a runtime dependency.

## Phase 4 Policy Model Router contract reference

- `brunovicco/policy-model-router`, branch `main`, inspected 2026-08-31 after workload/model-group
  generalization was merged.
- `src/policy_model_router/domain/routing.py` defines router request/decision provenance.
- `src/policy_model_router/application/route_model.py` defines fail-closed routing semantics.
- `src/policy_model_router/domain/constraints.py` defines ordered policy constraints.
- `src/policy_model_router/entrypoints/contracts.py` and
  `src/policy_model_router/entrypoints/http.py` define the versioned `POST /route` schema `1.0` used by
  the gateway.
- `docs/adr/0009-policy-identity-and-decision-provenance.md` defines policy identity/provenance.

The gateway does not import Policy Model Router domain/application Python types into contracts/domain;
the versioned HTTP boundary remains the integration contract.

## Phase 5 routing and explainability references

Normative Phase 5 requirements come from `SOURCE_ROADMAP.txt` and are captured architecturally in
ADR-0006.

Official framework documentation reviewed on 2026-08-31:

- FastAPI dependency injection: `https://fastapi.tiangolo.com/tutorial/dependencies/`
- FastAPI version guidance: `https://fastapi.tiangolo.com/deployment/versions/`
- Pydantic model configuration: `https://docs.pydantic.dev/latest/api/config/`
- Pydantic fields/constraints: `https://docs.pydantic.dev/latest/api/fields/`

FastAPI `0.141.1` and Pydantic `2.13.5` remain confined to the HTTP composition boundary and define no
authorization/ranking semantics.

## Phase 6 resilience source

Phase 6 behavior is derived from the normative `SOURCE_ROADMAP.txt` resilience sections and formalized
in ADR-0007 plus `docs/project/FALLBACK_AND_RETRY.md`.

No new external runtime library or provider-specific resilience SDK was introduced for Phase 6. The
implementation uses Python standard-library async/time/hash primitives and the provider-neutral typed
error contract established in Phase 3.

Normative Phase 6 distinctions retained from the roadmap:

- retry targets the same deployment;
- fallback targets a different already-eligible deployment;
- transient availability failures are bounded/retryable;
- permanent policy/validation failures are not retried;
- external side effects and opaque provider state establish replay boundaries;
- circuit state is deployment-specific and may be initially per process;
- availability never broadens authorization.

These project requirements, rather than vendor documentation, define gateway retry/fallback policy.
Provider documentation may identify transport/status behavior but cannot grant authorization or
change replay safety.

## Phase 3 provider references

Official provider documentation reviewed on 2026-08-31 defines API-family wire behavior only; it does
not grant provider/model authorization or registry approval.

### OpenAI

- Responses API reference: `https://platform.openai.com/docs/api-reference/responses`

### Anthropic

- Messages API reference: `https://docs.anthropic.com/en/api/messages`

### Google Gemini

- Gemini API overview: `https://ai.google.dev/gemini-api/docs`
- Interactions API overview: `https://ai.google.dev/gemini-api/docs/interactions-overview`
- `generateContent` API reference: `https://ai.google.dev/api/generate-content`

Google documents Interactions as the recommended/default interface for new projects as of June 2026
while continuing to support `generateContent`. Phase 3 uses `generateContent` because the current
provider-neutral request owns canonical messages but not exact model-generated Interaction steps.

## Internal migration-pattern reference

- `brunovicco/controlled-autonomy-lab`, branch `main`, inspected 2026-08-31.
- Provider-port/error-boundary patterns were reviewed as migration guidance only.
- It is not a runtime/development dependency of the gateway.

## Source authority rule

Policy Model Router sources define authorization/provenance. Provider documentation defines transport
behavior. FastAPI/Pydantic documentation defines API framework/validation behavior. The normative
roadmap plus accepted gateway ADRs define ranking/resilience semantics.

No external source may broaden PDP authorization. Runtime health, retry, circuit, and fallback are
gateway-owned operational controls only after the upstream authorization boundary is established.
