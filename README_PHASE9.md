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
