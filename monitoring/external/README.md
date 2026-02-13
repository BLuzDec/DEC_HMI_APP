# External Communication Module

This folder contains all files related to external communication, including PLC interfaces, simulators, and database management.

## Structure

- `plc_thread.py` - Main PLC communication thread using Snap7
- `plc_simulator.py` - PLC simulator for testing without hardware
- `database.py` - Database manager for storing PLC data
- `snap7_node_ids.json` - Configuration file for PLC node mappings
- `exchange_variables.csv` - CSV file used by the simulator
- `automation_data.db` - DuckDB database file (created at runtime)

## Usage

All external communication modules are imported from the `external` package:

```python
from external.plc_thread import PLCThread
from external.plc_simulator import PLCSimulator
from external.database import DatabaseManager
```

## File Paths

All file paths in this module are relative to the `external/` folder:
- Configuration files are loaded from this directory
- Database files are stored in this directory
- CSV files are read from this directory

This keeps all external communication resources organized and separate from the main application code.
