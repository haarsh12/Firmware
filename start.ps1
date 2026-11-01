$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .\venv\Scripts\python.exe)) {
    throw "Virtual environment not found. Run .\setup_venv.ps1 first."
}
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env. Confirm GOOGLE_APPLICATION_CREDENTIALS before using voice services." -ForegroundColor Yellow
}

# Use one stable process for ESP32 and Xiaozhi hardware sessions. The reload
# supervisor creates extra child processes and is unsuitable for this runtime.
& .\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
