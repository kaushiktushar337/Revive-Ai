# Revive — AI Revenue Recovery Agent

Revive is a startup-oriented prototype that detects revenue at risk, predicts recovery probability, chooses bounded interventions, executes safe demo actions, and records the outcome.

## Current implementation

- Failed payments, abandoned checkouts, and overdue invoices
- Synthetic ML recovery-probability model
- Bounded decision engine with human-approval and contact-frequency limits
- Revenue-at-risk / expected-recovery dashboard
- Audit trail
- Razorpay webhook ingestion endpoint with signature verification support
- Razorpay payment-link adapter (demo mode by default)
- Checkout event ingestion + abandonment scanner
- Overdue-invoice CSV importer
- Idempotency via external event IDs
- Recovery confirmation endpoint for demos
- Automated decision-engine tests

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python seed.py
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

Copy `backend/.env.example` to `backend/.env` and provide test credentials. Keep `MOCK_EXTERNAL_ACTIONS=true` while developing the UI; set it to `false` only when you have verified your test account and credentials.

Webhook endpoint:

`POST /api/webhooks/razorpay`

In production, configure `RAZORPAY_WEBHOOK_SECRET`. The webhook endpoint rejects invalid signatures once that secret is configured.

## CSV invoice format

Required columns:

```csv
customer,amount,due_date,invoice_id,currency,previous_success_rate,customer_value,prior_contacts,days_since_last_success
ABC Pvt Ltd,75000,2026-08-20,INV-1001,INR,0.80,300000,1,12
```

Upload to `POST /api/invoices/import`.

## Next build phases

1. Real Razorpay event normalization and payment-state reconciliation
2. WhatsApp/email connectors with consent and rate limits
3. Merchant authentication and multi-tenant data isolation
4. Merchant-specific recovery models and A/B experimentation
5. Incremental-lift measurement rather than raw recovered revenue
6. Stripe / Shopify / WooCommerce integrations
7. Production security, observability, compliance and billing
