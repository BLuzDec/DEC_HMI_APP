@echo off
REM ==========================================================================
REM  Build script for DecAutomation Studio installer
REM
REM  Usage:
REM    build_installer.bat              Build app + installer
REM    build_installer.bat --install    Also install/update deps before building
REM
REM  Auto-versioning:
REM    - Reads version from version.txt (e.g. 1.0.0)
REM    - On successful build, bumps the build number (1.0.0 -> 1.0.1)
REM    - Installer is named DecAutomation_Studio_Setup_vX.Y.Z.exe
REM
REM  Prerequisites:
REM    - .venv with all dependencies + pyinstaller + Pillow
REM    - Inno Setup 6 installed
REM ==========================================================================

setlocal
cd /d "%~dp0"

set INSTALL_DEPS=0
if "%~1"=="--install" set INSTALL_DEPS=1

echo.
echo ===================================================
echo   DecAutomation Studio - Build Pipeline
echo ===================================================
echo.

REM ── Step 1: Activate .venv ─────────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" goto :NO_VENV

echo [1/5] Activating .venv...
call .venv\Scripts\activate.bat
echo      Done.
echo.

REM ── Step 2: Install deps if --install ──────────────────────────────
if %INSTALL_DEPS%==0 goto :SKIP_DEPS

echo [2/5] Installing dependencies...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 goto :ERR_PIP
pip install pyinstaller Pillow
if %ERRORLEVEL% neq 0 goto :ERR_PIP
echo.
goto :READ_VERSION

:SKIP_DEPS
echo [2/5] Skipping dependency install -- pass --install to update deps.
echo.

:READ_VERSION
REM ── Step 3: Read version + generate icon ───────────────────────────
echo [3/5] Reading version and generating icon...

REM Read version from version.txt
set /p APP_VERSION=<version.txt
echo      Current version: %APP_VERSION%

REM Convert PNG logo to .ico if it doesn't exist or source is newer
python build_tools\convert_icon.py "Images\Dec Group_bleu_noir_transparent.png" "Images\app_icon.ico"
if %ERRORLEVEL% neq 0 goto :ERR_ICON
echo.

REM ── Step 4: PyInstaller build ──────────────────────────────────────
echo [4/5] Running PyInstaller -- this may take a few minutes...
echo.

if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

pyinstaller main_window.spec --noconfirm
if %ERRORLEVEL% neq 0 goto :ERR_PYINSTALLER

echo.
echo [OK] PyInstaller build succeeded!
echo.

REM Verify critical files (onboarding dashboard, monitoring, shared UI, sub-apps)
set MISSING=0
if not exist "dist\DecAutomationApp\DecAutomation Studio.exe" echo [WARN] Missing: DecAutomation Studio.exe & set MISSING=1
if not exist "dist\DecAutomationApp\_internal\snap7.dll" echo [WARN] Missing: _internal\snap7.dll & set MISSING=1
if not exist "dist\DecAutomationApp\_internal\monitoring\external\exchange_variables.csv" echo [WARN] Missing: _internal\monitoring\external\exchange_variables.csv & set MISSING=1
if not exist "dist\DecAutomationApp\_internal\Images\app_icon.ico" echo [WARN] Missing: _internal\Images\app_icon.ico & set MISSING=1
if not exist "dist\DecAutomationApp\_internal\shared\title_bar.py" echo [WARN] Missing: _internal\shared\title_bar.py & set MISSING=1
if not exist "dist\DecAutomationApp\_internal\monitoring\main_window.py" echo [WARN] Missing: _internal\monitoring\main_window.py & set MISSING=1
if not exist "dist\DecAutomationApp\_internal\step7_exchange\main.py" echo [WARN] Missing: _internal\step7_exchange\main.py & set MISSING=1
if not exist "dist\DecAutomationApp\_internal\st_block\main.py" echo [WARN] Missing: _internal\st_block\main.py & set MISSING=1
if %MISSING%==0 echo [OK] All critical files verified in bundle.
echo.

REM ── Step 5: Inno Setup ─────────────────────────────────────────────
echo [5/5] Looking for Inno Setup Compiler...

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC goto :NO_INNO

echo [OK] Found Inno Setup at: %ISCC%
echo      Building installer for version %APP_VERSION%...
"%ISCC%" /DMyAppVersion=%APP_VERSION% setup_script.iss
if %ERRORLEVEL% neq 0 goto :ERR_INNO

REM ── Success: bump version for next build ───────────────────────────
echo.
echo [OK] Bumping version for next build...
for /f %%v in ('python build_tools\bump_version.py') do set NEW_VERSION=%%v
echo      Version bumped: %APP_VERSION% -- next build will be %NEW_VERSION%

echo.
echo ===================================================
echo   BUILD COMPLETE!  v%APP_VERSION%
echo   Installer: InstallerOutput\DecAutomation_Studio_Setup_v%APP_VERSION%.exe
echo ===================================================

REM Copy installer to Labo Monitoring folder if successful
set "DEST_DIR=U:\S&T - Science & Technology\Software\Labo Monitoring\DecAutomation Studio"
if not exist "%DEST_DIR%" mkdir "%DEST_DIR%"
copy /Y "InstallerOutput\DecAutomation_Studio_Setup_v%APP_VERSION%.exe" "%DEST_DIR%\"
if %ERRORLEVEL% equ 0 (
    echo [OK] Installer copied to: %DEST_DIR%
) else (
    echo [WARN] Could not copy installer to %DEST_DIR%
)

goto :DONE

REM ── Error / info labels ────────────────────────────────────────────

:NO_VENV
echo [ERROR] .venv not found. Create it first:
echo         python -m venv .venv
echo         .venv\Scripts\activate
echo         pip install -r requirements.txt pyinstaller Pillow
pause
exit /b 1

:ERR_PIP
echo [ERROR] pip install failed. Check requirements.txt.
pause
exit /b 1

:ERR_ICON
echo [ERROR] Icon conversion failed. Make sure Pillow is installed:
echo         pip install Pillow
pause
exit /b 1

:ERR_PYINSTALLER
echo.
echo [ERROR] PyInstaller build failed. Check the output above.
pause
exit /b 1

:ERR_INNO
echo [ERROR] Inno Setup compilation failed.
pause
exit /b 1

:NO_INNO
echo [INFO] Inno Setup not found. Skipping installer creation.
echo        Install Inno Setup 6 from: https://jrsoftware.org/isdl.php
echo.
echo ===================================================
echo   PyInstaller BUILD COMPLETE -- but no installer created.
echo   Run the app from: dist\DecAutomationApp\DecAutomation Studio.exe
echo ===================================================

:DONE
echo.
pause
