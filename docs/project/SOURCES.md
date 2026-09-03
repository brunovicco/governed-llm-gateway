# Sources

## Normative project source

- `SOURCE_ROADMAP.txt` — user-supplied Governed LLM Gateway project plan, preserved verbatim and used
  as the normative phase/scope/architecture source.

## Development harness reference

- `brunovicco/codex-python-engineering-harness`, branch `main`, inspected 2026-08-31.
- Harness README documents the `workspace` profile and `agentic` governance profile.
- Workspace template structure remains guidance only, not a runtime dependency.

## Policy Model Router contract reference

- `brunovicco/policy-model-router`, branch `main`, inspected after workload/model-group generalization.
- `src/policy_model_router/domain/routing.py` defines request/decision provenance.
- `src/policy_model_router/application/route_model.py` defines fail-closed routing semantics.
- `src/policy_model_router/domain/constraints.py` defines ordered policy constraints.
- `src/policy_model_router/entrypoints/contracts.py` and `entrypoints/http.py` define `POST /route`
  schema `1.0` used by the gateway.

The gateway integrates with the Policy Model Router through the versioned HTTP contract rather than
importing its Python domain/application types.

## Phase 5 API framework references

Official framework documentation reviewed for the authenticated explain/API composition boundary:

- FastAPI dependency injection: `https://fastapi.tiangolo.com/tutorial/dependencies/`
- FastAPI version guidance: `https://fastapi.tiangolo.com/deployment/versions/`
- Pydantic model configuration: `https://docs.pydantic.dev/latest/api/config/`
- Pydantic fields/constraints: `https://docs.pydantic.dev/latest/api/fields/`

FastAPI/Pydantic define HTTP validation/composition only and have no authorization/ranking authority.

## Phase 6 resilience source

Phase 6 behavior is derived from the normative roadmap and formalized in ADR-0007 plus
`docs/project/FALLBACK_AND_RETRY.md`.

Gateway-owned policy distinguishes same-deployment retry from already-ranked authorized fallback,
keeps permanent policy/semantic failures non-retryable, and stops replay after output/side effects or
opaque provider state. Provider documentation cannot widen these semantics.

## Phase 7 structured-output and tool references

Normative Phase 7 scope comes from the roadmap and is formalized in ADR-0013 plus
`docs/project/STRUCTURED_OUTPUT_AND_TOOLS.md`.

Official provider/library references define wire/schema behavior only:

### OpenAI

- Responses API reference: `https://platform.openai.com/docs/api-reference/responses`

### Anthropic

- Messages API reference: `https://docs.anthropic.com/en/api/messages`
- Tool-use overview: `https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview`

### Google Gemini

- `generateContent` API reference: `https://ai.google.dev/api/generate-content`
- Function-calling guide: `https://ai.google.dev/gemini-api/docs/generate-content/function-calling`

### JSON Schema validation

- `jsonschema` PyPI: `https://pypi.org/project/jsonschema/`
- `types-jsonschema` PyPI: `https://pypi.org/project/types-jsonschema/`
- runtime: `jsonschema==4.26.0`;
- mypy-only ephemeral stub: `types-jsonschema==4.26.0.20260518`.

ADR-0013 intentionally imposes stricter gateway-side validation and authority boundaries than provider
wire-format support alone.

## Phase 8 streaming references

Normative Phase 8 behavior comes from `SOURCE_ROADMAP.txt` and is formalized in ADR-0011 plus
`docs/project/STREAMING.md`.

Provider documentation defines event/wire formats only. The gateway ADR defines replay cutoff,
authorization preservation, usage finalization, cancellation, and evidence semantics.

### OpenAI Responses streaming

- Responses API reference: `https://platform.openai.com/docs/api-reference/responses`

The native adapter maps documented Responses streaming events into the gateway provider-neutral event
contract. Provider event availability does not grant model authorization.

### Anthropic Messages streaming

- Messages API reference: `https://docs.anthropic.com/en/api/messages`
- Streaming Messages documentation is part of the Anthropic Messages API documentation set.

The gateway accumulates incremental tool JSON and validates the complete call locally before emitting
canonical completion.

### Google Gemini streaming

- `streamGenerateContent` is documented through the Gemini `generateContent` API family:
  `https://ai.google.dev/api/generate-content`
- Function-calling reference:
  `https://ai.google.dev/gemini-api/docs/generate-content/function-calling`

The gateway requires canonical correlation identity for streamed function calls and does not synthesize
missing provider IDs.

### HTTPX

- HTTPX async/streaming documentation: `https://www.python-httpx.org/async/`
- HTTPX exceptions: `https://www.python-httpx.org/exceptions/`

Phase 8 uses `httpx==0.28.1` for the dedicated asynchronous SSE transport. It remains an adapter-layer
transport dependency, not an authorization or routing dependency.

### Coverage enforcement

- Coverage.py command documentation: `https://coverage.readthedocs.io/`
- Phase 8 quality enforcement runs pytest-cov and then a separate Coverage.py
  `coverage report --fail-under=80` command.

This second check is a repository quality control only; it has no runtime effect.

## Phase 3 provider references

Official provider documentation originally reviewed for provider execution foundation:

- OpenAI Responses API: `https://platform.openai.com/docs/api-reference/responses`
- Anthropic Messages API: `https://docs.anthropic.com/en/api/messages`
- Gemini API overview: `https://ai.google.dev/gemini-api/docs`
- Gemini `generateContent`: `https://ai.google.dev/api/generate-content`

The native Gemini adapter remains on the `generateContent` API family because the canonical gateway
request does not fabricate provider-specific continuation/reasoning state.

## Internal migration-pattern reference

- `brunovicco/controlled-autonomy-lab`, branch `main`, inspected 2026-08-31.
- Provider-port/error-boundary patterns were migration guidance only and are not runtime dependencies.

## Source authority rule

Policy Model Router sources define authorization/provenance. Provider documentation defines transport
and API-family representation. FastAPI/Pydantic define HTTP framework behavior. JSON Schema/HTTPX
libraries define implementation mechanics. The normative roadmap plus accepted gateway ADRs define
authorization, ranking, resilience, structured-output/tool authority, streaming replay/cancellation,
and evidence semantics.

No external source may broaden PDP authorization. Provider feature support is an execution capability,
not an authorization grant.
