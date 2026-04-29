# 💳 Playto Payout Engine (Cursor-Driven Implementation Guide)

This README is structured as a **step-by-step execution plan** to build the Playto Payout Engine using Cursor.

⚠️ Goal: Guide AI to generate **correct, production-grade fintech code**, not just working code.

---

# 🧠 Core Rule (Read Before Starting)

- NEVER compute balances in Python
- ALWAYS use DB transactions for money movement
- USE row-level locking (`select_for_update`)
- Ledger must be **immutable**
- Every operation must be **idempotent-safe**

---

# 🚀 STEP 0: Project Setup

### Prompt Cursor:

> Create a Django project with DRF, PostgreSQL config, and Celery setup using Redis.

### Expected:
- Django project (`config/`)
- Apps: `ledger`, `payouts`, `merchants`
- Celery configured
- PostgreSQL connection

---

# 🧱 STEP 1: Data Modeling (MOST IMPORTANT)

### Prompt Cursor:

> Create Django models for Merchant, LedgerEntry, Payout, and IdempotencyKey following fintech best practices.

### Requirements:

## Merchant
- id
- name

## LedgerEntry
- merchant (FK)
- amount_paise (BigIntegerField)
- type (CREDIT, HOLD, RELEASE)
- reference_id
- created_at

⚠️ Immutable (no updates allowed)

## Payout
- merchant (FK)
- amount_paise
- status (pending, processing, completed, failed)
- idempotency_key
- attempts
- locked_at

## IdempotencyKey
- key
- merchant
- response_body
- created_at
- expires_at

---

# 💰 STEP 2: Ledger Logic

### Prompt Cursor:

> Implement a service to compute merchant balance using database aggregation only.

### Must Generate:

```sql
SELECT COALESCE(SUM(amount_paise), 0)
FROM ledger_entry
WHERE merchant_id = ?;
```

⚠️ Reject any Python-based sum

---

# 🔒 STEP 3: Concurrency-Safe Payout API

### Prompt Cursor:

> Implement POST /api/v1/payouts with transaction.atomic and select_for_update locking.

### Logic:

1. Lock merchant row
2. Compute balance (DB)
3. If insufficient → reject
4. Create payout (pending)
5. Create HOLD ledger entry

⚠️ Entire flow must be inside a transaction

---

# 🔁 STEP 4: Idempotency Layer

### Prompt Cursor:

> Implement idempotency middleware using Idempotency-Key header.

### Logic:

- Check if key exists for merchant
- If yes → return stored response
- If no → process request
- Store response

### Edge Case:

> Use select_for_update on idempotency key to prevent race condition

---

# 🔄 STEP 5: State Machine Enforcement

### Prompt Cursor:

> Implement payout state transitions with strict validation.

### Rules:

- pending → processing → completed
- pending → processing → failed

Reject everything else

---

# ⚙️ STEP 6: Background Worker (Celery)

### Prompt Cursor:

> Implement Celery task to process payouts asynchronously.

### Logic:

- Pick pending payouts
- Move to processing
- Simulate:
  - 70% success
  - 20% failure
  - 10% delay

---

# 💥 STEP 7: Failure Handling (CRITICAL)

### Prompt Cursor:

> On payout failure, return funds atomically.

### Must:

- Change status → failed
- Create RELEASE ledger entry (+amount)
- Wrap in transaction.atomic

---

# 🔁 STEP 8: Retry Logic

### Prompt Cursor:

> Implement retry logic for stuck payouts (>30s in processing).

### Requirements:

- Exponential backoff
- Max 3 attempts
- Then mark failed

---

# 🧪 STEP 9: Tests (MANDATORY)

### Prompt Cursor:

> Write tests for concurrency and idempotency.

## Concurrency Test
- Simulate 2 parallel payout requests
- Assert only one succeeds

## Idempotency Test
- Same key twice
- Same response
- No duplicate payout

---

# 🖥️ STEP 10: Frontend (Minimal)

### Prompt Cursor:

> Create React dashboard with Tailwind showing balance, payouts, and request form.

Keep it simple:
- Balance display
- Payout form
- History table

---

# 📦 STEP 11: Seed Data

### Prompt Cursor:

> Create Django command to seed 2–3 merchants with ledger credits.

---

# 🌐 STEP 12: Deployment

### Prompt Cursor:

> Add docker-compose and deployment config for Render or Railway.

---

# 📄 STEP 13: EXPLAINER.md (DO NOT SKIP)

### Prompt Cursor:

> Generate EXPLAINER.md answering:

1. Ledger query + reasoning
2. Locking strategy
3. Idempotency handling
4. State machine enforcement
5. AI audit example

⚠️ You MUST manually refine this

---

# 🧭 Execution Strategy

Do NOT generate everything at once.

Follow this order strictly:

1. Models
2. Ledger logic
3. Payout API (locking)
4. Idempotency
5. Worker
6. Tests
7. UI
8. Explainer

---

# ⚠️ Common AI Mistakes (REJECT THESE)

- ❌ Using FloatField
- ❌ Calculating balance in Python
- ❌ Missing transaction.atomic
- ❌ No select_for_update
- ❌ Updating ledger rows

---

# 🏁 Final Goal

A system where:

- Money is never duplicated or lost
- Concurrency is handled correctly
- APIs are idempotent
- Failures are recoverable

---

This README is designed to guide Cursor to generate a **production-grade fintech system**, not a demo project.

