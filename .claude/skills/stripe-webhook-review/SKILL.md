---
name: stripe-webhook-review
description: Audit any Stripe webhook handler for signature verification, idempotency, and entitlement update correctness. Run before merging any Stripe code.
---

## When to use
Before any Stripe webhook handler change is merged.

## Checklist
1. Find the webhook handler endpoint.
2. Verify `Stripe-Signature` header is read and passed to `stripe.Webhook.construct_event()` before any processing.
3. Verify `STRIPE_WEBHOOK_SECRET` (not `STRIPE_SECRET_KEY`) is used for signature verification.
4. Verify all event processing is wrapped in `try/except` — malformed events must return 400, not crash.
5. Verify idempotency: check for existing `stripe_event_id` in Supabase before processing.
6. Verify the handler returns `200` immediately after verifying signature and queuing work — do not do heavy work inline.
7. Verify entitlements table is updated via the service role key, not the anon key.
8. Verify no sensitive data (card numbers, secret keys) is logged.

## Rule
Do not modify code. Report findings only. Do not create new markdown files.

## Required output format
```
## Stripe Webhook Review: <route or file>

### Findings
- [CRITICAL|HIGH|MEDIUM|OK] <file:line> — <finding>

### Checklist
- [x/o] Stripe-Signature verified before processing
- [x/o] STRIPE_WEBHOOK_SECRET used (not STRIPE_SECRET_KEY)
- [x/o] Idempotency check on stripe_event_id
- [x/o] Returns 200 quickly; heavy work deferred
- [x/o] No secrets logged

### Verdict: PASS | FAIL
```
