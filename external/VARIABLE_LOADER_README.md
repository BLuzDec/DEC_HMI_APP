# Variable loader (exchange & recipe CSVs)

The module `variable_loader.py` loads exchange and recipe variable CSVs and returns structured data for the HMI. This keeps `main_window.py` simpler and makes it easy to add features (groups, Name, Unit, etc.) in one place.

## CSV format

- **exchange_variables.csv** and **recipe_variables.csv** (or any chosen file) use the same column set.

| Column    | Required | Description |
|-----------|----------|-------------|
| Variable  | Yes      | Variable/symbol ID (e.g. `GVL_HMI.TemperaturePLC`, `PT_ChamberValve`). |
| Type      | No       | Data type (e.g. Real, INT, Bool). Used for **grouping** only (same Type+Min+Max → same group). |
| Min       | No       | Minimum value (default 0). Used for axis range and grouping. |
| Max       | No       | Maximum value (default 10). Used for axis range and grouping. |
| Unit      | No       | Unit string (e.g. `°C`, `mbar`, `bar`). Shown on graph axis as `Name [Unit]`. |
| Name      | No       | Human-readable name (can contain spaces). Shown on Y-axis and value labels as `Name [Unit]`. If missing, `Variable` is used. |

- Rows with empty `Variable` are skipped.
- **Grouping:** Variables with the same **Type**, **Min**, and **Max** get the same `group_id`. When you select variables from the same group for one graph, they are plotted on the **same Y-axis** (left) so you can compare them on one scale (e.g. two pressures in mbar).

## Axis and value labels

- Y-axis label: **Name [Unit]** (e.g. `Chamber pressure [mbar]`). If several variables from the same group are on one axis, names are combined (e.g. `Chamber pressure, Outlet pressure [mbar]`).
- Value label above the graph: **Name [Unit]: value** (e.g. `Chamber pressure [mbar]: 1.23`).

## Usage from main window

- `load_exchange_and_recipes(exchange_path=..., recipe_path=...)` returns a `LoadedVariables` object with:
  - `all_variables`: list of variable IDs
  - `variable_metadata`: dict per variable with `min`, `max`, `unit`, `name`, `group_id`, `display_label`, `type`
  - `recipe_params`: list of recipe variable IDs

- `main_window.load_variables()` calls the loader and then fills the variable list and metadata; graph creation uses `variable_metadata` for axis labels and same-group single-axis logic.
