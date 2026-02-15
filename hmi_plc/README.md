# HMI-PLC Dashboard

Interactive HMI screens for PLC control with Exchange, Recipes, and **Requests** (outputs from app to PLC).

## System simulations (e.g. FB_MPTS)

- **File → Open HMI_MPTS**: Opens a pre-configured MPTS simulation with:
  - **Block view** tab: FB_MPTS block with inputs/outputs table (Cmd.Run, St.Mode, oInletValvePR, etc.)
  - **Visual** tab: Valves (Inlet, Outlet, Chamber), Tank, Pump
- **Block (MPTS)** in palette: Drag a block with I/O table onto the canvas
- Block shows INPUTS and OUTPUTS tables; values are placeholders for simulation (future: connect to PLC or simulator)

## Features

- **Sidebar**: Same connection/communication style as Monitoring (Connect, Disconnect, Comm Info)
- **No datapoints list** – focused on HMI screen design
- **Load Variables**: Exchange CSV, Recipes CSV, **Requests CSV** (write commands to PLC)
- **Center**: Tabbed HMI screens
- **File → Open...**: Open HMI project (`.hmi` or `.json`) with tabbed screens

## Requests CSV Format

Same structure as exchange variables, for outputs/write commands:

```
Variable;Type;Min;Max;Unit;Name;PLC_VAR_NAME
StartRecipe;BOOL;0;1;-;Start recipe;DB_Device.StartRecipe
TargetWeight_Setpoint;REAL;0;10;g;Target weight setpoint;DB_Device.TargetWeight
```

See `monitoring/external/requests_variables_sample.csv` for an example.

## HMI Project Format

JSON with `tabs` array. Each tab has `name` and `widgets`:

```json
{
  "version": 1,
  "tabs": [
    {"name": "Main Screen", "widgets": [...]},
    {"name": "Overview", "widgets": []}
  ]
}
```

## Python HMI Libraries & Canvas Example

For industrial HMI-style interfaces in Python:

### PySide6/Qt Graphics View (recommended)

- **QGraphicsScene** + **QGraphicsView**: Canvas with coordinate-based placement
- **QGraphicsRectItem**, **QGraphicsPixmapItem**: Valves, tanks, images
- Drag-and-drop, transparent images, custom painting

Run the example:

```bash
python hmi_plc/hmi_canvas_example.py
```

### Other options

- **PyDM** (SLAC): Control system UIs, EPICS/Channel Access
- **hmPy**: PyQt5-based HMI widgets
- **Taurus**: Tango/EPICS/spec control GUIs
