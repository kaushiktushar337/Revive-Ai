# Revive AI

Revive AI is a revenue-recovery dashboard for businesses that want to find missed payments and act on them before they become lost revenue.

The app takes the payment and customer data already available to a business, turns it into recovery opportunities, and gives the team a simple workflow to execute those opportunities. That includes creating a PayU payment link, checking its status, and preparing a recovery email that can be edited before it is sent.

## What the app does

- Tracks customers, invoices, payments, and recovery opportunities.
- Uses customer payment history to calculate recovery probability and risk.
- Surfaces the highest-priority revenue leaks in the dashboard.
- Lets you create **PayU payment links in test mode** directly from an existing recovery event. The customer name, email, amount, and reference data are taken from the event instead of being entered again.
- Lets you open or copy the payment link as soon as it is created.
- Generates a recovery email preview and lets you edit the recipient, subject, and body before sending.
- Sends transactional email through **Brevo** using one server-side sender configuration.
- Receives and syncs payment status through gateway APIs/webhooks.
- Includes demo/simulation tools for trying the workflow without real payments.
- Stores data in SQLite locally and can use PostgreSQL/Supabase when `DATABASE_URL` is configured.

## Tech stack

**Frontend**
- React 18
- Vite 5
- Tailwind CSS 3
- JavaScript/JSX

**Backend**
- FastAPI
- Python
- scikit-learn / joblib for the recovery model
- SQLite locally or PostgreSQL in a hosted deployment

**Services**
- Vercel for the frontend
- Render for the FastAPI backend
- Supabase PostgreSQL for hosted database persistence
- PayU for payment-link creation and payment status
- Brevo for transactional recovery email

## Project structure

```text
.
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   ├── engine.py
│   ├── model.py
│   ├── payu_adapter.py
│   ├── razorpay_adapter.py
│   ├── email_adapter.py
│   ├── recovery_model.joblib
│   ├── seed.py
│   ├── seed_events.json
│   ├── sample_invoices.csv
│   ├── sample_webhook.py
│   ├── requirements.txt
│   └── tests...
├── frontend/
│   ├── src/
│   ├── public/
│   ├── index.html
│   ├── package.json
│   └── package-lock.json
├── start_backend.bat
├── start_frontend.bat
└── README.md
```

## Running locally

### 1. Backend

Use Python 3.12 for the current configuration.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API should be available at:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/api/health
```

### 2. Frontend

Use Node.js 20 or 22.

```powershell
cd frontend
npm install
npm run dev
```

Vite normally serves the app at:

```text
http://127.0.0.1:5173
```

The Vite configuration proxies `/api` requests to the local FastAPI server.

## Environment variables

### Backend

Copy `backend/.env.example` and set the values for your environment.

The important production settings are:

```env
REVIVE_ENV=production
CORS_ORIGINS=https://your-vercel-domain.vercel.app
REVIVE_AUTH_SECRET=replace-with-a-long-random-secret
DATABASE_URL=your-supabase-postgres-connection-string
PUBLIC_BASE_URL=https://your-render-service.onrender.com

MOCK_EXTERNAL_ACTIONS=false

EMAIL_PROVIDER=brevo
BREVO_API_KEY=your-brevo-api-key
EMAIL_FROM=no-reply@your-verified-domain.com
EMAIL_FROM_NAME=ReviveAI

PAYU_MODE=test
```

Do not commit `.env` files or any API keys to GitHub.

## PayU test mode

PayU credentials are stored server-side and are never put in the browser bundle.

Set these values in the Render environment for a test deployment:

```env
PAYU_MODE=test
```

The PayU integration also expects the merchant ID, client ID, and client secret to be configured in the application's payment settings. The UI hides saved secrets and only reveals the editing controls when you choose to edit the settings.

When a recovery event is executed, Revive AI uses the event's existing customer and payment data to create the PayU payment link. No separate payment-link form is required for the normal recovery flow.

## Brevo email

Revive AI uses one server-side Brevo configuration for hosted transactional email.

```env
EMAIL_PROVIDER=brevo
BREVO_API_KEY=your-brevo-api-key
EMAIL_FROM=no-reply@your-verified-domain.com
EMAIL_FROM_NAME=ReviveAI
```

Verify the sender (or the domain) in Brevo before enabling real email delivery.

The recovery email workflow is intentionally editable:

1. Open the recovery email preview.
2. Review the generated message.
3. Change the recipient, subject, or body if needed.
4. Confirm consent.
5. Send the final version.

## Database

The backend supports two storage modes:

- **SQLite** when `DATABASE_URL` is not set. This is useful for local demos.
- **PostgreSQL** when `DATABASE_URL` is set. In production, this can be a Supabase PostgreSQL connection string.

The deployed application should use PostgreSQL/Supabase so data survives Render restarts and redeployments.

## Useful API endpoints

A few of the main endpoints are:

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me

GET  /api/dashboard
GET  /api/customers
GET  /api/customers/{customer_id}/history
POST /api/customers/history
POST /api/customers/demo
POST /api/customers/scan

POST /api/events
POST /api/events/{event_id}/execute
POST /api/events/{event_id}/sync-payment-link
POST /api/events/{event_id}/confirm-recovered

GET  /api/events/{event_id}/email-preview
POST /api/recovery/email

GET  /api/integrations/payu/settings
PUT  /api/integrations/payu/settings
GET  /api/integrations/payu/test-merchant

POST /api/webhooks/payu/{merchant_id}
```

## Deployment

### Render

Set the backend root directory to `backend`.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set `PYTHON_VERSION=3.12.7` if Render does not pick the version from `backend/.python-version` automatically.

Also set:

- `DATABASE_URL` to the Supabase PostgreSQL connection string
- `CORS_ORIGINS` to the exact Vercel origin
- `PUBLIC_BASE_URL` to the Render service URL
- `REVIVE_AUTH_SECRET` to a strong random secret
- PayU and Brevo secrets as required

### Vercel

Set the project root directory to `frontend`.

Build command:

```text
npm run build
```

The output directory is:

```text
dist
```

Set:

```env
VITE_API_BASE_URL=https://your-render-service.onrender.com/api
```

## Testing

The backend includes tests for core flows such as authentication, payment-gateway integration, email delivery, customer history, and recovery execution.

Run the available test suite with:

```powershell
cd backend
pytest
```

For a quick frontend production check:

```powershell
cd frontend
npm install
npm run build
```

## Notes

Revive AI is currently configured around **PayU test mode** for payment-link creation. Switching to live payments should be treated as a separate production-readiness step: verify the live PayU credentials, webhook configuration, domain/email authentication, and all business rules before enabling it.

The UI is designed around a single branded Revive AI experience, including the landing page, animated background, logo-based loading state, reusable modals, and editable recovery-email workflow.

## License

No open-source license has been added yet. Add the license that matches how you plan to distribute the project before publishing the repository publicly.
