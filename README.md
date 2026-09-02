# Revive — AI Revenue Recovery Agent (CodeBuild MVP)

A hackathon-ready prototype for detecting revenue at risk, predicting recovery probability, choosing bounded recovery actions, and tracking recovered revenue.

## MVP scope
- Failed payments
- Abandoned checkouts
- Overdue invoices
- Recovery probability model (synthetic training data)
- Bounded decision engine
- Simulated actions: retry payment, generate payment link, send recovery message, escalate
- Revenue-at-risk and recovered dashboards
- Event simulator for a strong live demo

## Run

### 1) Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python seed.py
uvicorn main:app --reload --port 8000
```

### 2) Frontend
Open `frontend/index.html` directly, or serve the folder with a local server:
```bash
cd frontend
python -m http.server 5500
```
Then open http://localhost:5500

The frontend expects the backend at http://localhost:8000.

## Production integrations to add later
- Razorpay webhook verification + live API integration
- WhatsApp Business API
- Email provider
- Merchant auth/onboarding
- Stripe/Shopify/WooCommerce connectors
- Experimentation / incremental lift measurement
- Production security, observability, and compliance
