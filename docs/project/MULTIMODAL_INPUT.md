# Multimodal Input Foundation

Status: initial image-input contract implemented after the core execution baseline stabilized.

## Scope

The first multimodal increment adds **image understanding input only**. It does not add image generation or a general file transport.

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

Model/deployment eligibility already requires the vision capability and image modality to be declared together in the registry. A request with `requirements.vision = true` therefore narrows the already-authorized candidate set to deployments advertising vision.

The provider wire contract is a separate concern. `ProviderFeatureSupport.native_image_input` defaults to `false`; an adapter must opt in only when its exact API family has a reviewed native translation. Registry capability never implies wire-format support automatically.

The permanent authorization invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Image input cannot add model groups or deployments. It only creates another gateway-side eligibility/execution constraint.

Policy Model Router API 1.0 does not currently receive a dedicated vision flag. The gateway can still narrow PDP authorization through registry capability checks without violating monotonic authorization. Expanding the PDP request vocabulary is a separate cross-repository contract change and must not be inferred from this increment.

## Initial adapter support

Native OpenAI Responses is the first explicitly enabled image-input API family. The adapter maps a provider-neutral user message to Responses content parts:

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

Anthropic Messages, Gemini `generateContent`, and generic OpenAI-compatible adapters intentionally remain `native_image_input = false` in this increment. Direct calls fail closed before provider I/O instead of silently dropping image content. Each API family should be enabled in its own reviewed adapter increment.

## Privacy and observability

Image URLs are request content. They must not be added to metadata-only OpenTelemetry attributes, routing evidence, benchmark evidence, or logs by default.

Existing telemetry continues to record bounded metadata such as workload, provider/model/deployment identity, latency, retries/fallbacks, and normalized usage. The gateway does not capture the referenced image bytes.

## Deferred

- base64/inline image data;
- signed/query-bearing URLs;
- provider-hosted file IDs;
- PDFs and arbitrary file inputs;
- audio/video input;
- image output/generation;
- image preprocessing or fetching by the gateway;
- implicit vision inference from message shape without `requirements.vision`;
- generic OpenAI-compatible image support without endpoint-specific verification.
