# Script to check which virtual environment is active
Write-Host "Checking virtual environment status..." -ForegroundColor Cyan
Write-Host ""

if ($env:VIRTUAL_ENV) {
    Write-Host "Virtual environment is ACTIVE" -ForegroundColor Green
    Write-Host "  Path: $env:VIRTUAL_ENV" -ForegroundColor Yellow
    
    if ($env:VIRTUAL_ENV -like "*\.venv*") {
        Write-Host "  Using .venv (correct)" -ForegroundColor Green
    }
    elseif ($env:VIRTUAL_ENV -like "*\venv*") {
        Write-Host "  Using venv (should use .venv instead)" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "Python executable:" -ForegroundColor Cyan
    python --version
    Write-Host ""
    Write-Host "Python path:" -ForegroundColor Cyan
    (Get-Command python).Source
}
else {
    Write-Host "No virtual environment is active" -ForegroundColor Red
    Write-Host ""
    Write-Host "To activate .venv, run:" -ForegroundColor Yellow
    Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "  or" -ForegroundColor White
    Write-Host "  .\activate.ps1" -ForegroundColor White
}
