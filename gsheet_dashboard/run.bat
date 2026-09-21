@echo off
setlocal enabledelayedexpansion
title Google Sheets Live-Sync Dashboard

echo =========================================================
echo    Google Sheets Live-Sync Streamlit Dashboard Launcher
echo =========================================================
echo.

:: Detect Python Virtual Environment in workspace root or local folder
if exist "..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\.venv\Scripts\python.exe"
    set "STREAMLIT_EXE=..\.venv\Scripts\streamlit.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    set "STREAMLIT_EXE=.venv\Scripts\streamlit.exe"
) else (
    echo [INFO] Virtual environment not found. Setting up .venv...
    python -m venv ..\.venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Ensure Python is installed and in PATH.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=..\.venv\Scripts\python.exe"
    set "STREAMLIT_EXE=..\.venv\Scripts\streamlit.exe"
    echo [INFO] Installing required packages...
    "!PYTHON_EXE!" -m pip install --upgrade pip
    "!PYTHON_EXE!" -m pip install -r requirements.txt
)

:: Verify Streamlit executable
if not exist "!STREAMLIT_EXE!" (
    echo [INFO] Installing dependencies from requirements.txt...
    "!PYTHON_EXE!" -m pip install -r requirements.txt
)

echo.
echo [OK] Launching Streamlit Live-Sync Dashboard...
echo [INFO] The dashboard will open in your default browser automatically.
echo [INFO] Press Ctrl+C in this terminal window to stop the server.
echo.

"!STREAMLIT_EXE!" run app.py --server.port=8501

if errorlevel 1 (
    echo.
    echo [ERROR] Streamlit exited with an error.
    pause
)
