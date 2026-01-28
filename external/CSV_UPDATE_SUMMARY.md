# CSV Files Update Summary

## Overview
Updated `exchange_variables.csv` based on `DB_OPC_UA.db` structure and created separate `recipe_variables.csv` for recipe parameters.

## Changes Made

### 1. Updated `exchange_variables.csv`
**Location:** `external/exchange_variables.csv`

**Contains:** Regular operational variables (NO recipe variables)
- Dose_number (Int)
- StableWeight (Real)
- TargetWeight (Real)
- EjectorPosition (Real)
- InstantDensity (Real)
- AvgDensity (Real)
- FlexPTS_running (Bool)
- PT_Chamber (Real)
- PR_Chamber (Real)
- PT_Outlet (Real)
- PR_Outlet (Real)

**Excluded:** All variables from the "Recipes" struct (those starting with "r")

### 2. Created `recipe_variables.csv`
**Location:** `external/recipe_variables.csv`

**Contains:** All recipe parameters from the "Recipes" struct in DB_OPC_UA.db
- rEjectingPressure1
- rTimerEjection1
- rEjectingPressure2
- rTimerEjection2
- rUncloggingPressure
- rVacuumPressure1
- rTimerSuction
- rVacuumPressure2
- rDelayAlternateVacuum
- rDelayCloseOutletValve
- rDelaySetEjectingPressure1
- rVibratorPressure
- rTimerVibrator
- rDelayVibrator
- rDelayAtmPressure

## Variable Mapping

### From DB_OPC_UA.db Structure:
```
Top Level Variables → exchange_variables.csv
├── Dose_number
├── StableWeight
├── TargetWeight
├── EjectorPosition
├── InstantDensity
└── AvgDensity

Pressures Struct → exchange_variables.csv
├── FlexPTS_running
├── PT_Chamber (mapped from PT_ChamberValve)
├── PR_Chamber (mapped from PR_ChamberValve)
├── PT_Outlet (mapped from PT_OutletValve)
└── PR_Outlet (mapped from PR_OutletValve)

Recipes Struct → recipe_variables.csv (SEPARATED)
├── rEjectingPressure1
├── rTimerEjection1
├── rEjectingPressure2
├── rTimerEjection2
├── rUncloggingPressure
├── rVacuumPressure1
├── rTimerSuction
├── rVacuumPressure2
├── rDelayAlternateVacuum
├── rDelayCloseOutletValve
├── rDelaySetEjectingPressure1
├── rVibratorPressure
├── rTimerVibrator
├── rDelayVibrator
└── rDelayAtmPressure
```

## Verification

✅ **exchange_variables.csv** contains NO recipe variables (no variables starting with "r")
✅ **recipe_variables.csv** contains ONLY recipe variables (all starting with "r")
✅ Variable names match those in `snap7_node_ids.json`
✅ All variables from DB_OPC_UA.db are accounted for (excluding arrays which are handled separately)

## Notes

- Arrays (arrPT_chamber, arrPR_chamber, arrPT) are not included in CSV files as they are handled programmatically
- FPT_Keyence_1 and FPT_Keyence_2 struct variables (FT, PT) are not in snap7_node_ids.json, so they were not added
- Variable names use the format from `snap7_node_ids.json` (e.g., PT_Chamber not PT_ChamberValve)
