# Variable Loading Update Summary

## Overview
Updated the application to load variables from CSV files instead of directly from JSON, and properly separate regular variables from recipe parameters.

## Changes Made

### 1. Updated `snap7_node_ids.json` Structure
**Location:** `external/snap7_node_ids.json`

**New Structure:**
- Regular variables remain at the top level of `Node_id_flexpts_S7_1500_snap7`
- Recipe variables are now in a nested `"recipes"` object within the same node
- This maintains the node structure while clearly separating recipe parameters

**Example:**
```json
{
    "Node_id_flexpts_S7_1500_snap7": {
        "Dose_number": [20, 0, "INT"],
        "StableWeight": [20, 2, "REAL"],
        ...
        "recipes": {
            "rEjectingPressure1": [20, 22, "REAL"],
            "rTimerEjection1": [20, 26, "REAL"],
            ...
        }
    }
}
```

### 2. Updated `main_window.py` - `load_variables()` Method
**Changes:**
- Now loads regular variables from `external/exchange_variables.csv`
- Loads recipe parameters from `external/recipe_variables.csv`
- Regular variables are added to the main variable list (shown in sidebar)
- Recipe parameters are stored separately in `self.recipe_params` (shown in graph tooltips)

**Behavior:**
- Regular variables appear in the "DATA POINTS" list for graph selection
- Recipe parameters are automatically included in graph tooltips under "Recipe Parameters" section
- Recipe parameters are NOT shown in the main variable list (they're separate)

### 3. Updated `external/plc_thread.py`
**Changes:**
- Modified to read both regular variables and recipe variables from JSON
- Combines variables from main node and nested "recipes" section
- All variables (regular + recipes) are read from PLC and emitted via signals

**Logic:**
```python
# Get main node configuration
node_config = self.config['Node_id_flexpts_S7_1500_snap7']

# Add regular variables (exclude 'recipes' key)
for key, value in node_config.items():
    if key != 'recipes':
        self.take_specific_nodes[key] = value

# Add recipe variables from 'recipes' section
if 'recipes' in node_config:
    for key, value in node_config['recipes'].items():
        self.take_specific_nodes[key] = value
```

## Data Flow

1. **CSV Files** → Define which variables exist and their metadata
   - `exchange_variables.csv` → Regular operational variables
   - `recipe_variables.csv` → Recipe parameters

2. **JSON File** → Defines PLC communication addresses
   - `snap7_node_ids.json` → Contains both regular and recipe variable addresses

3. **Application Loading:**
   - `load_variables()` reads CSV files to populate UI
   - Recipe parameters are loaded separately and stored in `self.recipe_params`
   - Regular variables appear in sidebar list
   - Recipe parameters appear in graph tooltips

4. **PLC Communication:**
   - `PLCThread` reads JSON to get all variable addresses (regular + recipes)
   - All variables are read from PLC and emitted
   - Values are stored in `latest_values` dictionary
   - Recipe parameter values appear in graph tooltips automatically

## Variable Display

### Regular Variables (from exchange_variables.csv)
- **Location:** Sidebar "DATA POINTS" list
- **Usage:** Can be selected to create graphs
- **Examples:** Dose_number, StableWeight, TargetWeight, PT_Chamber, etc.

### Recipe Parameters (from recipe_variables.csv)
- **Location:** Graph tooltips under "Recipe Parameters" section
- **Usage:** Automatically displayed when hovering over graphs
- **Examples:** rEjectingPressure1, rTimerEjection1, rVacuumPressure1, etc.
- **NOT shown in:** Main variable list (kept separate)

## Benefits

1. **Clear Separation:** Recipe parameters are clearly separated from operational variables
2. **CSV-Based Configuration:** Easy to modify variable lists without editing code
3. **Automatic Display:** Recipe parameters automatically appear in graph tooltips
4. **Maintained Structure:** JSON structure maintains node organization while separating recipes
5. **Backward Compatible:** PLC communication still works with all variables
