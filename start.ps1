$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .\venv\Scripts\python.exe)) {
    throw "Virtual environment not found. Run .\setup_venv.ps1 first."
}
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env. Confirm GOOGLE_APPLICATION_CREDENTIALS before using voice services." -ForegroundColor Yellow
}

& .\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
