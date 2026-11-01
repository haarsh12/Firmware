$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path '.\livekit_venv\Scripts\python.exe')) {
    throw 'LiveKit worker is not installed. Run .\scripts\setup_livekit_agent.ps1 once first.'
}

# Load environment variables from .env file
if (Test-Path '.\.env') {
    Get-Content '.\.env' | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            Write-Host "Loaded: $name" -ForegroundColor Gray
        }
    }
    Write-Host ""
}

& .\livekit_venv\Scripts\python.exe -m livekit_mobile.agent start
