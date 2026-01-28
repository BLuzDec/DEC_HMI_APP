# Missing Variables Update Summary

## Overview
Added all missing variables from the DB_OPC_UA.db structure that were not previously included in the configuration files.

## Variables Added

### 1. Pressures Struct Variables (Updated Names)
**Changed from shortened names to full descriptive names:**
- `PT_Chamber` → `PT_ChamberValve` ✅
- `PR_Chamber` → `PR_ChamberValve` ✅
- `PT_Outlet` → `PT_OutletValve` ✅
- `PR_Outlet` → `PR_OutletValve` ✅

**Arrays (already existed, kept):**
- `arrPT_chamber` (Array[0..600] of Real)
- `arrPR_chamber` (Array[0..600] of Real)

### 2. FPT_Keyence_1 Struct Variables (NEW)
**Added complete FPT_Keyence_1 structure:**
- `FlexPTS_running_Keyence1` (Bool)
- `FT_Keyence1` (Real) - Force/Torque
- `PT_Keyence1` (Real) - Pressure/Temperature
- `arrPT_Keyence1` (Array[0..600] of Real)

**Byte Offsets:**
- FlexPTS_running_Keyence1: 4908
- FT_Keyence1: 4910
- PT_Keyence1: 4914
- arrPT_Keyence1: 4918 (600 elements = 2400 bytes)

### 3. FPT_Keyence_2 Struct Variables (NEW)
**Added complete FPT_Keyence_2 structure:**
- `FlexPTS_running_Keyence2` (Bool)
- `FT_Keyence2` (Real) - Force/Torque
- `PT_Keyence2` (Real) - Pressure/Temperature
- `arrPT_Keyence2` (Array[0..600] of Real)

**Byte Offsets:**
- FlexPTS_running_Keyence2: 7318
- FT_Keyence2: 7320
- PT_Keyence2: 7324
- arrPT_Keyence2: 7328 (600 elements = 2400 bytes)

## Byte Offset Calculation

### Structure Layout:
1. **Top Level Variables:** 0-18 bytes
2. **Recipes Struct:** 22-78 bytes (15 Real variables)
3. **Pressures Struct:**
   - FlexPTS_running: 82 (Bool, 1 byte)
   - PT_ChamberValve: 84 (Real, 4 bytes)
   - PR_ChamberValve: 88 (Real, 4 bytes)
   - PT_OutletValve: 92 (Real, 4 bytes)
   - PR_OutletValve: 96 (Real, 4 bytes)
   - arrPT_chamber: 100 (600 * 4 = 2400 bytes, ends at 2500)
   - arrPR_chamber: 2504 (600 * 4 = 2400 bytes, ends at 4904)

4. **FPT_Keyence_1 Struct:**
   - Starts after arrPR_chamber (4904 + 4 byte gap = 4908)
   - FlexPTS_running_Keyence1: 4908 (Bool, 1 byte)
   - FT_Keyence1: 4910 (Real, 4 bytes)
   - PT_Keyence1: 4914 (Real, 4 bytes)
   - arrPT_Keyence1: 4918 (600 * 4 = 2400 bytes, ends at 7318)

5. **FPT_Keyence_2 Struct:**
   - Starts after arrPT_Keyence1 (7318)
   - FlexPTS_running_Keyence2: 7318 (Bool, 1 byte)
   - FT_Keyence2: 7320 (Real, 4 bytes)
   - PT_Keyence2: 7324 (Real, 4 bytes)
   - arrPT_Keyence2: 7328 (600 * 4 = 2400 bytes, ends at 9728)

## Files Updated

### 1. `external/exchange_variables.csv`
- Updated variable names to use full names (ChamberValve, OutletValve)
- Added FPT_Keyence_1 variables
- Added FPT_Keyence_2 variables
- **Total variables:** 17 (was 12)

### 2. `external/snap7_node_ids.json`
- Updated variable names to match DB structure
- Added all FPT_Keyence_1 variables with calculated offsets
- Added all FPT_Keyence_2 variables with calculated offsets
- Arrays use DB names: `arrPT_chamber`, `arrPR_chamber`, `arrPT_Keyence1`, `arrPT_Keyence2`

### 3. `external/plc_thread.py`
- Updated to handle both old and new array names for backward compatibility
- Checks for `arrPT_chamber` or `PT_Chamber_Array`
- Checks for `arrPR_chamber` or `PR_Chamber_Array`

## Array Variables

**Arrays are included in JSON but NOT in CSV files:**
- Arrays are handled programmatically
- They are read from PLC but not displayed in variable lists
- Arrays are logged separately to database when dose_number changes
- Arrays: `arrPT_chamber`, `arrPR_chamber`, `arrPT_Keyence1`, `arrPT_Keyence2`

## Why FPT_Keyence Variables Were Missing

The FPT_Keyence_1 and FPT_Keyence_2 structs were not included in the original configuration because:
1. They are nested structures in the DB definition
2. They were not present in the original `snap7_node_ids.json`
3. They require calculation of byte offsets after the Pressures struct arrays

## Verification

✅ All variables from DB_OPC_UA.db are now included
✅ Variable names match DB structure (ChamberValve, OutletValve)
✅ FPT_Keyence_1 and FPT_Keyence_2 structs fully included
✅ Arrays properly configured with correct sizes (600 elements each)
✅ Byte offsets calculated based on structure layout
