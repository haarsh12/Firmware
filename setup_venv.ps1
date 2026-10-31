# Creates an isolated Python environment and installs the backend dependencies.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 or later is required but 'python' was not found on PATH."
}

python -m venv venv
& .\venv\Scripts\python.exe -m pip install --upgrade pip
& .\venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example. Check the credential-file path before starting." -ForegroundColor Yellow
}

Write-Host "Virtual environment is ready. Start with: .\start.ps1" -ForegroundColor Green
