# Grounded RAG Answer Benchmark v1

Status: **COMPLETE — merged in PR #58.**

## Purpose

`rag-answer-v1` measures whether a model can answer from reviewed synthetic source
records and cite the source IDs that support the answer.

It is intentionally separate from `rag-ptbr-v1`. The historical PT-BR workload measures
required-fact coverage and explicit forbidden-claim regressions. `rag-answer-v1` adds
source-record identity and deterministic citation-grounding evidence without rewriting
the historical benchmark.

## Versioned contract

- workload: `rag_answer`
- benchmark version: `rag-answer-v1`
- contract version: `1.0`
- scorer: `rag_answer_v1`
- response format: `grounded_answer_v1`
- data classification: `public`
- cases: six synthetic cases
- reviewed languages: `en`, `pt-BR`
- retrieval execution: none
- LLM-as-judge: none

Each case contains at least two immutable synthetic source records. The exact source
records are materialized into the canonical prompt and repeated in validated metadata so
the scorer can verify source identities without relying on hidden executor behavior.

## Expected output

The model must return only:

```json
{
  "answer": "Temporary access expires after 24 hours and requires manager approval.",
  "citations": ["access-policy"]
}
```

The top-level object must contain exactly `answer` and `citations`. Citation values are
reviewed `source_id` strings from the case.

## Deterministic scoring

The scorer exposes two components:

1. `fact_score` — case-insensitive coverage of the reviewed required facts in `answer`;
2. `citation_score` — set F1 between observed citations and the reviewed supporting
   source IDs.

The scalar score is:

```text
(fact_score + citation_score) / 2
```

A known but irrelevant citation lowers citation precision. A missing supporting citation
lowers citation recall. Unknown/invented source IDs fail closed with zero quality evidence.

Explicitly reviewed forbidden claims also force zero quality. This remains a narrow
regression guard and does not claim arbitrary factuality detection.

Reference ground truth is validated independently: every reviewed required fact must occur
in the combined text of the reference citations. A known citation that does not support the
reviewed facts is rejected instead of becoming misleading benchmark truth.

## Fail-closed validation

Dataset/case validation rejects, among other things:

- the wrong benchmark version;
- duplicate case IDs;
- a case count other than exactly six;
- workloads or scorers outside the reviewed v1 contract;
- unknown metadata;
- non-public/non-synthetic drift;
- languages outside the reviewed `en` / `pt-BR` set;
- malformed or duplicate source IDs;
- fewer than two reviewed source records;
- expected citations that reference undeclared sources;
- expected citations whose reviewed source text does not support every required fact;
- prompt/source drift;
- reference answers missing reviewed required facts;
- reference answers containing reviewed forbidden claims.

Provider output fails closed on malformed output shape, invalid/duplicate citation lists,
or citations to unknown sources.

## Evidence boundary

`rag-answer-v1` evaluates answer grounding against checked-in evidence. It does not
perform retrieval and therefore cannot prove:

- which documents a production retriever returned;
- vector-search or reranker quality;
- authorization to access a data source;
- freshness of an external knowledge base;
- runtime citation URL validity;
- provider availability or tool execution.

Those are separate runtime/retrieval facts and require their own provenance.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Source IDs, required facts, citations, scores, observations, and snapshots are benchmark
ground truth/evidence only. They cannot:

- authorize a model, provider, deployment, data source, tool, or side effect;
- expand the PDP-authorized set;
- force benchmark target identity into runtime routing;
- bypass ordinary gateway eligibility, ranking, retry, or fallback;
- self-promote or mutate policy.

Benchmark quality may become ranking evidence only through the existing explicit,
attributable promotion path and only among already-authorized and eligible candidates.

## CI boundary

Default CI remains credential-free, deterministic, and replayable:

- no live provider is required by contract tests;
- no embeddings, retrieval service, vector database, or network call is used;
- no citation target is fetched;
- no LLM-as-judge path exists;
- checked-in source records and the deterministic scorer are sufficient for replay.

## Non-goals

Version 1 does not introduce:

- live retrieval or RAG orchestration;
- embedding or reranking benchmarks;
- citation URL fetching;
- arbitrary factuality judging;
- provider-specific grounding semantics;
- benchmark-side model/provider forcing;
- automatic promotion or self-modifying policy.
