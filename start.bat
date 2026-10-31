@echo off
setlocal
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
  echo Virtual environment not found. Run setup_venv.bat first.
  exit /b 1
)
if not exist .env (
  copy .env.example .env >nul
  echo Created .env. Confirm GOOGLE_APPLICATION_CREDENTIALS before using voice services.
)

venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
