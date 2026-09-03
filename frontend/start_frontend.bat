@echo off
cd /d "%~dp0"
set "REVIVE_TOOLS=%~dp0..\..\.tools"
if exist "%REVIVE_TOOLS%\node-v22.18.0-win-x64\npm.cmd" set "PATH=%REVIVE_TOOLS%\node-v22.18.0-win-x64;%PATH%"
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
