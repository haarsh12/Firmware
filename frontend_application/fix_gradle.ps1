# Fix Gradle stuck build issue
Write-Host "=== Fixing Flutter Gradle Build ===" -ForegroundColor Cyan

# Step 1: Kill all Gradle/Java processes
Write-Host "`nStep 1: Stopping all Java/Gradle processes..." -ForegroundColor Yellow
Get-Process | Where-Object {$_.ProcessName -like "*java*"} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Step 2: Clean Flutter build
Write-Host "`nStep 2: Cleaning Flutter build cache..." -ForegroundColor Yellow
flutter clean

# Step 3: Remove corrupted Kotlin cache
Write-Host "`nStep 3: Removing corrupted Kotlin cache..." -ForegroundColor Yellow
if (Test-Path ".\build") {
    Remove-Item -Recurse -Force ".\build" -ErrorAction SilentlyContinue
}
if (Test-Path ".\android\.gradle") {
    Remove-Item -Recurse -Force ".\android\.gradle" -ErrorAction SilentlyContinue
}

# Step 4: Get dependencies
Write-Host "`nStep 4: Getting Flutter dependencies..." -ForegroundColor Yellow
flutter pub get

# Step 5: Try build with verbose output
Write-Host "`n=== Starting Flutter build (verbose mode) ===" -ForegroundColor Green
Write-Host "This may take 15-30 minutes on first build..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C if you see it stuck again`n" -ForegroundColor Red
flutter run -v
