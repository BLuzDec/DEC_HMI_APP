# Project Reorganization Summary

## Overview
All external/PLC communication files have been reorganized into the `external/` folder to separate external communication logic from the main application.

## Changes Made

### 1. Created `external/` Folder Structure
- New folder: `external/`
- Contains all PLC and external communication modules

### 2. Moved Files to `external/`

**Python Modules:**
- `plc_thread.py` → `external/plc_thread.py`
- `plc_simulator.py` → `external/plc_simulator.py`
- `database.py` → `external/database.py`

**Configuration Files:**
- `snap7_node_ids.json` → `external/snap7_node_ids.json`
- `exchange_variables.csv` → `external/exchange_variables.csv` (if exists)

**Library Files:**
- `snap7.dll` → `external/snap7.dll` (if exists)
- `snap7.lib` → `external/snap7.lib` (if exists)

**Database Files:**
- `automation_data.db` → Created in `external/` at runtime

### 3. Updated Imports

**main_window.py:**
- Changed: `from plc_thread import PLCThread`
- To: `from external.plc_thread import PLCThread`
- Updated: `load_variables()` to load config from `external/snap7_node_ids.json`

### 4. Updated File Paths in External Modules

All modules in `external/` now use relative paths within the `external/` folder:

- **plc_thread.py:**
  - Config file: `external/snap7_node_ids.json`
  - Database: `external/automation_data.db`

- **plc_simulator.py:**
  - CSV file: `external/exchange_variables.csv`

- **database.py:**
  - Database: `external/automation_data.db` (default)

## File Structure

```
DEC_HMI_APP/
├── external/                    # External communication module
│   ├── __init__.py
│   ├── plc_thread.py           # PLC communication thread
│   ├── plc_simulator.py        # PLC simulator
│   ├── database.py             # Database manager
│   ├── snap7_node_ids.json     # PLC node configuration
│   ├── exchange_variables.csv  # Simulator CSV data
│   ├── automation_data.db      # Database (created at runtime)
│   └── README.md               # Module documentation
├── main.py                     # Application entry point
├── main_window.py              # Main UI window
└── ... (other application files)
```

## Migration Notes

### Old Files
The old files in the root directory (`plc_thread.py`, `plc_simulator.py`, `database.py`) can be safely deleted as they have been moved to `external/`. However, they are kept for now in case of rollback needs.

### Import Changes
All imports of external modules should now use:
```python
from external.plc_thread import PLCThread
from external.plc_simulator import PLCSimulator
from external.database import DatabaseManager
```

### Configuration Files
Configuration files are now loaded from the `external/` folder. The application automatically looks for `external/snap7_node_ids.json` when loading variables.

## Benefits

1. **Better Organization**: External communication code is separated from UI/application logic
2. **Easier Maintenance**: All PLC-related files are in one location
3. **Clearer Structure**: Makes it obvious which files handle external communication
4. **Scalability**: Easy to add more external communication modules (OPC-UA, Modbus, etc.)

## Testing

After reorganization, verify:
1. Application starts without import errors
2. PLC connection works correctly
3. Variables load from `external/snap7_node_ids.json`
4. Database is created in `external/automation_data.db`
5. Simulator works with `external/exchange_variables.csv`
