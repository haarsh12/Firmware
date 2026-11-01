# Stop any process using port 8000
Write-Host "Checking for processes using port 8000..." -ForegroundColor Cyan

$connections = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue

if ($connections) {
    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    
    foreach ($procId in $processIds) {
        $process = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Found: PID $procId - $($process.ProcessName) - $($process.Path)" -ForegroundColor Yellow
            Write-Host "Stopping process..." -ForegroundColor Red
            Stop-Process -Id $procId -Force
            Write-Host "Process stopped!" -ForegroundColor Green
        }
    }
} else {
    Write-Host "Port 8000 is free!" -ForegroundColor Green
}
