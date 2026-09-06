# RAG PT-BR v2 Benchmark

Status: **COMPLETE — merged in PR #67; issue #66 closed after validated post-merge CI.**

## Purpose

`rag-ptbr-v1` remains the historical deterministic PT-BR RAG contract. It measures reviewed
required-fact coverage and fails quality when an explicit unsupported `forbidden_claim` appears.
It does not independently measure language quality.

`rag-ptbr-v2` adds a separate, bounded PT-BR language-quality component without rewriting v1.
The v2 contract is intentionally narrower than a general fluency or grammar judge: it measures
reviewer-authored Brazilian Portuguese locale/terminology conformance in public/synthetic cases.

## Evidence dimensions

Each completed v2 case produces two independent deterministic components:

- `grounding` — reviewed fact coverage, forced to zero when a reviewed unsupported claim appears;
- `pt_br_quality` — mean conformance across explicit case-local terminology rules.

The scalar workload score remains convenient for the historical benchmark runner interface:

```text
if unsupported reviewed claim is present:
    score = 0
else:
    score = (grounding + pt_br_quality) / 2
```

The component values remain separately preserved in benchmark observations and scorecards.

## PT-BR quality rule

Each case contains at least two reviewed locale rules:

```json
{
  "preferred": ["usuário"],
  "rejected": ["utilizador"]
}
```

A rule scores `1` only when the output contains at least one reviewed preferred term and no reviewed
rejected term. Otherwise the rule scores `0`. The case `pt_br_quality` value is the arithmetic mean
of its rule results.

Matching is deterministic, Unicode NFC aware, case-insensitive and phrase-boundary aware. This avoids
substring artifacts such as treating `equipa` as present inside another longer token.

Rejected terms mean "outside the reviewed Brazilian locale terminology for this synthetic benchmark
case". They are not a universal claim that a word is linguistically invalid in every Portuguese
variety or context.

## Dataset integrity

`rag-ptbr-v2` fails closed unless:

- workload remains `rag_ptbr` and scorer remains `rag_ptbr_v2`;
- metadata keys match the v2 contract exactly;
- language is exactly `pt-BR` and data is explicitly synthetic/public;
- the reviewed source context appears verbatim in the model prompt;
- the prompt explicitly requests `português do Brasil`;
- every expected fact appears in the reviewed context;
- reviewed unsupported claims do not appear in the context;
- at least two language-quality rules are present;
- preferred and rejected terminology is normalized, unique and disjoint;
- every rule has reviewed preferred terminology supported by the source context;
- rejected locale terminology does not appear in the source context.

The checked-in v2 dataset contains six cases spanning security, data handling, incident response,
mobile operations, transport and logistics. Each case uses two independently reviewed terminology
rules.

## Explicit non-claims

This benchmark does **not** claim to measure arbitrary:

- Portuguese fluency;
- complete grammar correctness;
- semantic equivalence of unrestricted paraphrases;
- writing style or tone;
- cultural appropriateness;
- dialect quality outside the reviewed Brazilian locale terminology;
- factuality beyond the checked-in required/forbidden evidence.

Those would require additional explicit evaluation contracts rather than silently expanding what this
score means.

## Execution boundary

The v2 path remains credential-free and deterministic in default CI. It does not use:

- provider calls during scoring;
- embeddings or retrieval services;
- language-detection services;
- network access;
- LLM-as-judge evaluation;
- hidden chain-of-thought;
- business tools or side effects.

The prompt is self-contained for future reviewed live execution because the checked-in source context
is materialized into the prompt. A future provider-backed benchmark must still pass through ordinary
gateway authorization, eligibility, ranking, resilience and target/effective-execution integrity
checks.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

`grounding`, `pt_br_quality`, the scalar score, snapshots and any later explicitly promoted evidence
remain non-authorizing evidence. This benchmark cannot force a target into routing, widen eligibility,
mutate policy, self-promote or change ranking weights implicitly.

## Phase 14 sequencing

Issue #18 remains authoritative. OpsLens stays deferred, and RAGForge must not start in parallel
unless the normative integration order is explicitly revised.
