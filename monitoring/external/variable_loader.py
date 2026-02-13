"""
Load exchange and recipe variable CSVs and provide structured data for the HMI.
Handles Variable, Type, Min, Max, Unit, Name; groups variables by same Type+Min+Max
for comparable plotting on the same axis.
"""

import csv
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class LoadedVariables:
    """Result of loading exchange and recipe CSVs."""
    all_variables: List[str] = field(default_factory=list)
    variable_metadata: Dict[str, dict] = field(default_factory=dict)
    recipe_params: List[str] = field(default_factory=list)


def _normalize_type(t: str) -> str:
    """Normalize type string for grouping (e.g. INT, Real -> uppercase, stripped)."""
    if not t or not isinstance(t, str):
        return ""
    return t.strip().upper()


def _parse_number(val: str, default: float) -> float:
    """Parse Min/Max to float; return default on error."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _parse_decimals(val: str, default: int = 2) -> int:
    """Parse Decimals column to int; return default on error or empty. Clamp to 0..10."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return default
    try:
        n = int(float(val))
        return max(0, min(10, n))
    except (ValueError, TypeError):
        return default


def _group_key(var_type: str, min_val: float, max_val: float) -> str:
    """Return a stable key for grouping variables with same type and range."""
    return f"{var_type}|{min_val}|{max_val}"


def _display_label(name: Optional[str], unit: Optional[str], variable_id: str) -> str:
    """Build axis/label string: 'Name [unit]' or 'variable_id' if no name."""
    label = (name or variable_id).strip() if name else variable_id
    unit_str = (unit or "").strip()
    if unit_str:
        return f"{label} [{unit_str}]"
    return label


