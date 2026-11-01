# Clean start script - stops old backend first, then starts new one

Write-Host "`n=== Stopping any existing backend on port 8000 ===" -ForegroundColor Cyan
& "$PSScriptRoot\stop_old_backend.ps1"

Write-Host "`n=== Starting new_backend ===" -ForegroundColor Cyan
Start-Sleep -Seconds 2

# Activate virtual environment and start
& "$PSScriptRoot\venv\Scripts\Activate.ps1"
& "$PSScriptRoot\start.ps1"
