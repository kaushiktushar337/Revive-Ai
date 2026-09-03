@echo off
cd /d "%~dp0backend"
set "REVIVE_TOOLS=%~dp0..\.tools"
if exist "%REVIVE_TOOLS%\Python312\python.exe" (
  "%REVIVE_TOOLS%\Python312\python.exe" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
  pause
  exit /b %errorlevel%
)
if not exist ".venv\Scripts\python.exe" (
  echo Python 3.12 environment not found.
  echo Use the local ReviveAI tools setup or create .venv\Scripts\python.exe.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
pause
