# Virtual Environment Setup Instructions

**This project uses `.venv` as the virtual environment folder.**

## Quick Start

### Option 1: Using PowerShell Script (Recommended)
```powershell
.\setup_venv.ps1
```

### Option 2: Using Batch Script
```cmd
setup_venv.bat
```

### Option 3: Manual Setup

#### Step 1: Create Virtual Environment
```powershell
python -m venv .venv
```

#### Step 2: Activate Virtual Environment

**In PowerShell (Easiest):**
```powershell
.\activate.ps1
```

**Or directly:**
```powershell
.\.venv\Scripts\Activate.ps1
```

**In Command Prompt (CMD):**
```cmd
activate.bat
```

**Or directly:**
```cmd
.venv\Scripts\activate.bat
```

**Note:** If you get an execution policy error in PowerShell, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Step 3: Install Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

## Daily Usage

### Activate Virtual Environment

**PowerShell (Easiest):**
```powershell
.\activate.ps1
```

**Or:**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Command Prompt:**
```cmd
activate.bat
```

**Or:**
```cmd
.venv\Scripts\activate.bat
```

When activated, you'll see `(.venv)` at the beginning of your command prompt.

### Check Which Venv is Active
```powershell
.\check_venv.ps1
```

### Run Your Application
```powershell
python main.py
```

### Deactivate Virtual Environment
```powershell
deactivate
```

## Troubleshooting

### PowerShell Execution Policy Error
If you see: "cannot be loaded because running scripts is disabled on this system"

Run this command in PowerShell (as Administrator):
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Python Not Found
Make sure Python is installed and added to your PATH. Check with:
```powershell
python --version
```

### Virtual Environment Already Exists
If you need to recreate the virtual environment:
```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Verify You're Using .venv
Run the check script:
```powershell
.\check_venv.ps1
```

This will tell you:
- If a virtual environment is active
- Which one is active (.venv or venv)
- The Python version and path
