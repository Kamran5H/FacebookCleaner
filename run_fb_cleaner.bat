@echo off
title Facebook Zenith Cleaner - Debug Runner
cd /d "%~dp0"
echo ============================================================
echo   FACEBOOK ZENITH CLEANER - DEBUG RUNNER (console visible)
echo ============================================================
echo.
python backend\app.py --open
echo.
echo Server stopped.
pause
