@echo off
title Facebook Zenith Cleaner - Setup
cd /d "%~dp0"
echo ============================================================
echo   FACEBOOK ZENITH CLEANER - ONE-TIME SETUP
echo ============================================================
echo.
echo [1/3] Installing Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :fail
echo.
echo [2/3] Installing the bundled Chromium browser...
python -m playwright install chromium || goto :fail
echo.
echo [3/3] Building the icon and desktop shortcut...
python create_icon.py
python create_desktop_shortcut.py
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
