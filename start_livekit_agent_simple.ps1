# Simple LiveKit agent starter with .env loading
Write-Host "=== Starting LiveKit Voice Agent ===" -ForegroundColor Cyan

# Check if livekit_venv exists
if (-not (Test-Path '.\livekit_venv\Scripts\python.exe')) {
    Write-Host "ERROR: LiveKit environment not found!" -ForegroundColor Red
    Write-Host "Run this first: .\scripts\setup_livekit_agent.ps1" -ForegroundColor Yellow
    exit 1
}

# Load .env file
if (Test-Path '.\.env') {
    Write-Host "Loading environment variables..." -ForegroundColor Yellow
    Get-Content '.\.env' | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
    Write-Host "Environment loaded!`n" -ForegroundColor Green
} else {
    Write-Host "WARNING: .env file not found!" -ForegroundColor Red
    exit 1
}

# Start the agent
Write-Host "Starting LiveKit agent..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop`n" -ForegroundColor Yellow

& .\livekit_venv\Scripts\python.exe -m livekit_mobile.agent start
