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

## Phase 4 — Outbound email recovery

- Recovery email preview endpoint with customer-specific content
- Email consent check before sending
- Per-event contact limit (maximum 3 emails)
- Mock email delivery by default for safe local demos
- SMTP delivery support via environment variables for real testing
- Email action audit logging and lifecycle update to `AWAITING_OUTCOME`

Email endpoints:

- `GET /api/events/{event_id}/email-preview`
- `POST /api/recovery/email`

Set `MOCK_EMAIL_ACTIONS=false` and configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM` only when you are ready to send real messages.

## Next build phases

1. Real Razorpay test payment → webhook → recovery workflow demo
2. Outbound email connector with consent, templates and rate limits
3. WhatsApp connector after business messaging setup
4. Merchant authentication and multi-tenant data isolation
5. Merchant-specific recovery models and A/B experimentation
6. Incremental-lift measurement rather than raw recovered revenue
7. Stripe / Shopify / WooCommerce integrations
8. Production security, observability, compliance and billing

## Phase 3 — Recovery execution lifecycle

- Recovery actions now follow a lifecycle: `DETECTED → RECOMMENDED → AWAITING_OUTCOME → RECOVERED` (or `ESCALATION_REQUIRED`, `LINK_EXPIRED`, `LINK_CANCELLED`, `NO_ACTION`).
- Demo and real Razorpay Payment Links return/store the link ID, URL and reference ID.
- `payment_link.paid`, `payment_link.partially_paid`, `payment_link.expired`, and `payment_link.cancelled` webhooks can reconcile a Revive-generated recovery link.
- Recovered amount, recovery timestamp and outcome source are persisted for dashboard/reporting use.
- The dashboard exposes the recovery link, lifecycle state and recovered amount where available.

Razorpay's current Payment Links webhook documentation lists `payment_link.paid`, `payment_link.partially_paid`, `payment_link.cancelled` and `payment_link.expired` events; the Phase 3 webhook handler uses those states for recovery reconciliation. citeturn456888view0

## Phase 5 — Merchant accounts + recovery sender mailbox

Revive now supports merchant accounts and keeps dashboard/recovery data isolated by merchant.

### Create a merchant ID

Open the frontend and choose **Create merchant ID**. The onboarding form asks for:

- Business name
- Login email + password
- **Recovery sender email** — the mailbox customers will see as the sender of recovery emails
- Email mode: demo or real SMTP

Demo mode is recommended while building the prototype. In real SMTP mode, authenticated SMTP credentials are required in addition to the sender email.

### Default demo account

```text
Login email: demo@revive.local
Password:    demo12345
Sender:      demo@revive.local
```

### Sender settings

After login, open **Merchant Settings** to change the recovery sender mailbox. The settings page supports SMTP host, port, username and password/app-password for real delivery.

For a real mailbox, the From address must be permitted by the SMTP provider. The sender email alone does not grant permission to send mail.

### Authentication

Protected merchant endpoints use a short-lived signed bearer token. Event, invoice, checkout, dashboard, audit and recovery-email data is scoped to the authenticated merchant.

Razorpay webhooks remain public endpoints for provider callbacks. During local testing, the webhook may be attributed to the demo merchant or to a merchant supplied through `X-Revive-Merchant-Id`; production deployments should replace this with a per-merchant webhook credential/secret mapping.

## Phase 5.1 — Verified recovery sender mailbox

Merchant Settings now includes a **Send test email** action. Enter a recipient address and Revive sends a diagnostic message using the merchant's configured recovery sender.

- Demo mode: safe mocked delivery; no external mailbox is contacted.
- SMTP mode: validates that host, username and password/app password are present before sending.
- The API returns the configured sender and delivery mode, but never returns the stored SMTP password.
- Test sends are written to the merchant audit trail.

Endpoint:

`POST /api/auth/email-test`

Payload:

```json
{"recipient":"you@example.com"}
```

The merchant onboarding form already asks for the **Recovery sender email**. For real SMTP delivery, configure the sender mailbox's authenticated SMTP credentials in the merchant settings.

## Windows quick start

Use Python 3.12 for this prototype. From the `revive_phase4_work` folder:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
backend\.venv\Scripts\python.exe -m uvicorn --app-dir backend main:app --reload --port 8000
```

The backend includes the `python-multipart` dependency required by the invoice upload endpoint.

Frontend:

```powershell
python -m http.server 5500 --directory frontend
```

Open `http://127.0.0.1:5500`.


## Real Razorpay Test Mode
1. In Razorpay Dashboard switch to Test Mode and generate a Test API Key ID/Secret. Razorpay provides separate Test and Live keys; Test Mode does not move real money.
2. In Revive Settings → Razorpay payment gateway, choose Test Mode, paste Key ID, Key Secret, and create/configure a webhook secret.
3. Save, then click Test API connection.
4. Copy the merchant-specific webhook endpoint shown by Revive into Razorpay Dashboard → Account & Settings → Webhooks and subscribe to the payment/payment-link events used by the app.
5. For localhost webhooks, expose the local server through a secure tunnel or use a staging HTTPS endpoint. Razorpay documents testing webhooks with localhost/staging and emphasizes signature verification/idempotency.
6. Create a real Test Mode Payment Link from a Revive recovery action. Razorpay Payment Links are API-created URLs that can be paid with supported test payment methods.
7. After payment, use the event's “Sync payment status” control if the webhook cannot reach localhost; otherwise the webhook should reconcile automatically.
8. Never put Live credentials in a demo environment. Keep secrets out of source control.

## Frontend update
The frontend has been replaced with the Deep Intelligence / Stitch modern UI reference design. It keeps the full prototype functionality: merchant auth, overview metrics, risk, recovery actions, Razorpay connector, invoice CSV import, checkout scanner simulation, email sender settings/test, payment-link sync, and audit logs embedded in Overview (no separate Audit tab).

Run frontend with:
`python -m http.server 5500 --directory frontend`

## PayU Test Mode

Revive uses PayU as the primary payment gateway for recovery Payment Links. The integration uses PayU's OAuth 2.0 Client Credentials flow and the Test/UAT Payment Links API.

Configure these merchant fields in **Settings → PayU payment gateway**:
- Merchant ID
- Client ID
- Client Secret
- Test/Product Key (optional for hosted checkout)
- Salt (used for response-hash verification)

PayU's documented Test/UAT Payment Links endpoint is `https://uatoneapi.payu.in/payment-links`, and access tokens are obtained from `https://uat-accounts.payu.in/oauth/token` with the appropriate payment-link scopes.

PayU payment webhooks should be configured at:
`<PUBLIC_BASE_URL>/api/webhooks/payu/<merchant_id>`

The webhook handler validates the PayU response hash before accepting a successful payment.

For a real sandbox payment, use PayU's Test credentials/cards/UPI values documented in their Test Integration guide. UPI intent/in-app flows are not available in Test Mode.
