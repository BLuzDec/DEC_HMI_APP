@echo off
REM ==========================================================================
REM  Build script for ProAutomation Studio installer
REM
REM  This script:
REM    1. Creates/activates a virtual environment
REM    2. Installs all dependencies + PyInstaller
REM    3. Runs PyInstaller to freeze the app into dist\ProAutomationApp\
REM    4. Optionally runs Inno Setup to produce the .exe installer
REM
REM  Prerequisites:
REM    - Python 3.10+ installed on the BUILD machine
REM    - Inno Setup 6 installed (for step 4 – optional)
REM
REM  The resulting installer needs NO Python/TwinCAT on the TARGET machine.
REM ==========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ===================================================
echo   ProAutomation Studio - Build Pipeline
echo ===================================================
echo.

REM ── Step 0: Locate Python ──────────────────────────────────────────
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found in PATH. Install Python 3.10+ first.
    pause
    exit /b 1
)
echo [OK] Python found:
python --version
echo.

REM ── Step 1: Virtual environment ────────────────────────────────────
if not exist "venv\" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment already exists.
)

echo      Activating venv...
call venv\Scripts\activate.bat

echo.

REM ── Step 2: Install dependencies ───────────────────────────────────
echo [2/4] Installing dependencies from requirements.txt...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] pip install failed. Check requirements.txt.
    pause
    exit /b 1
)

echo      Installing PyInstaller...
pip install pyinstaller
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)
echo.

REM ── Step 3: PyInstaller build ──────────────────────────────────────
echo [3/4] Running PyInstaller (this may take a few minutes)...
echo.

REM Clean previous build artifacts
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

pyinstaller main_window.spec --noconfirm
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed. Check the output above.
    pause
    exit /b 1
)

echo.
echo [OK] PyInstaller build succeeded!
echo      Output: dist\ProAutomationApp\
echo.

REM ── Verify critical files are in the bundle ────────────────────────
set MISSING=0
if not exist "dist\ProAutomationApp\ProAutomation Studio.exe" (
    echo [WARN] Missing: ProAutomation Studio.exe
    set MISSING=1
)
if not exist "dist\ProAutomationApp\snap7.dll" (
    echo [WARN] Missing: snap7.dll
    set MISSING=1
)
if not exist "dist\ProAutomationApp\external\exchange_variables.csv" (
    echo [WARN] Missing: external\exchange_variables.csv
    set MISSING=1
)
if not exist "dist\ProAutomationApp\Images\Dec Group_bleu_noir_transparent.png" (
    echo [WARN] Missing: Images\Dec Group_bleu_noir_transparent.png
    set MISSING=1
)
if %MISSING%==1 (
    echo.
    echo [WARN] Some expected files are missing from the bundle.
    echo        The app may not work correctly. Check the spec file.
    echo.
) else (
    echo [OK] All critical files verified in bundle.
    echo.
)

REM ── Step 4: Inno Setup (optional) ─────────────────────────────────
echo [4/4] Looking for Inno Setup Compiler...

set ISCC=
REM Check common install locations
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if defined ISCC (
    echo [OK] Found Inno Setup at: !ISCC!
    echo      Building installer...
    "!ISCC!" setup_script.iss
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Inno Setup compilation failed.
        pause
        exit /b 1
    )
    echo.
    echo ===================================================
    echo   BUILD COMPLETE!
    echo   Installer: InstallerOutput\ProAutomation_Studio_Setup.exe
    echo ===================================================
) else (
    echo [INFO] Inno Setup not found. Skipping installer creation.
    echo        Install Inno Setup 6 from: https://jrsoftware.org/isdl.php
    echo        Then run:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup_script.iss
    echo.
    echo ===================================================
    echo   PyInstaller BUILD COMPLETE!
    echo   You can run the app from: dist\ProAutomationApp\ProAutomation Studio.exe
    echo   To create the installer, install Inno Setup and re-run this script.
    echo ===================================================
)

echo.
pause
