@echo off
title DMS Upload Automation — Spyne

echo.
echo  ╔════════════════════════════════════════╗
echo  ║   DMS Upload Automation — Spyne        ║
echo  ╚════════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found. Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

echo  [1/3] Checking dependencies...
python -m pip install -q flask playwright 2>nul
if %errorlevel% neq 0 (
    echo  [INFO] Installing dependencies (first run only)...
    python -m pip install flask playwright
)

echo  [2/3] Installing Playwright browser (first run only)...
python -m playwright install chromium --quiet 2>nul

echo  [3/3] Starting server...
echo.
echo  UI will open in your browser automatically.
echo  Press Ctrl+C here to stop the server.
echo.

python "%~dp0server.py"
pause
