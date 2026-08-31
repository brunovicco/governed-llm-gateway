# Sources

## Normative project source

- `SOURCE_ROADMAP.txt` — user-supplied Governed LLM Gateway project plan, preserved verbatim in this
  repository and used as the normative phase/scope/architecture source.

## Development harness reference

- `brunovicco/codex-python-engineering-harness`, branch `main`, inspected 2026-08-31.
- Harness README documents the `workspace` profile as a virtual uv workspace with explicit members,
  and governance as an independent profile dimension including `agentic`.
- Workspace template `pyproject.toml` and `AGENTS.md` were used as structural guidance.

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
June 2026 while continuing to fully support `generateContent`. Phase 3 intentionally uses native
`generateContent` because the current provider-neutral request owns canonical message history but not
the exact model-generated Interaction steps required for lossless stateless Interactions history.
See `docs/project/PROVIDER_CONTRACT.md` for the architectural rationale.

## Internal migration-pattern reference

- `brunovicco/controlled-autonomy-lab`, branch `main`, inspected 2026-08-31.
- Its provider-port/error-boundary patterns were reviewed as migration guidance only.
- It is not a runtime or development dependency of the gateway; consumer-project dependency
  direction remains downstream-only.

## Source authority rule

Provider documentation may define transport fields, response shapes, and API behavior. It must not
be used as authorization evidence. Model/deployment eligibility remains governed by the gateway
registry plus the upstream Policy Model Router authorization boundary.
