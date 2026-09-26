@echo off
setlocal
title Facebook Zenith Cleaner - Setup
cd /d "%~dp0"
echo ============================================================
echo   FACEBOOK ZENITH CLEANER - ONE-TIME SETUP
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python 3.10+ from python.org
    echo         and tick "Add python.exe to PATH" during install.
    goto :fail
)

echo [1/4] Creating a private virtual environment in .venv ...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || goto :fail
)
set "PY=.venv\Scripts\python.exe"

echo.
echo [2/4] Installing Python packages...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt || goto :fail

echo.
echo [3/4] Installing the bundled Chromium browser...
"%PY%" -m playwright install chromium || goto :fail

echo.
echo [4/4] Building the icon and desktop shortcut...
"%PY%" create_icon.py
"%PY%" create_desktop_shortcut.py

echo.
echo ============================================================
echo   SETUP COMPLETE - launch from the desktop shortcut.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup failed. Check the messages above.
pause
exit /b 1
