# PDP/PEP composition proof

The authority chain this portfolio is built around is

`Verifiable AI Governance → Policy Model Router → Governed LLM Gateway → model provider`

Every hop is tested. Until this proof, the middle hop had never been *executed*: the Gateway's
contract tests assert the wire shape it sends, the Router's assert the wire shape it accepts, and
nothing ran the two against each other.

That gap matters more than it looks. Neither repository may import the other, and the canonical
Ed25519 signing bytes must stay byte-identical across both, so each keeps a **hand-written mirror**
of the Verifiable AI Governance runtime-authorization contract:

| Side | Mirror |
|---|---|
| Policy Model Router | `application/runtime_authorization_contract.py` |
| Governed LLM Gateway | `adapters/governance_authorization.py` |

If those drift by one field, signature verification fails in production and **neither CI notices**.
This stack is what notices.

## What it runs

A real Policy Model Router container with `RUNTIME_AUTHORIZATION_REQUIRED=true`, Redis behind it
for replay state, and the Gateway's own PDP adapter — loaded from a real
`policy_router.json` through `build_policy_router_adapter`, not hand-assembled — calling it over
the loopback transport.

Four scenarios:

| # | Scenario | Expected |
|---|---|---|
| 1 | a forwarded envelope | `reasoning-medium` authorized |
| 2 | the same request with no envelope | non-retryable authorization denial |
| 3 | an envelope signed by a key the Gateway trusts and the Router does not | denial |
| 4 | the scenario-1 envelope, replayed | denial |

Scenario 2 is the behavior that made the pair unusable before the Gateway learned to forward. It
stays in the proof so the regression is visible rather than remembered.

Scenario 3 is why the Gateway's key resolver trusts *both* keys: if the Gateway refused the rogue
envelope first, the scenario would only prove the Gateway has an allowlist, which its own unit
tests already cover. The envelope has to reach the Router for the Router's refusal to mean
anything.

All three denials surface at the Gateway as one non-retryable authorization failure with no
provider call. That is the design, not a gap — the Router does not tell a caller *why* it denied.
The reasons (`runtime_authorization_required`, `unknown_key`, `replay_detected`) live in the
Router's own logs:

```bash
docker compose -f compose.pdp-composition.yml logs policy-model-router
```

## Running it

The Router is built from a sibling checkout. Clone it next to this repository, or point
`POLICY_MODEL_ROUTER_PATH` somewhere else.

```bash
uv run python -m scripts.composition_fixture \
    --write-key-set .composition/runtime-authorization-keys.json
docker compose -f compose.pdp-composition.yml up -d --build
uv run python -m scripts.composition_proof
docker compose -f compose.pdp-composition.yml down -v
```

The key set is generated rather than committed because it carries the public half of a key derived
at run time, and an envelope cannot be committed at all: the Router binds `requested_at` to the
signed `issued_at`, so every envelope is good for five minutes and is minted fresh on each run.

## What the fixture is, and is not

`scripts/composition_fixture.py` mints the envelope. Governance is the only system allowed to sign
one and it does not exist as a running service yet, so something has to stand in. The fixture is
deliberately **not** a Governance implementation: its signing key is derived from a sentence
printed in plain text in the file, nothing in `governed_llm_gateway_core` imports it, and its
output only ever reaches a throwaway container.

Two details in it are load-bearing:

- The Router recomputes the signing bytes from its **parsed pydantic model**, not from the bytes
  it received. Every value therefore has to already be in the form pydantic emits — UTC timestamps
  as `...Z` without microseconds, UUIDs lowercase and hyphenated, every set-like collection sorted
  and deduplicated. A hand-rolled envelope that looks right and sorts differently verifies on the
  Gateway and fails on the Router.
- `audience` lists **both** service names. Each side checks that its own name is present, so a
  composed deployment needs an envelope addressed to both. Neither repository's documentation said
  so before the two ran together.

## Three things this surfaced

Worth recording, because each is a composition fact that no single-repository test could have
produced:

1. **Request identity comes from the envelope.** The Router binds `requested_at`, `workflow_id` and
   `task_id` to the signed claims, and the Gateway's own clock and request id differ from them by
   construction. Forwarding without moving the request identity would have traded one guaranteed
   denial for another.
2. **Workload identifiers have to be dotted.** The Gateway requires a dotted workload
   (`credit.cashflow-analysis`); the Router accepts any policy identifier and its shipped example
   policy uses underscores. Both are valid alone; composed, the dotted form is the only one that
   works. That is why this proof mounts a routing policy of its own.
3. **Every model group must be reachable.** The Router rejects a policy containing a group no
   workload maps to unless it is marked `staged: true`. The first draft of this proof's policy had
   a second group with no workload, purely to make `rejected_candidates` non-empty, and the Router
   refused to start.

## What it still does not prove

- **A deployed-environment Router.** `APP_ENV=development` with enforcement on is the enforcing
  configuration minus what `staging`/`production` additionally mandate: Governance Runtime Control,
  which needs a Governance projection that does not exist yet. Redis is here, so replay protection
  runs in its real cross-replica shape rather than the in-process fallback.
- **A real Governance issuer.** See the fixture section above.
- **Provider execution.** The proof stops at authorization. Nothing downstream of the PDP decision
  runs, and no provider credential is needed.
- **CI.** Default CI has no second repository checked out and no Docker-in-Docker, so this is run
  by hand. The wire shape remains pinned on each side by
  `tests/contract/test_pdp_runtime_authorization_forwarding.py` here and by the Router's own
  `AuthorizedModelRouteRequest` contract there; this proof is what confirms the two agree.
