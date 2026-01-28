# Script to commit with line ending fix
# Close any Git dialogs in Cursor before running this

Write-Host "Waiting for Git lock to be released..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Remove lock file if it exists
$lockFile = ".git\index.lock"
if (Test-Path $lockFile) {
    Write-Host "Attempting to remove lock file..." -ForegroundColor Yellow
    try {
        Remove-Item -Path $lockFile -Force -ErrorAction Stop
        Write-Host "Lock file removed successfully!" -ForegroundColor Green
    } catch {
        Write-Host "Could not remove lock file. Please close Cursor's Git dialog and try again." -ForegroundColor Red
        exit 1
    }
}

# Add the .gitattributes file first
Write-Host "Adding .gitattributes file..." -ForegroundColor Cyan
git add .gitattributes

# Add all other changes
Write-Host "Adding all changes..." -ForegroundColor Cyan
git add .

# Show status
Write-Host "`nCurrent status:" -ForegroundColor Cyan
git status --short

Write-Host "`nReady to commit! You can now run:" -ForegroundColor Green
Write-Host "  git commit -m 'Your commit message'" -ForegroundColor White
