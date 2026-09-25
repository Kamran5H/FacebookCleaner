@echo off
setlocal
title Facebook Zenith Cleaner - Debug Runner
cd /d "%~dp0"
echo ============================================================
echo   FACEBOOK ZENITH CLEANER - DEBUG RUNNER (console visible)
echo ============================================================
echo.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" backend\app.py --open
echo.
echo Server stopped.
pause
