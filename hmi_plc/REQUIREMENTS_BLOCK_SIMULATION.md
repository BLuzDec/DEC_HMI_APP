# HMI Block Simulation – Requirements

## Overview

Block-only HMI simulation: each block represents a function block (e.g. FB_MPTS) with inputs, outputs, and in_out variables. User controls inputs (Request) and receives outputs (Status). Each block runs in its own PLC communication thread. Play/Stop for simulation control and case scenarios.

---

## 1. SCL Parser → JSON Block Definition

### Input
- `.scl` file (Siemens SCL)
- Optional: UDT `.udt` files for nested structures (e.g. `Cmd : "UDT_MPTS_Commands"`)

### Extract
- **VAR_INPUT** → `inputs[]`
- **VAR_OUTPUT** → `outputs[]`
- **VAR_IN_OUT** → `in_out[]`

### Per variable
- `name` (e.g. `Cmd.Run`, `E_Stop`, `iChamberPressure`)
- `type` (Bool, Real, Int, Time, DInt, etc.)
- `comment` (from `//` or `(* *)`)
- For UDT refs: expand inline or keep as reference + load UDT

### Output
- `.json` file loadable by `block_definitions.py`
- Schema compatible with block component

### Parser requirements
- Regex or simple line-by-line parsing
- Handle `VAR_INPUT`, `VAR_OUTPUT`, `VAR_IN_OUT` sections
- Skip `VAR`, `VAR_TEMP`, `VAR_RETAIN`, `VAR_CONSTANT`
- Parse `name : type` and `name : "UDT_Name"`
- Optional: resolve UDT to flatten nested members

---

## 2. Block Definition JSON Schema

```json
{
  "name": "FB_MPTS",
  "title": "MPTS",
  "source": "FB_MPTS.scl",
  "inputs": [
    {"name": "Cmd.Run", "type": "Bool", "desc": "Run", "direction": "request"},
    {"name": "iChamberPressure", "type": "Real", "desc": "Chamber pressure", "direction": "status"}
  ],
  "outputs": [
    {"name": "St.Busy", "type": "Bool", "desc": "Busy"},
    {"name": "oInletValvePR", "type": "Real", "desc": "Inlet valve setpoint"}
  ],
  "in_out": [
    {"name": "HMI_Data.iStatus", "type": "Int", "desc": "Status", "direction": "status"}
  ]
}
```

### `direction` (for inputs and in_out)
- **request**: HMI sends value to PLC (user controls)
- **status**: HMI receives value from PLC (read-only display)

---

## 3. Block UI per Variable

| Type | Request (user sends) | Status (PLC sends) |
|------|----------------------|--------------------|
| Bool | Push "On" / Push "Off" (or toggle) | Read-only label (True/False) |
| Real | QDoubleSpinBox (min/max) | Read-only label |
| Int  | QSpinBox | Read-only label |
| Time | QLineEdit or spin | Read-only label |

Each row: `[Name] [Direction: Request|Status] [Control/Display]`

---

## 4. Thread per Block

- One **PLC thread** per block instance (like one thread per graph in Monitoring)
- Thread: Snap7 or ADS client
- Cycle: read outputs + in_out (status), write inputs + in_out (request)
- Block config: DB number, byte offsets (or symbol-based if supported)
- Play = start thread, Stop = stop thread
- Thread emits signals for UI updates (outputs, status vars)

### Requirements
- Reuse/adapt `PLCThread` from monitoring
- Or lighter `BlockPLCThread`: only the variables for this block
- Need address mapping: variable name → DB, offset, type, size

---

## 5. Address Mapping

Block needs PLC addresses. Options:

**A. From CSV** (like exchange_variables)
- Column: Variable, DB, Offset, Type
- One CSV per block or one shared with block filter

**B. From generated config**
- Step7 Exchange or similar generates DB layout
- JSON: `{"Cmd.Run": {"db": 100, "offset": 0, "type": "Bool"}, ...}`

**C. Manual in block definition**
- Each variable has `db`, `offset`, `type` in JSON

---

## 6. Play / Stop

- **Play**: start PLC thread(s) for all blocks (or selected)
- **Stop**: stop thread(s)
- Global or per-block Play/Stop
- Case scenarios: record/playback sequences (future)

---

## 7. Case Scenarios (Future)

- Record: log input values over time
- Playback: replay inputs to simulate scenarios
- Save/load scenario files

---

## 8. Implementation Order

1. ✅ **SCL parser** → JSON (`scl_parser.py`, File → Import SCL...)
2. ✅ **Block definition loader** (JSON → block_definitions, `load_block_from_json`)
3. ✅ **Block UI** with Request/Status (Bool: On/Off, Real: spinbox, Status: read-only)
4. ⏳ **BlockPLCThread** (or adapter of PLCThread)
5. ⏳ **Address mapping** (CSV or JSON)
6. ⏳ **Play/Stop** wiring
7. ⏳ **Remove** valve/tank/pump drag-and-drop (blocks only)

## 9. SCL Parser Usage

```bash
python hmi_plc/scl_parser.py path/to/FB_MPTS.scl output/FB_MPTS.json
```

Or: **File → Import SCL...** in HMI-PLC app.

## 10. FC Generator (from SCL)

**File → Generate FC from SCL...** creates:
- `FC_{FB}_Caller.scl` – calls the FB, reads from DB_HMI_To_PLC, writes to DB_PLC_To_HMI
- `DB_{FB}_HMI_To_PLC.scl` – HMI writes control + simulated i*
- `DB_{FB}_PLC_To_HMI.scl` – PLC writes outputs

Uses `step7_exchange` data_declaration for SCL types. Parameters, Settings, Timers (UDTs) require separate DBs.

## 11. Simulation Types (i* feedbacks)

`simulation.py` – multiple types selectable via dropdown:

| Type | Var | Parameters |
|------|-----|------------|
| **First-order (Real)** | Real | τ [s] (time constant) |
| **Boolean delay** | Bool | delay [s], trigger variable |
| **Instant** | Any | (none) |

**View → Configure simulation...** – per-variable dropdown + parameter fields.

- First-order: y(t) = target + (y0 - target) * exp(-t/τ)
- Boolean delay: output True after delay_seconds when trigger_variable becomes True
