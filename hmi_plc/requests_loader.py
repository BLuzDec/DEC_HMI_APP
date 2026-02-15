"""
Load Requests CSV - outputs from HMI app to PLC (write commands, setpoints, triggers).
Format: Variable;Type;Min;Max;Unit;Name;PLC_VAR_NAME
Same structure as exchange but for write-only / request variables.
"""

import csv
import logging
import os
from typing import Dict, List, Tuple


def _detect_delimiter(path: str) -> str:
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


def load_requests_csv(path: str) -> Tuple[List[str], Dict[str, dict]]:
    """
    Load requests (outputs to PLC) CSV.
    Returns (list of variable names, metadata dict).
    Metadata: min, max, unit, name, type, plc_var_name.
    """
    variables = []
    metadata = {}

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

                var_type = (row.get("Type") or "").strip().upper()
                min_val = float(row.get("Min", "0") or 0) if str(row.get("Min", "0")).strip() else 0.0
                max_val = float(row.get("Max", "10") or 10) if str(row.get("Max", "10")).strip() else 10.0
                unit = (row.get("Unit") or "").strip()
                name = (row.get("Name") or "").strip()
                plc_var = (row.get("PLC_VAR_NAME") or "").strip() or var_name

                variables.append(var_name)
                metadata[var_name] = {
                    "min": min_val,
                    "max": max_val,
                    "unit": unit,
                    "name": name or var_name,
                    "type": var_type,
                    "plc_var_name": plc_var,
                }
    except Exception as e:
        logging.error("Error loading requests CSV %s: %s", path, e)

    return variables, metadata
