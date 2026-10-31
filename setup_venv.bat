@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.11 or later is required but was not found on PATH.
  exit /b 1
)

python -m venv venv
call venv\Scripts\python.exe -m pip install --upgrade pip
call venv\Scripts\python.exe -m pip install -r requirements.txt

if not exist .env (
  copy .env.example .env >nul
  echo Created .env from .env.example. Check the credential-file path before starting.
)

echo Virtual environment is ready. Start with start.bat
