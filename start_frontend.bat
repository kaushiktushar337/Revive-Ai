@echo off
cd /d "%~dp0frontend"
where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js/npm is not installed or not on PATH.
  echo Install Node.js LTS, reopen this window, then run again.
  pause
  exit /b 1
)
if not exist "node_modules" (
  echo Installing frontend dependencies...
  call npm install
  if errorlevel 1 exit /b 1
)
call npm run dev
pause
