# Block Template Structure

Templates for generating Siemens SCL function blocks and UDTs. Use placeholders when creating new blocks.

## Function Block Template (`FB_Template.scl`)

### Placeholders

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{BLOCK_NAME}` | Function block name | `FB_MPTS` |
| `{CMD_UDT}` | Commands UDT type | `UDT_MPTS_Commands` |
| `{PARAM_UDT}` | Parameters UDT type | `UDT_MPTS_Parameters` |
| `{SETTINGS_UDT}` | Settings UDT type | `UDT_MPTS_Settings` |
| `{TIMERS_UDT}` | Timers UDT type | `UDT_MPTS_Timers` |
| `{STATUS_UDT}` | Status UDT type | `UDT_MPTS_Status` |
| `{HMI_UDT}` | HMI data UDT type | `UDT_MPTS_HMI` |
| `{INPUTS}` | Block-specific inputs | `HeadInPosition : Bool;` |
| `{OUTPUTS}` | Block-specific outputs | `oValvePR : Real;` |
| `{STATE_TONS}` | TON timers for states | `ton_S10_Delay : TON_TIME;` |
| `{VARS}` | Internal variables, R_TRIGs, etc. | `rtrigRun : R_TRIG;` |
| `{RETAIN_BLOCK}` | Optional full VAR RETAIN block (omit if empty) | `VAR RETAIN` ... `END_VAR` |
| `{STATE_CONSTANTS}` | Additional state constants | `S100_SUCTION : Int := 100;` |
| `{STATE_TONS_LOGIC}` | Timer call logic in BEGIN | TON instances |
| `{RISING_TRIGGERS}` | Additional R_TRIG calls (block-specific) | `#rtrigCharge(CLK := #Cmd.Charge);` |
| `{V_CMD_LATCH}` | Additional v-variable latches (block-specific) | `IF #rtrigCharge.Q THEN #vCharge := TRUE; END_IF;` |
| `{CMD_LOGIC}` | Logic for vRun, vCharge, etc. | Trigger-to-variable mapping |
| `{OTHER_CONDITIONS}` | Block-specific conditions | Pressure, valve logic |
| `{STEPPER_LOGIC}` | CASE steps (GRAFCET) | State machine transitions |
| `{ALARM_CONDITION}` | Block-specific alarm condition | `FALSE` or `NOT #HeadInPosition` |
| `{FAULT_SAFE_OUTPUTS}` | Safe outputs in S999_FAULT | Set valves, pressures to safe state |
| `{ALARM_SAFE_OUTPUTS}` | Safe outputs in S998_ALARM | Set valves, pressures to safe state |
| `{HALT_KEEP_OUTPUTS}` | S997_HALT: keep outputs unchanged (usually empty) | Leave outputs as-is |
| `{RESET_LOGIC}` | S996_RESET: block-specific reset sequence | Homing, clearing; when done: #_Step := #S0_START_UP |
| `{STATUS_ALARM_CODE}` | S998_ALARM: set #_AlarmCode for multiple alarms | `#_AlarmCode := (Alarm1 SHL 0) OR (Alarm2 SHL 1);` |
| `{STATUS_ERROR_CODE}` | S999_FAULT: set #_ErrorCode for multiple issues | `#_ErrorCode := 2;` (e.g. tolerance timeout) |
| `{MODE_CONSTANTS}` | Block-specific mode constants | `MODE_CHARGING : Int := 10;` |
| `{HMI_TRANSFER}` | HMI_Data assignments | `#HMI_Data.iCurrentStep := #_Step;` |

### Default Structure

- **INPUTS**: Cmd, E_Stop, Alarm, Parameters, Settings, Timers + `{INPUTS}`
- **OUTPUTS**: St (status) + `{OUTPUTS}`
- **VAR IN OUT**: HMI_Data
- **VAR**: Step, PreviousStep, bFirstStepCycle, rtrigStop/Reset/Acknowledge/Halt/Run, vStop/vReset/vAcknowledge/vHalt/vRun + `{STATE_TONS}` + `{VARS}`
- **VAR RETAIN**: Optional `{RETAIN_VARS}`
- **VAR_TEMP**: Temporary_for_Alarm
- **VAR CONSTANT**: S0_START_UP, S100_IDLE, S997_HALT, S998_ALARM, S999_FAULT + `{STATE_CONSTANTS}`

### Sections in BEGIN

1. **Timers** – `{STATE_TONS_LOGIC}`
2. **Rising triggers** – rtrigStop, rtrigReset, rtrigAcknowledge, rtrigHalt, rtrigRun + `{RISING_TRIGGERS}` (block-specific)
3. **Cmd logic** – `{CMD_LOGIC}` (trigger → internal variables)
4. **Alarm/E-Stop management (BEFORE)** – E_Stop → S999_FAULT, Alarm → S998_ALARM
5. **Other conditions** – `{OTHER_CONDITIONS}`
6. **Stepper** – `{STEPPER_LOGIC}` (CASE with state transitions)
7. **HMI transfer** – `{HMI_TRANSFER}`

## UDT Templates

| Template | Placeholders |
|----------|--------------|
| `UDT_Commands_Template.udt` | `{CMD_UDT}`, `{CMD_FIELDS}` |
| `UDT_Status_Template.udt` | `{STATUS_UDT}`, `{STATUS_FIELDS}` |

### Status UDT fields (mode, multi-alarm, multi-issue)

- **Mode**: Operational/fault state (0=Disabled, 1=Idle, 2=Manual, 3=Running, 4=Halt, 5=Alarm, 6=Fault, 7=Reset; block-specific 10+)
- **AlarmCode**: DWord bitmask for multiple alarms (bit0=alarm1, bit1=alarm2, etc.)
- **ErrorCode**: Int for multiple issues (0=None, 1=E_Stop, block-specific 2+)
- **StepBeforeTrigger**: Last step before Alarm/Halt/Fault; used for recovery display

In each step of `{STEPPER_LOGIC}`, set `#_Mode` (e.g. `#_Mode := #MODE_CHARGING;` in charging steps). Standard steps S997/S998/S999/S996 set it automatically.
| `UDT_Parameters_Template.udt` | `{PARAM_UDT}`, `{PARAM_FIELDS}` |
| `UDT_Settings_Template.udt` | `{SETTINGS_UDT}`, `{SETTINGS_FIELDS}` |
| `UDT_Timers_Template.udt` | `{TIMERS_UDT}`, `{TIMER_FIELDS}` |
| `UDT_HMI_Template.udt` | `{HMI_UDT}`, `{HMI_INPUT_FIELDS}`, `{HMI_OUTPUT_FIELDS}` |

## Reference Implementation

`FB_MPTS.scl` and the `UDT_MPTS_*` files are the concrete MPTS implementation and serve as the reference for the template structure.
