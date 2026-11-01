$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = "C:\Users\LOQ\AppData\Local\Programs\Python\Python311\python.exe"
$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

if (-not (Test-Path $python)) { throw "Python 3.11 was not found: $python" }
if (-not (Test-Path $cloudflared)) { throw "cloudflared was not found. Install it first." }

$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    Write-Host "Starting new_backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
    # Visible by design: relay/MCP command logs must remain available while
    # testing from the Xiaozhi portal.
    Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $PWD -WindowStyle Normal
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    } until ($listener -or (Get-Date) -ge $deadline)
}

if (-not $listener) {
    throw "Backend did not start on port 8000. Run .\start.ps1 and resolve its errors first."
}

Write-Host "" 
Write-Host "Copy the https://...trycloudflare.com URL printed below and append:" -ForegroundColor Yellow
Write-Host "/xiaozhi/mcp?key=YOUR_XIAOZHI_MCP_SHARED_SECRET" -ForegroundColor Yellow
Write-Host "Keep this terminal open. Closing it stops the public test URL." -ForegroundColor Yellow
& $cloudflared tunnel --url http://127.0.0.1:8000
