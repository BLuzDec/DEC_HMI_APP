@echo off
REM ==========================================================================
REM  Build script for ProAutomation Studio installer
REM
REM  Usage:
REM    build_installer.bat              Build app + installer (uses existing .venv)
REM    build_installer.bat --install    Also install/update deps before building
REM
REM  Prerequisites:
REM    - .venv already set up with all dependencies + pyinstaller
REM    - Inno Setup 6 installed (for installer .exe – optional)
REM
REM  The resulting installer needs NO Python/TwinCAT on the TARGET machine.
REM ==========================================================================

setlocal
cd /d "%~dp0"

REM ── Parse arguments ────────────────────────────────────────────────
set INSTALL_DEPS=0
if "%~1"=="--install" set INSTALL_DEPS=1

echo.
echo ===================================================
echo   ProAutomation Studio - Build Pipeline
echo ===================================================
echo.

REM ── Step 1: Activate .venv ─────────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" goto :NO_VENV

echo [1/3] Activating .venv...
call .venv\Scripts\activate.bat
echo      Done.
echo.

REM ── Step 2: Install deps only if --install was passed ──────────────
if %INSTALL_DEPS%==0 goto :SKIP_DEPS

echo [2/3] Installing dependencies from requirements.txt...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 goto :ERR_PIP
echo      Installing PyInstaller...
pip install pyinstaller
if %ERRORLEVEL% neq 0 goto :ERR_PIP
echo.
goto :DO_BUILD

:SKIP_DEPS
echo [2/3] Skipping dependency install -- pass --install to update deps.
echo.

:DO_BUILD
REM ── Step 3: PyInstaller build ──────────────────────────────────────
echo [3/3] Running PyInstaller -- this may take a few minutes...
echo.

REM Clean previous build artifacts
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

pyinstaller main_window.spec --noconfirm
if %ERRORLEVEL% neq 0 goto :ERR_PYINSTALLER

echo.
echo [OK] PyInstaller build succeeded!
echo      Output: dist\ProAutomationApp\
echo.

REM ── Verify critical files are in the bundle ────────────────────────
REM PyInstaller 6.x places files inside _internal\ next to the exe
set MISSING=0
if not exist "dist\ProAutomationApp\ProAutomation Studio.exe" echo [WARN] Missing: ProAutomation Studio.exe & set MISSING=1
if not exist "dist\ProAutomationApp\_internal\snap7.dll" echo [WARN] Missing: _internal\snap7.dll & set MISSING=1
if not exist "dist\ProAutomationApp\_internal\external\exchange_variables.csv" echo [WARN] Missing: _internal\external\exchange_variables.csv & set MISSING=1
if not exist "dist\ProAutomationApp\_internal\Images\Dec Group_bleu_noir_transparent.png" echo [WARN] Missing: _internal\Images\Dec Group_bleu_noir_transparent.png & set MISSING=1

if %MISSING%==0 echo [OK] All critical files verified in bundle.
echo.

REM ── Step 4: Inno Setup ─────────────────────────────────────────────
echo Looking for Inno Setup Compiler...

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC goto :NO_INNO

echo [OK] Found Inno Setup at: %ISCC%
echo      Building installer...
"%ISCC%" setup_script.iss
if %ERRORLEVEL% neq 0 goto :ERR_INNO

echo.
echo ===================================================
echo   BUILD COMPLETE!
echo   Installer: InstallerOutput\ProAutomation_Studio_Setup.exe
echo ===================================================
goto :DONE

REM ── Error / info labels ────────────────────────────────────────────

:NO_VENV
echo [ERROR] .venv not found. Create it first:
echo         python -m venv .venv
echo         .venv\Scripts\activate
echo         pip install -r requirements.txt pyinstaller
pause
exit /b 1

:ERR_PIP
echo [ERROR] pip install failed. Check requirements.txt.
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
echo   PyInstaller BUILD COMPLETE!
echo   Run the app from: dist\ProAutomationApp\ProAutomation Studio.exe
echo   To create the installer, install Inno Setup and re-run this script.
echo ===================================================

:DONE
echo.
pause
