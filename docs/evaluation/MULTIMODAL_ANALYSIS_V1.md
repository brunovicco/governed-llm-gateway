# Multimodal Analysis Benchmark v1

Status: deterministic credential-free benchmark contract implemented after the multimodal input, fixture-integrity, and immutable-publication foundations stabilized.

## Purpose

`multimodal-analysis-v1` measures whether a vision-capable target can inspect a real image and return a bounded structured answer. It is evaluation evidence only.

It does not authorize a model, mutate routing policy, or expand the Policy Router allowed set.

The permanent authorization invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Dataset contract

The initial v1 dataset contains one synthetic visual task backed by the checked-in fixture `multimodal.quadrants_rgb_001`.

The image is a deterministic 16 × 16 RGB PNG with four solid-color quadrants:

- `top_left`: `red`
- `top_right`: `green`
- `bottom_left`: `blue`
- `bottom_right`: `yellow`

Each benchmark case carries the reviewed fixture identity, media type, and SHA-256 digest in metadata. Dataset loading also validates that the same fixture ID and digest exist in both:

- the local fixture manifest, which is the content-integrity authority;
- the immutable publication manifest, which provides the provider-retrievable HTTPS URL.

A mismatch fails closed before a provider executor can run.

## Expected provider output

The executor must normalize a successful provider response into a JSON object with exactly four fields:

```json
{
  "top_left": "red",
  "top_right": "green",
  "bottom_left": "blue",
  "bottom_right": "yellow"
}
```

The benchmark scorer does not call another model and does not access the network.

## Deterministic scoring

`multimodal_analysis_v1` scores the four quadrants independently:

- each exact quadrant/color match contributes `0.25`;
- a wrong color or wrong label type loses only that quadrant's credit;
- a response with missing or extra top-level fields is an invalid output shape and scores `0`;
- full success requires score `1.0` with no issues.

The assessment also emits bounded reason codes such as:

- `wrong_color`;
- `wrong_label_type`;
- `invalid_output_shape`.

This makes benchmark failures explainable without introducing LLM-as-judge variability.

## Execution boundary

Default CI validates the dataset, fixture bindings, scorer behavior, typing, security, and repository architecture without making a provider call or downloading the published fixture.

A future live benchmark executor may use the publication URL to construct the provider-neutral image input. That executor must preserve provider failures as availability evidence distinct from model-quality evidence.

Provider/network availability is not authorization evidence.

## Promotion boundary

This increment registers the workload and deterministic scorer, but it does not automatically publish ranking evidence or change routing behavior.

Any later promotion of multimodal scorecards into ranking evidence must remain explicit, versioned, reviewable, and reversible under the existing benchmark-promotion contract.
