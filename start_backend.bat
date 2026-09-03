@echo off
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo Python 3.12 virtual environment not found.
  echo Create it with: py -3.12 -m venv .venv
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
pause
