@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Universal Local File Searcher
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo and make sure "Add python.exe to PATH" is checked during install.
    pause
    exit /b 1
)

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing/updating dependencies...
pip install --upgrade pip >nul
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies. See messages above.
    pause
    exit /b 1
)

echo.
echo Starting Universal File Searcher at http://127.0.0.1:5000
echo (Leave this window open. Close it to stop the app.)
echo.

start "" http://127.0.0.1:5000
python app.py

pause
