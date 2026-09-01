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

## Phase 7 structured-output and tool references

Normative Phase 7 scope comes from `SOURCE_ROADMAP.txt` and is formalized in ADR-0013 plus
`docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md`.

Official provider/library documentation reviewed on 2026-09-01 defines wire/schema behavior only; it
does not grant deployment capability or authorization.

### OpenAI

- Responses API reference: `https://platform.openai.com/docs/api-reference/responses`
- Responses/Structured Outputs reference documents `text.format` with `type: json_schema`, schema name,
  schema object, and strict schema adherence.
- Function tools are defined through the Responses `tools` collection and JSON-schema parameters.

### Anthropic

- Messages API reference: `https://docs.anthropic.com/en/api/messages`
- Tool-use overview: `https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview`
- Tool definitions use a name, description, and `input_schema`; model-produced client-side tool calls
  are returned as `tool_use` content blocks.
- Current Anthropic platform documentation also exposes strict tool/schema behavior; gateway-side
  validation remains mandatory regardless of provider enforcement.

### Google Gemini

- `generateContent` API reference: `https://ai.google.dev/api/generate-content`
- Function-calling guide:
  `https://ai.google.dev/gemini-api/docs/generate-content/function-calling`
- Gemini function declarations describe tool names/parameters and `functionCall` returns name/args.
- The API reference marks `FunctionCall.id` as optional in the general contract, while current Gemini 3
  function-calling guidance requires exact ID round-tripping and states Gemini 3 returns unique IDs.
  The gateway therefore requires an ID for canonical correlation and fails closed when absent.

### JSON Schema validation

- `jsonschema` PyPI: `https://pypi.org/project/jsonschema/`
- `types-jsonschema` PyPI: `https://pypi.org/project/types-jsonschema/`
- Phase 7 runtime pins `jsonschema==4.26.0` through the uv lock.
- `types-jsonschema==4.26.0.20260518` targets `jsonschema~=4.26.0` and is used only as an ephemeral mypy
  dependency, not as a runtime package.

### Gateway-owned safety decisions

Provider docs define how a feature is represented on the wire. ADR-0013 defines the stricter gateway
contract:

- prompted JSON is not equivalent to provider-native structured output;
- provider-native enforcement is followed by local output validation;
- caller schema validation is local/bounded and remote references are rejected;
- generic OpenAI-compatible endpoints do not inherit feature support implicitly;
- tool-call correlation IDs are not synthesized;
- business-tool execution authority remains outside the gateway;
- structured/tool semantic failures do not become retry/fallback availability signals.

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

The native Gemini adapter currently uses `generateContent` because the canonical gateway request does
not preserve every provider-generated continuation/reasoning step needed for lossless stateful
reconstruction. Phase 7 keeps that boundary explicit for tool-result continuation as well.

## Internal migration-pattern reference

- `brunovicco/controlled-autonomy-lab`, branch `main`, inspected 2026-08-31.
- Provider-port/error-boundary patterns were reviewed as migration guidance only.
- It is not a runtime/development dependency of the gateway.

## Source authority rule

Policy Model Router sources define authorization/provenance. Provider documentation defines transport
and API-family feature representation. FastAPI/Pydantic documentation defines API framework/validation
behavior. JSON Schema library documentation defines validator mechanics. The normative roadmap plus
accepted gateway ADRs define authorization, ranking, resilience, structured-output/tool authority, and
replay semantics.

No external source may broaden PDP authorization. Provider feature support is an execution capability,
not an authorization grant.
