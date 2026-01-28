@echo off
REM Batch script to set up virtual environment for DEC_HMI_APP

echo Creating virtual environment (.venv)...
python -m venv .venv

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing requirements...
pip install -r requirements.txt

echo.
echo Virtual environment setup complete!
echo To activate in the future, run: .venv\Scripts\activate.bat
echo Or use: activate.bat
pause
