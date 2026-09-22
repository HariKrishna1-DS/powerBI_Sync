@echo off
setlocal
cd /d "%~dp0"
title DataTrace Workspace
if not exist "..\.venv\Scripts\python.exe" (
    python -m venv ..\.venv
    if errorlevel 1 exit /b 1
)
set "PYTHON_EXE=..\.venv\Scripts\python.exe"
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
call npm.cmd install
if errorlevel 1 exit /b 1
call npm.cmd --prefix frontend install
if errorlevel 1 exit /b 1
call npm.cmd --prefix frontend run build
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" server.py
if errorlevel 1 pause
