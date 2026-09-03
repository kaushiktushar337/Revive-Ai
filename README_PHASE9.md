# ReviveAI Phase 9 — Connector & UX Hardening

This build keeps the React + JavaScript + Tailwind frontend and the existing FastAPI backend, while fixing interaction and connector reliability issues.

## Main fixes
- Payment gateway selector works for PayU and Razorpay and persists the active gateway.
- Existing gateway secrets are preserved when settings are reloaded and saved with blank secret fields.
- Payment-link sync uses the gateway recorded on the recovery event, so switching gateways does not break historical recovery actions.
- Recovery action buttons are state-aware and disappear from the active-leak table after execution.
- Recovery email preview and send are available from the Recovery view, with explicit consent confirmation.
- Checkout tracker now has working Start, Complete, and Scan Abandonment actions.
- Invoice CSV import is wired with file validation and refresh.
- Account popover shows merchant and active gateway details.
- Audit logs remain embedded in Overview with a refresh control; no separate Audit tab.
- API errors show actionable toast messages.
- Backend preserves SMTP password when an update intentionally leaves it blank.

## Frontend
- React 18 + JSX
- Tailwind CSS 3
- Vite 5
- No TypeScript files

## Run on Windows
Backend:
```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

Frontend:
```powershell
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite, usually `http://127.0.0.1:5173/`.

## Verification
Backend test suite: 16 passed.
FastAPI smoke test: `/api/health` returned HTTP 200.

The environment used for packaging did not have the Vite dependency cache, so a local `npm install` was not completed here. On Windows, Node 20–22 is recommended for this Vite configuration.


## Customer history + database update
The current build supports customer histories and an optional hosted PostgreSQL database. Set DATABASE_URL to a PostgreSQL connection string for deployed persistence; when DATABASE_URL is absent, the app falls back to local SQLite. Customer records and bills are stored separately from the derived recovery events. Use POST /api/customers/history for manual history entry, POST /api/customers/demo for demo history generation, and POST /api/customers/scan to derive new overdue revenue-risk events from the histories.

## Phase 10: customer history + hosted database
- The **Simulate customer history** control now creates full customer ledgers (multiple bills with due dates, paid dates, and unpaid balances) instead of directly creating fake leak events.
- Merchants can add customer histories manually from **Customers → Add customer**.
- **Customers → Scan for leaks** derives current invoice-overdue revenue-risk events from the stored ledger.
- The legacy `/api/simulate-leaks` route is retained as a backward-compatible demo trigger but now generates customer histories and scans them.
- Invoice CSV import now writes bills into customer histories before scanning for overdue opportunities.
- Added `users`, `customers`, and `customer_bills` tables. Each merchant owns its users/customers/bills.
- The database layer supports local SQLite by default and PostgreSQL/Supabase when `DATABASE_URL` is set. The SQL used for the core schema and event upserts is compatible with both modes.
- For Render, pin Python with `backend/.python-version` or `PYTHON_VERSION=3.12.7` and set `DATABASE_URL` to the hosted PostgreSQL connection string for persistence.
