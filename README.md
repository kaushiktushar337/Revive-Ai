# Revive — AI Revenue Recovery Agent

Revive is a startup-oriented prototype that detects revenue at risk, predicts recovery probability, chooses bounded interventions, executes safe demo actions, and records the outcome.

## Current implementation

- Failed payments, abandoned checkouts, and overdue invoices
- Synthetic ML recovery-probability model
- Bounded decision engine with human-approval and contact-frequency limits
- Revenue-at-risk / expected-recovery dashboard
- Audit trail
- Razorpay webhook ingestion endpoint with signature verification support
- Razorpay event deduplication
- Razorpay payment reconciliation (`payment.failed` → later `payment.captured`)
- Read-only Razorpay credential connection test
- Razorpay payment-link adapter (demo mode by default)
- Checkout event ingestion + abandonment scanner
- Overdue-invoice CSV importer
- Idempotency via external event IDs
- Recovery confirmation endpoint for demos
- Automated decision-engine and Razorpay integration tests

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
python -m http.server 5500
```

Open http://localhost:5500.

The frontend expects the backend at http://localhost:8000.

## Razorpay test mode

Copy `backend/.env.example` to `backend/.env` and provide Razorpay test credentials. Keep `MOCK_EXTERNAL_ACTIONS=true` while developing the UI. Set it to `false` only after the read-only connection test succeeds and you are ready to create test Payment Links.

The frontend now includes **Test Razorpay connection**, which calls:

`GET /api/integrations/razorpay/test`

Webhook endpoint:

`POST /api/webhooks/razorpay`

In production, configure `RAZORPAY_WEBHOOK_SECRET`. The webhook endpoint rejects invalid signatures once that secret is configured.

### Local webhook test without Razorpay

Run the API locally, set `RAZORPAY_WEBHOOK_SECRET=dev_secret`, then:

```bash
python backend/sample_webhook.py --secret dev_secret --event payment.failed --payment-id pay_demo_001
```

The script sends a signed Razorpay-style event. Send it again to verify webhook deduplication. Then send a captured event with the same payment ID:

```bash
python backend/sample_webhook.py --secret dev_secret --event payment.captured --payment-id pay_demo_001
```

Revive should reconcile the original failed-payment record as recovered.

## CSV invoice format

Required columns:

```csv
customer,amount,due_date,invoice_id,currency,previous_success_rate,customer_value,prior_contacts,days_since_last_success
ABC Pvt Ltd,75000,2026-08-15,INV-1001,INR,0.80,300000,1,12
```

A ready-to-use example is included at `backend/sample_invoices.csv`.

Upload to `POST /api/invoices/import`.

## Next build phases

1. Real Razorpay test payment → webhook → recovery workflow demo
2. Outbound email connector with consent, templates and rate limits
3. WhatsApp connector after business messaging setup
4. Merchant authentication and multi-tenant data isolation
5. Merchant-specific recovery models and A/B experimentation
6. Incremental-lift measurement rather than raw recovered revenue
7. Stripe / Shopify / WooCommerce integrations
8. Production security, observability, compliance and billing
