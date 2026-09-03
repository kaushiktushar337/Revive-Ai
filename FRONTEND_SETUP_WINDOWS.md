# ReviveAI — Frontend verification

## One-time setup
1. Install Node.js 20 or 22 (64-bit).
2. Open PowerShell in `frontend`.
3. Run `npm install`.

## Development
Run:

```powershell
npm run dev
```

Then open `http://127.0.0.1:5500`.

## Production build check
Run:

```powershell
npm run build
```

A successful run creates `frontend/dist/`.

## Backend
The backend remains Python/FastAPI and is independent of the frontend build. Start it from the backend directory with:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

Verify `http://127.0.0.1:8000/api/health` before opening the frontend.
