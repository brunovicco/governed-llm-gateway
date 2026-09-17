# Estimated Spend Accounting

Per-client, per-workload accumulation of what execution implied, and budgets that refuse
a request once a ceiling is reached.

## Component scope, not current serving enforcement

`SpendGuard`, `SpendPolicy`, and `RedisSpendLedger` are component contracts/implementations.
The current API bootstrap and generation coordinators do not compose them into serving;
these component tests do not prove budget enforcement on a gateway endpoint. A future
serving integration must be separately reviewed. Per-request routing cost limits are not
the same contract as this accumulated-spend ledger.

## Estimated, never billed

Every amount here comes from two things: the Model Registry's **pinned pricing metadata**
and the provider's **reported token usage**. That pricing is reviewed at a source date
and can drift from a provider's live catalog — the `personal-default` profile says as
much about its own NVIDIA/Groq/OpenRouter entries.

So this is the gateway's estimate of what a call implied. It is not an invoice, it will
not reconcile exactly against provider billing, and nothing in the code or the operations
surface presents it as one. A deployment that needs billed figures reconciles against the
provider; this ledger is for *governance* — knowing which client and which workload is
consuming what, and stopping runaway spend before the bill arrives.

## Money is integer micro-USD

Budgets accumulate as integers, never floats. Two reasons, both concrete:

- A float ledger loses precision at exactly the scale that matters. A thousand calls at
  a tenth of a cent must total exactly one dollar, and a contract test asserts it does.
- A counter shared across replicas has to be incremented atomically. `INCRBY` on an
  integer is exact and atomic; a read-modify-write of a float is neither.

`Decimal` is the boundary type, micro-USD is the stored one, and conversion rounds half
up at the sixth decimal.

## A budget narrows, it never widens

In any future serving integration, the guard must run **after** the Policy Model Router
has authorized a request and before provider work. Its result is a budget check only, not
authorization. An exhausted budget removes permission to execute; it can never grant
permission. That keeps the permanent rule intact:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

A limit is exhausted when observed spend has **reached** it, not merely passed it. A
budget that still permits one more call at exactly its ceiling is a budget designed to be
exceeded.

## Fail closed on read, best effort on write

The two directions are deliberately asymmetric.

**Reading fails closed.** If the ledger cannot be read, the budget's state is unknown,
and proceeding would mean spending against a ceiling nobody can see. The request is
refused.

**Writing is swallowed.** A record is written after the caller already holds their
answer. Losing an estimate is bad; losing a delivered answer to a storage error is worse.

## A cached answer is never counted twice

A response served from cache records nothing. Its tokens were already counted when the
original call produced them, and counting them again would inflate the estimate every
time the same question is asked. This is what `ProviderExecution.cached` exists for.

## Policy configuration (component only)

Budgets are off by default, and an enabled policy that declares no limit is rejected
rather than read as "unlimited". A limit names a client, a window (`daily` or `monthly`)
and a ceiling; omitting the workload makes it client-wide. Two limits may not share a
scope.

Buckets carry an expiry sized to their window, because a ledger of estimated spend is
operational evidence rather than an accounting record, and keeping it indefinitely would
be a retention decision nobody made.

## What this is not

Not a billing system, not a quota system for tokens, and not a rate limiter. It does not
pre-authorize spend before a call — the cost of a call is not known until the provider
reports usage — so a single request can carry the ledger past its ceiling, and the
refusal lands on the *next* one. Tighter enforcement would require reserving an estimated
maximum before execution and settling afterwards, which is future work rather than a
silent gap.

## Concurrent checks are not reservations

`check` reads already-observed spend; it neither increments the ledger nor reserves
capacity for work in flight. With US$0.90 observed against a US$1.00 limit, two requests
can both pass before either records usage. Recording US$0.20 for each leaves US$1.30
observed; subsequent checks refuse. Even one sequential request can overshoot. Atomic
`INCRBY` prevents lost updates, not admission above an eventual ceiling. Separate limit
buckets are updated individually, not as one cross-scope transaction.

The deterministic regressions in `test_spend_guard_concurrency.py` use independent
guards/clients over one controlled RESP emulator. Events hold both request fixtures
between checking and recording, proving the order without timing sleeps. They cover
client-wide/workload daily/monthly limits, sequential/concurrent overshoot, refusal at
the exact ceiling, shared counter corruption, concurrent cached records, and separate
client/workload/window accounting. Existing tests also preserve read-outage denial and
best-effort write failure behavior. These are component/emulator proofs, not live
Redis/Valkey, actual replica processes, provider execution, billing or serving proofs.

No hard no-overshoot guarantee is supplied. Failed best-effort writes can undercount
observed spend. Before adding atomic reservation, define conservative estimation,
multi-scope admission, idempotent settlement, partial/failing writes, unknown usage,
retries/fallback, cancellation and retention/recovery. This increment changes none of
those runtime contracts and adds no reserve, release or settlement implementation.
