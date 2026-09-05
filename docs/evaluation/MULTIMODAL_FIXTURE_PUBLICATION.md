# Multimodal Fixture Publication

Status: provider-retrievable publication boundary defined after the local fixture foundation and checked-in catalog.

## Purpose

The local multimodal fixture catalog proves which bytes belong to a benchmark case. Native multimodal provider APIs, however, consume the gateway's provider-neutral HTTPS image URL contract rather than local filesystem bytes.

A live multimodal benchmark therefore needs a separate publication artifact that maps each verified local fixture to a public, immutable HTTPS URL without making network access part of default CI.

## V1 contract

`publication.json` is separate from the local `manifest.json` and contains:

```json
{
  "schema_version": "1.0",
  "data_classification": "public",
  "publications": [
    {
      "fixture_id": "multimodal.quadrants_rgb_001",
      "digest": "sha256:<fixture digest>",
      "source": "github_raw_commit",
      "source_revision": "<40-character commit SHA>",
      "url": "https://raw.githubusercontent.com/.../<same commit SHA>/.../fixture.png"
    }
  ]
}
```

V1 deliberately supports only GitHub raw URLs pinned to a full commit SHA. Mutable refs such as `main`, tags without an independently reviewed immutability contract, query-bearing URLs, fragments, userinfo, alternate hosts, and non-standard HTTPS ports are rejected.

The publication catalog must map one-to-one to the local fixture catalog and must preserve the exact fixture SHA-256 digest. Publication metadata cannot introduce an unknown fixture or substitute content with a different digest.

## Trust boundary

Default CI validates publication metadata and its relationship to the locally verified fixture catalog without downloading the remote URL. The local fixture remains the content-integrity authority for deterministic tests.

A future live-provider benchmark executor may pass the reviewed publication URL to the gateway/provider. Provider-side URL retrieval is availability/execution evidence, not authorization. A network failure must remain separate from model-quality scoring.

The first checked-in publication uses the repository commit that already contains the reviewed fixture bytes. The URL is therefore commit-pinned rather than branch-pinned.

## Non-goals

This increment does not:

- introduce `multimodal_analysis-v1`;
- call any provider in default CI;
- download published fixtures inside the gateway;
- create a generic remote-file downloader;
- add benchmark evidence to runtime authorization;
- promote multimodal evidence into ranking automatically;
- change Policy Router vocabulary;
- change the Phase 14 consumer sequence.

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```
