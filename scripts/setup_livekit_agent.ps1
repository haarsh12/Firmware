$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path $PSScriptRoot -Parent
$workerPython = Join-Path $projectRoot 'livekit_venv\Scripts\python.exe'

if (-not (Test-Path $workerPython)) {
    Write-Host 'Creating isolated LiveKit worker environment...'
    & py -3.11 -m venv (Join-Path $projectRoot 'livekit_venv')
}

Write-Host 'Installing the isolated LiveKit voice worker dependencies...'
& $workerPython -m pip install --upgrade pip
& $workerPython -m pip install -r (Join-Path $projectRoot 'livekit_mobile\requirements.txt')

Write-Host ''
Write-Host 'LiveKit voice worker setup is complete.' -ForegroundColor Green
Write-Host 'Start it in a separate terminal with: .\scripts\start_livekit_agent.ps1'
