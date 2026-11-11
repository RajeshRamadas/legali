# Background verification provider usage

Administrators can open **Provider usage** at `/admin/ai-usage`. Case staff see a
usage summary on each accessible background job. This covers full-case background
verification calls recorded after migration `0042_verification_usage`; synchronous
verification, upload classification, chat, research and historical calls remain
outside this scope. Local extraction makes no provider attempts. No calls are
backfilled, and opening the dashboard never contacts a provider.

## Recorded information

Each request records a durable `started` attempt before contacting the provider.
Completion updates that row with the outcome, monotonic elapsed milliseconds,
reported input/output/cache tokens and a safe failure category. The elapsed time
includes provider work and response validation, but excludes queue wait, document
reading and the initial recording transaction. Failed response validation can
still have reported tokens and an estimate. Transport/HTTP errors without usable
counters retain unknown usage; they are not treated as free calls.

Worker termination can leave an unfinished attempt. Its outcome and billing are
unknown; do not infer a retry is free. Initial recording failure prevents sending.
Final recording failure fails the job and leaves the started record for review.
There are no new automatic provider retries, spending caps or billing reconciliation.
Cancellation, stale evidence and discarded results do not erase incurred attempts.

Rows contain UUID case/job references, provider/model, extraction/comparison stage,
times, counters, configured price snapshots and fixed reason codes. They contain
no document text, prompts, filenames, storage paths, customer identity, contacts,
provider response bodies, provider request IDs, endpoint URLs or credentials.
References are intentionally not foreign keys: recording never takes a case
reference lock, and removing a case must not erase already incurred attempts.
These retained operational references need to be included in any future retention
policy. This feature adds no automatic deletion policy. Rows are mutable by the
internal recorder and are not an append-only audit or a billing ledger.

## Configure optional USD estimates

Estimates are unavailable by default. Review the actual provider/endpoint price
contract, then set `VERIFICATION_TOKEN_RATES` consistently on API and verification
worker. Compose forwards it through the shared API environment. Restart processes
after configuration changes. Keys use the exact `provider/model` sent by the
adapter, including model overrides. An OpenAI-compatible endpoint requires prices
for that actual endpoint, which may differ from OpenAI's own prices.

The following prices are **fictional examples**, not current provider rates:

```json
{"version":"reviewed-2026-11","models":{"anthropic/example-model":{"input_per_million":"1.00","output_per_million":"2.00"},"openai/example-model":{"input_per_million":"1.00","output_per_million":"2.00"}}}
```

The version permits 1–40 letters, digits, periods, underscores or hyphens. There
can be 1–40 model entries; model identifiers permit letters, digits, `.`, `_`,
`:`, `/`, `-` and at most 120 characters. Prices must be finite, nonnegative USD
per million tokens, no more than 1,000,000 and no more than six decimal places.
Use decimal strings. Duplicate/extra keys and malformed values disable estimates
and surface a safe configuration warning; analysis continues. Configuration is
server controlled, without a browser editing endpoint.

Each attempt snapshots matching rates and the version before sending. Cost is
`(input_tokens * input_rate + output_tokens * output_rate) / 1,000,000`, rounded
half up to twelve decimal places. Old estimates never change when rates change.
Explicit zero usage/rates can produce a true zero estimate; missing usage stays
unavailable. Anthropic input includes reported uncached input plus cache read/write
input; the OpenAI adapter's prompt count already includes cached input. Any reported
cache usage is left unpriced because cache read/write contracts differ. There is
no guessed token count or assumed current public price.

## Review and filtering

`GET /api/v1/admin/verification-usage` requires administrator access and uses the
shared lookup budget. Responses, including access failures, are private/no-store.
Filters: `provider=all|anthropic|openai`, `step=all|extract|compare`,
`status=all|started|succeeded|failed`, `days=1..90` (default 30), optional UUID
`job_id`, `page=1..10000`, `page_size=1..100` (default 25). Calendar windows begin
at India midnight `days-1` days before the check date and end at the check time.
Rows sort by start time then ID, newest first. Live updates between pages can
change counts/order; refresh for a new observation.

Totals cover matching attempts, including off-page rows. Tokens are sums of known
complete counter pairs. The known cost subtotal includes priced attempts only;
unpriced and unfinished counts remain visible. Average elapsed time includes
finished successes and failures. No attempts means no estimate, not zero spend.
Very small positive estimates display `< $0.000001 USD`; exact row decimals are
available under estimate details. These amounts are not invoices, customer fees
or proof of a legally valid analysis. Human legal review is still required.

The dashboard uses explicit Apply/Clear/Refresh, preserves unapplied filters while
paging/refreshing, and labels retained snapshots after lookup failures. Per-job
summaries use one grouped query per page and retain existing case permissions;
agents cannot use the cross-case administrator API. There is no export or edit API.

Apply `alembic upgrade head` before starting API/worker. Migration 0042 creates an
empty table without touching existing verification results or audit data. Empty
downgrade is supported; downgrade refuses once usage rows exist. Use a reviewed
forward fix or recovery procedure instead of deleting operational history.

Tests use mocked provider transports and synthetic disposable databases. No paid
calls are required to validate this feature. Live pricing approval, provider
invoice reconciliation, quality evaluation, broader AI coverage and retention
controls remain separate operational work.
