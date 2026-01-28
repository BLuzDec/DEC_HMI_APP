# PowerShell script to set up virtual environment for DEC_HMI_APP

Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Green
python -m venv .venv

Write-Host "Activating virtual environment..." -ForegroundColor Green
& .\.venv\Scripts\Activate.ps1

Write-Host "Upgrading pip..." -ForegroundColor Green
python -m pip install --upgrade pip

Write-Host "Installing requirements..." -ForegroundColor Green
pip install -r requirements.txt

Write-Host "`nVirtual environment setup complete!" -ForegroundColor Green
Write-Host "To activate in the future, run: .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "Or use: .\activate.ps1" -ForegroundColor Yellow
