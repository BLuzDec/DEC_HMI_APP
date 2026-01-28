# Script to fix Git lock file issue
# Run this script to remove the Git index lock file

Write-Host "=== Git Lock File Fixer ===" -ForegroundColor Cyan
Write-Host ""

$lockFile = ".git\index.lock"
$lockFilePath = Resolve-Path $lockFile -ErrorAction SilentlyContinue

if (-not $lockFilePath) {
    Write-Host "Lock file not found. Git should work normally now." -ForegroundColor Green
    exit 0
}

Write-Host "Lock file found at: $lockFilePath" -ForegroundColor Yellow
Write-Host ""

# Try to find what's locking the file
Write-Host "Checking for processes that might be locking the file..." -ForegroundColor Cyan
$processes = Get-Process | Where-Object {
    $_.ProcessName -like "*cursor*" -or 
    $_.ProcessName -like "*code*" -or
    $_.ProcessName -like "*git*"
}

if ($processes) {
    Write-Host "Found potentially related processes:" -ForegroundColor Yellow
    $processes | ForEach-Object {
        Write-Host "  - $($_.ProcessName) (PID: $($_.Id))" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "Please close Cursor completely, then run this script again." -ForegroundColor Red
    Write-Host "Or press Ctrl+C to cancel and close Cursor manually." -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Have you closed Cursor? (Y/N)"
    if ($response -ne "Y" -and $response -ne "y") {
        Write-Host "Please close Cursor and try again." -ForegroundColor Red
        exit 1
    }
}

# Try to remove the lock file
Write-Host ""
Write-Host "Attempting to remove lock file..." -ForegroundColor Cyan

try {
    # Method 1: Simple remove
    Remove-Item -Path $lockFile -Force -ErrorAction Stop
    Write-Host "✓ Lock file removed successfully!" -ForegroundColor Green
} catch {
    Write-Host "Method 1 failed. Trying alternative method..." -ForegroundColor Yellow
    
    try {
        # Method 2: Use cmd to delete
        $result = cmd /c "del /F /Q `"$lockFile`" 2>&1"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Lock file removed using cmd!" -ForegroundColor Green
        } else {
            throw "Failed"
        }
    } catch {
        Write-Host "Method 2 failed. Trying Method 3..." -ForegroundColor Yellow
        
        try {
            # Method 3: Take ownership and delete
            $acl = Get-Acl $lockFile
            $owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            $acl.SetOwner([System.Security.Principal.NTAccount]$owner)
            Set-Acl -Path $lockFile -AclObject $acl
            Remove-Item -Path $lockFile -Force -ErrorAction Stop
            Write-Host "✓ Lock file removed after taking ownership!" -ForegroundColor Green
        } catch {
            Write-Host ""
            Write-Host "✗ Could not remove lock file automatically." -ForegroundColor Red
            Write-Host ""
            Write-Host "Manual steps:" -ForegroundColor Yellow
            Write-Host "1. Close Cursor completely" -ForegroundColor White
            Write-Host "2. Open File Explorer and navigate to: .git folder" -ForegroundColor White
            Write-Host "3. Delete the 'index.lock' file manually" -ForegroundColor White
            Write-Host "4. Or run this command in a NEW PowerShell window (not in Cursor):" -ForegroundColor White
            Write-Host "   Remove-Item '$lockFile' -Force" -ForegroundColor Cyan
            exit 1
        }
    }
}

# Verify it's gone
Start-Sleep -Seconds 1
if (-not (Test-Path $lockFile)) {
    Write-Host ""
    Write-Host "✓✓✓ Success! Lock file has been removed." -ForegroundColor Green
    Write-Host "You can now commit your changes." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  git add ." -ForegroundColor White
    Write-Host "  git commit -m 'Your commit message'" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "✗ Lock file still exists. Please close Cursor and try again." -ForegroundColor Red
    exit 1
}