def _detect_delimiter(path: str) -> str:
    """Auto-detect CSV delimiter (comma or semicolon) from the first line."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            if ";" in first_line and "," not in first_line:
                return ";"
            if first_line.count(";") > first_line.count(","):
                return ";"
    except Exception:
        pass
    return ","


def load_exchange_csv(path: str) -> Tuple[List[str], Dict[str, dict]]:
    """
    Load exchange variables CSV. Returns (list of variable names, metadata dict).
    Metadata per variable: min, max, unit, name, group_id, display_label.
    Variables with same Type, Min, Max get the same group_id for comparable plots.
    """
    variables = []
    metadata = {}
    group_keys_seen: Dict[str, str] = {}  # group_key -> group_id (e.g. "0", "1")
    next_group_id = 0

    if not path or not os.path.isfile(path):
        return variables, metadata

    try:
        delimiter = _detect_delimiter(path)
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                var_name = (row.get("Variable") or "").strip()
                if not var_name:
                    continue

                var_type = _normalize_type(row.get("Type", ""))
                min_val = _parse_number(row.get("Min", "0"), 0.0)
                max_val = _parse_number(row.get("Max", "10"), 10.0)
                unit = (row.get("Unit") or "").strip()
                name = (row.get("Name") or "").strip()
                decimals = _parse_decimals(row.get("Decimals", ""), 2)

                gkey = _group_key(var_type, min_val, max_val)
                if gkey not in group_keys_seen:
                    group_keys_seen[gkey] = str(next_group_id)
                    next_group_id += 1
                group_id = group_keys_seen[gkey]

                display_label = _display_label(name, unit, var_name)

                variables.append(var_name)
                plc_var = (row.get("PLC_VAR_NAME") or "").strip()
                array_base = (row.get("ArrayBaseType") or "").strip()
                array_size_str = (row.get("ArraySize") or "").strip()
                array_size = int(array_size_str) if array_size_str.isdigit() else None

                metadata[var_name] = {
                    "min": min_val,
                    "max": max_val,
                    "unit": unit,
                    "name": name,
                    "group_id": group_id,
                    "display_label": display_label,
                    "type": var_type,
                    "decimals": decimals,
                    "plc_var_name": plc_var or var_name,
                    "array_base_type": array_base or None,
                    "array_size": array_size,
                }
    except Exception as e:
        logging.error("Error loading exchange variables CSV %s: %s", path, e)

    return variables, metadata


def load_recipe_csv(
    path: str,
    existing_metadata: Optional[Dict[str, dict]] = None,
) -> Tuple[List[str], Dict[str, dict]]:
    """
    Load recipe variables CSV. Returns (recipe_param names, updated metadata).
    If existing_metadata is provided, recipe variables are merged in (metadata updated).
    Same grouping and Name/Unit logic as exchange.
    """
    recipe_params = []
    metadata = dict(existing_metadata) if existing_metadata else {}
    group_keys_seen = {_group_key(m.get("type", ""), m.get("min", 0), m.get("max", 10)): m.get("group_id", "0")
                       for m in metadata.values() if m.get("group_id") is not None}
    next_group_id = int(max((int(g) for g in group_keys_seen.values() if str(g).isdigit()), default=0)) + 1

    if not path or not os.path.isfile(path):
        return recipe_params, metadata

    try:
        delimiter = _detect_delimiter(path)
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                var_name = (row.get("Variable") or "").strip()
                if not var_name:
                    continue

                recipe_params.append(var_name)
                var_type = _normalize_type(row.get("Type", ""))
                min_val = _parse_number(row.get("Min", "0"), 0.0)
                max_val = _parse_number(row.get("Max", "10"), 10.0)
                unit = (row.get("Unit") or "").strip()
                name = (row.get("Name") or "").strip()
                decimals = _parse_decimals(row.get("Decimals", ""), 2)

                gkey = _group_key(var_type, min_val, max_val)
                if gkey not in group_keys_seen:
                    group_keys_seen[gkey] = str(next_group_id)
                    next_group_id += 1
                group_id = group_keys_seen[gkey]

                display_label = _display_label(name, unit, var_name)

                plc_var = (row.get("PLC_VAR_NAME") or "").strip()
                array_base = (row.get("ArrayBaseType") or "").strip()
                array_size_str = (row.get("ArraySize") or "").strip()
                array_size = int(array_size_str) if array_size_str.isdigit() else None

                metadata[var_name] = {
                    "min": min_val,
                    "max": max_val,
                    "unit": unit,
                    "name": name,
                    "group_id": group_id,
                    "display_label": display_label,
                    "type": var_type,
                    "decimals": decimals,
                    "plc_var_name": plc_var or var_name,
                    "array_base_type": array_base or None,
                    "array_size": array_size,
                }
    except Exception as e:
        logging.error("Error loading recipe variables CSV %s: %s", path, e)

    return recipe_params, metadata


def discover_csv_files(directory: Optional[str] = None):
    """Find exchange and recipe CSV files.  Prefers DB-named versions, falls back to plain names.

    Returns (exchange_path_or_None, recipe_path_or_None).
    """
    if directory is None:
        directory = os.path.dirname(os.path.abspath(__file__))

    exchange_path = None
    recipe_path = None

    if not os.path.isdir(directory):
        return exchange_path, recipe_path

    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith(".csv"):
            continue
        lower = fname.lower()
        full = os.path.join(directory, fname)

        if lower.startswith("exchange_variables"):
            # DB-named file takes priority over plain name
            if "db" in lower:
                exchange_path = full
            elif exchange_path is None:
                exchange_path = full
        elif lower.startswith("recipe_variables"):
            if "db" in lower:
                recipe_path = full
            elif recipe_path is None:
                recipe_path = full

    return exchange_path, recipe_path


def load_exchange_and_recipes(
    exchange_path: Optional[str] = None,
    recipe_path: Optional[str] = None,
    default_exchange_dir: Optional[str] = None,
    default_recipe_dir: Optional[str] = None,
) -> LoadedVariables:
    """
    Load both exchange and recipe CSVs and return a single LoadedVariables result.
    Exchange is loaded first; recipe variables are merged and get their own grouping.
    Automatically discovers DB-named CSVs (e.g. exchange_variables_DB20.csv) when
    no explicit paths are provided.
    """
    ext_dir = os.path.dirname(os.path.abspath(__file__))

    # Auto-discover DB-named CSVs as defaults
    discovered_exchange, discovered_recipe = discover_csv_files(ext_dir)

    if default_exchange_dir is None:
        default_exchange_dir = discovered_exchange or os.path.join(ext_dir, "exchange_variables.csv")
    if default_recipe_dir is None:
        default_recipe_dir = discovered_recipe or os.path.join(ext_dir, "recipe_variables.csv")

    ex_path = exchange_path or default_exchange_dir
    rec_path = recipe_path or default_recipe_dir

    all_variables = []
    variable_metadata = {}
    recipe_params = []

    exchange_vars, variable_metadata = load_exchange_csv(ex_path)
    all_variables.extend(exchange_vars)

    recipe_params, variable_metadata = load_recipe_csv(rec_path, variable_metadata)
    # Data points shown (graphs, var list) use only exchange variables; recipe_params stay separate for recipe UI.

    return LoadedVariables(
        all_variables=all_variables,
        variable_metadata=variable_metadata,
        recipe_params=recipe_params,
    )
