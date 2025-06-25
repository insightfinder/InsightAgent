# PowerShell script to run insightagent-go.exe every minute
# Run this script with: powershell -ExecutionPolicy Bypass -File .\run.ps1

Write-Host "Starting InsightAgent scheduler..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow

while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] Running InsightAgent..." -ForegroundColor Cyan
    
    try {
        # Run the executable non-blocking
        $process = Start-Process -FilePath ".\insightagent-go.exe" -PassThru
        Write-Host "[$timestamp] InsightAgent started with PID: $($process.Id)" -ForegroundColor Green
    }
    catch {
        Write-Host "[$timestamp] Error starting InsightAgent: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    Write-Host "[$timestamp] Waiting 60 seconds..." -ForegroundColor Gray
    Start-Sleep -Seconds 60
}
