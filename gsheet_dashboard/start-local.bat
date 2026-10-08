@echo off
setlocal
cd /d "%~dp0"
if not exist "..\.venv\Scripts\python.exe" (
    echo Run run.bat once to install the local application dependencies.
    pause
    exit /b 1
)
set "DATATRACE_DESKTOP="
set "DATATRACE_DESKTOP_TOKEN="
"..\.venv\Scripts\python.exe" server.py --host 127.0.0.1 --port 8510
if errorlevel 1 pause
