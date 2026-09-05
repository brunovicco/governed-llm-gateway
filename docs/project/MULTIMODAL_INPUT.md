# Multimodal Input Foundation

Status: bounded image-input runtime plus deterministic multimodal benchmark foundations implemented after the core execution baseline stabilized.

## Scope

The multimodal runtime currently supports **image understanding input only**. It does not add image generation or a general file transport.

Provider-neutral messages may carry bounded image references alongside text:

```text
Message
  ├─ role = user
  ├─ content = non-empty text at the API/SDK boundary
  └─ images[]
       ├─ media_type = image/jpeg | image/png | image/webp
       └─ url = absolute HTTPS URL
```

Limits:

- at most 8 images per message;
- at most 16 images per gateway request;
- images are accepted only on `user` messages in v1;
- any request containing images must declare `WorkloadRequirements.vision = true`;
- image URLs are limited to 2048 characters;
- URL userinfo, query strings, and fragments are rejected;
- the gateway does **not** resolve or fetch the image URL.

Keeping URL retrieval outside the gateway avoids adding a downloader, base64 body amplification, file persistence, or an SSRF-capable HTTP client to the gateway process. Provider-native URL retrieval rules still apply downstream.

Signed URLs are deliberately outside v1 because their query strings commonly carry credentials. Base64, provider file IDs, PDFs, audio, video, and image-only messages require separate reviewed contracts.

## Capability and authority boundaries

Model/deployment eligibility requires the vision capability and image modality to be declared together in the registry. A request with `requirements.vision = true` therefore narrows the already-authorized candidate set to deployments advertising vision.

The provider wire contract is a separate concern. `ProviderFeatureSupport.native_image_input` defaults to `false`; an adapter must opt in only when its exact API family has a reviewed native translation. Registry capability never implies wire-format support automatically.

The permanent authorization invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Image input cannot add model groups or deployments. It only creates another gateway-side eligibility/execution constraint.

Policy Model Router API 1.0 does not currently receive a dedicated vision flag. The gateway can still narrow PDP authorization through registry capability checks without violating monotonic authorization. Expanding the PDP request vocabulary is a separate cross-repository contract change and must not be inferred from this increment.

## Reviewed adapter support

### OpenAI Responses

Native OpenAI Responses maps a provider-neutral user message to Responses content parts:

```json
{
  "role": "user",
  "content": [
    {"type": "input_text", "text": "Describe the image."},
    {"type": "input_image", "image_url": "https://images.example/image.png"}
  ]
}
```

Native and streaming Responses paths share the same translation.

### Anthropic Messages

Native Anthropic Messages maps the same provider-neutral message to content blocks, placing image blocks before the text block:

```json
{
  "role": "user",
  "content": [
    {
      "type": "image",
      "source": {
        "type": "url",
        "url": "https://images.example/image.png"
      }
    },
    {"type": "text", "text": "Describe the image."}
  ]
}
```

Non-streaming and streaming Anthropic paths reuse the same translation helper and both advertise `native_image_input = true`.

Anthropic supports additional image formats in some API configurations, but the provider-neutral gateway contract remains deliberately narrower: JPEG, PNG, and WebP only. Provider capability does not automatically widen the gateway contract.

### Google Gemini generateContent

Native Gemini `generateContent` and `streamGenerateContent` map provider-neutral image references into `fileData` parts and preserve the declared MIME type:

```json
{
  "role": "user",
  "parts": [
    {
      "fileData": {
        "mimeType": "image/png",
        "fileUri": "https://images.example/image.png"
      }
    },
    {"text": "Describe the image."}
  ]
}
```

Non-streaming and streaming Gemini paths reuse the same `_google_contents()` translation helper and advertise `native_image_input = true` for the API family.

External HTTPS URL support is model-sensitive. Gemini 2.0 models do not support this external-URL file-input method, so the adapter rejects `gemini-2.0*` image requests deterministically before provider I/O. That preflight is an execution compatibility constraint; it does not grant or widen model authorization.

Google may support signed external URLs, but the provider-neutral gateway v1 contract still rejects URL query strings. Provider support does not override the gateway's privacy and credential-handling boundary.

### Still fail-closed

Generic OpenAI-compatible adapters intentionally remain `native_image_input = false`. Compatibility labels alone are not enough to infer a reviewed multimodal wire format, so direct image calls fail closed before provider I/O.

## Multimodal benchmark path

The post-core multimodal benchmark is implemented through separate reviewed boundaries rather than a single provider-coupled runner.

### Fixture integrity and publication

The benchmark fixture catalog is local, public and content-addressed. It verifies normalized relative paths, JPEG/PNG/WebP media signatures, size bounds, root containment and SHA-256 before bytes are exposed.

The initial visual fixture is `multimodal.quadrants_rgb_001`, a deterministic 16 × 16 RGB PNG. Its publication record is separately bound to the exact fixture digest and a commit-pinned `raw.githubusercontent.com` HTTPS URL. Default CI validates publication metadata without downloading the remote image.

### `multimodal-analysis-v1`

The benchmark workload evaluates actual visual input rather than a text surrogate. The initial case asks for the colors of four image quadrants and uses deterministic scoring: each exact quadrant/color match contributes `0.25`; invalid top-level shape scores zero; no LLM-as-judge is used.

### Provider-neutral gateway materialization

A validated multimodal case plus immutable fixture publication can be materialized into the existing `GatewayRequest` contract with:

- caller-provided request/workload identity;
- public / low-risk benchmark context;
- `requirements.vision = true`;
- non-empty benchmark prompt;
- one provider-neutral `ImageInput` pointing at the commit-pinned publication URL.

This is not authorization and does not force a provider/model/deployment. The request must pass through the normal policy, registry, ranking, resilience and provider-execution path.

### Terminal benchmark evidence

A terminal `GatewayResponse` can be normalized into `ProviderCall` evidence while keeping successful-but-malformed output as model-quality evidence and provider/gateway failures as availability evidence.

Where available, terminal evidence preserves provider/model/deployment identity, `api_family`, `max_output_tokens`, latency, fallback index, normalized token usage and optional cost. Benchmark target schemas can require exact API-family and max-output attestation before scoring.

There is still no benchmark-side model-forcing bypass and no live provider/network requirement in default CI.

## Privacy and observability

Image URLs are request content. They must not be added to metadata-only OpenTelemetry attributes, routing evidence, benchmark evidence, or logs by default.

Existing telemetry continues to record bounded metadata such as workload, provider/model/deployment identity, latency, retries/fallbacks, and normalized usage. The gateway does not capture the referenced image bytes.

Benchmark fixture bytes are local evaluation inputs, not runtime telemetry. Their digest and stable fixture identity may appear in benchmark provenance, but raw fixture bytes should not be copied into scorecards, routing evidence, or logs.

## Deferred

- base64/inline image data;
- signed/query-bearing URLs;
- provider-hosted file IDs;
- PDFs and arbitrary file inputs;
- audio/video input;
- image output/generation;
- image preprocessing or fetching by the gateway;
- implicit vision inference from message shape without `requirements.vision`;
- generic OpenAI-compatible image support without endpoint-specific verification;
- benchmark-side provider/model forcing;
- credential-bearing live-provider benchmark execution in default CI;
- automatic promotion or routing mutation from multimodal benchmark evidence.
