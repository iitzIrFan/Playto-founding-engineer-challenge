# Playto Payout Engine Explainer

## 1) Ledger: model and balance calculation

The source of truth for merchant funds is the append-only `ledger_entry` table (model: `LedgerEntry`).

Key implementation details:
- `LedgerEntry` fields: `merchant` (FK), `amount_paise` (BigInteger), `type` (TextChoices: `CREDIT`, `HOLD`, `RELEASE`), `reference_id` (string), `created_at`.
- The model uses `db_table = "ledger_entry"` and has indexes on `merchant, created_at` and `reference_id`.
- Ledger entries are immutable: `save()` raises if attempting to update an existing row.

Balance is computed with a DB aggregation (see `ledger/services.get_merchant_balance_paise`):

```sql
SELECT COALESCE(SUM(amount_paise), 0) FROM ledger_entry WHERE merchant_id = ?;
```

Why this design:
- All money math is integer paise (no floating point drift).
- Balance is derived from an immutable event stream (audit-friendly).
- Queries and audits can fully replay and reason over history.

Event meaning:
- `CREDIT`: funds added to a merchant.
- `HOLD`: a negative reservation created when a payout is opened (stored as `-amount_paise`).
- `RELEASE`: a positive compensating entry written when a payout fails (stored as `+amount_paise`).

## 2) Locking and transactional strategy

All money-moving code runs under `transaction.atomic()` and uses `select_for_update()` to obtain row-level locks where necessary.

Payout creation path (what actually happens):
1. The `IdempotencyMiddleware` resolves or creates an `IdempotencyKey` under a DB transaction (see `payouts.services.get_or_lock_idempotency_key`).
2. The view calls `create_payout_with_hold(...)` with the locked `IdempotencyKey`.
3. Inside `create_payout_with_hold` the merchant row is locked with `Merchant.objects.select_for_update()`.
4. The code computes the current balance with `get_merchant_balance_paise(merchant.id)` and compares against the requested amount.
5. If sufficient, a `Payout` row is created (status `pending`, `idempotency_key` is a `OneToOneField` linking that key to the payout) and a `HOLD` `LedgerEntry` is written atomically with `amount_paise = -amount` and `reference_id = f"payout:{payout.id}"`.

Result: concurrent create requests cannot both consume the same funds because of the merchant row lock and the idempotency key protection.

## 3) Idempotency handling (middleware + model)

Where it lives:
- Model: `IdempotencyKey` (fields: `merchant`, `key`, `response_body` JSONField, `created_at`, `expires_at`). There is a unique constraint on `(merchant, key)`.
- Middleware: `IdempotencyMiddleware` inspects the `Idempotency-Key` header for `POST /api/v1/payouts`.

Behavior:
- The middleware extracts `merchant_id` from the JSON body and calls `get_or_lock_idempotency_key(merchant_id, key)` inside a transaction.
- `get_or_lock_idempotency_key` uses `select_for_update()` when the key already exists; if it does not exist it attempts to `create()` it and falls back to a `select_for_update()` get() if an `IntegrityError` race occurs.
- If acquiring the key fails due to DB contention (an `OperationalError`), the middleware returns HTTP 409 with `"Request is already being processed. Please retry."`.
- If the `IdempotencyKey` already contains a `response_body`, the middleware immediately returns that saved response (HTTP 200), enabling safe client retries.
- Otherwise the request proceeds with `request.idempotency_key` set; after the view returns the middleware stores the JSON response into `idempotency.response_body` (first successful response wins).

Operational notes:
- The `IdempotencyKey` includes `expires_at` (created with a 24-hour default). In production you should periodically remove expired keys.

## 4) State machine and transitions

Transitions are enforced centrally in `payouts.services`:

- Allowed transitions:
   - `pending -> processing`
   - `processing -> completed`
   - `processing -> failed`

- `transition_payout_status(payout, target)` validates the transition against the `ALLOWED_TRANSITIONS` map and raises `PayoutError` on invalid moves.
- `fail_and_release_payout(payout)` requires the payout to be in `processing`, sets the status to `failed`, and writes a compensating `RELEASE` ledger entry (`amount_paise = +payout.amount_paise`, `reference_id = payout:{id}`) in the same transaction.

This enforces lifecycle correctness and guarantees held funds are returned exactly once for terminal failures.

## 5) Worker processing and retries

Worker tasks are implemented with Celery (`payouts.tasks`):

- `process_pending_payouts_task`: finds `PENDING` payouts and enqueues `process_single_payout_task` for each.
- `process_single_payout_task` locks the payout row (`select_for_update()`), skips if already terminal, transitions `pending -> processing` if needed, sets `locked_at` and increments `attempts`.
- The example worker uses a randomized outcome for demo purposes:
   - 70% path: mark `COMPLETED`.
   - 20% path: call `fail_and_release_payout` (status `FAILED` + `RELEASE` entry).
   - 10% path: raise a retry; Celery retries with an exponential backoff.
- `retry_stuck_processing_payouts_task` looks for `PROCESSING` payouts with `locked_at` older than `PROCESSING_STALE_SECONDS` (30s) and either fails-and-releases if `attempts >= MAX_ATTEMPTS` (3), or requeues `process_single_payout_task` with exponential backoff.

This design ensures only one worker mutates a payout at a time and that stuck/failed workers eventually lead to retries or deterministic failure with fund release.

## 6) API contract and responses

- Endpoint: `POST /api/v1/payouts` (requires `Idempotency-Key` header).
- Successful create returns HTTP `201` with body: `{ "payout_id": <id>, "merchant_id": <id>, "amount_paise": <int>, "status": "pending" }`.
- Insufficient funds returns HTTP `400` with a `detail` message.
- Middleware may return HTTP `200` with a cached response for repeated idempotent requests, or HTTP `409` when the idempotency key is locked by another inflight request.

## 7) Audit example (aligned to implementation)

For payout `payout:P987` amount `50000` paise the invariants are:

1. On create: exactly one `HOLD` with `reference_id = 'payout:987'` and `amount_paise = -50000`.
2. If payout completed: there is no `RELEASE` for that `reference_id`.
3. If payout failed: there is exactly one `RELEASE` with `amount_paise = +50000` and the same `reference_id`.
4. The net ledger effect for that reference is either `-50000` (completed) or `0` (failed then released).

Illustrative SQL checks:

```sql
SELECT COUNT(*) FROM ledger_entry WHERE reference_id = 'payout:987' AND type = 'HOLD' AND amount_paise = -50000;
SELECT COUNT(*) FROM ledger_entry WHERE reference_id = 'payout:987' AND type = 'RELEASE' AND amount_paise = 50000;
SELECT COALESCE(SUM(amount_paise),0) FROM ledger_entry WHERE reference_id = 'payout:987';
```

If these checks fail, flag the payout for manual review.

---

If you want, I can (a) run the test suite that exercises these flows, or (b) add a short sequence diagram showing the request/middleware/create/worker flow.
