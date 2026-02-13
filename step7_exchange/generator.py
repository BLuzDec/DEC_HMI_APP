"""
Step7 Exchange Blocks Generator.
Parses exchange_variables.csv and recipe_variables.csv, fills templates,
and generates DB + FC SCL blocks.
"""

import csv
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = Path(__file__).resolve().parent / "Step7_Templates"
EXCHANGE_TEMPLATE = TEMPLATES_DIR / "Exchange_Blocks_Template.scl"
VERSION_FILE = PROJECT_ROOT / "version.txt"


def _detect_delimiter(path: str) -> str:
    """Auto-detect CSV delimiter (comma or semicolon)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline()
            if ";" in first and "," not in first:
                return ";"
            if first.count(";") > first.count(","):
                return ";"
    except Exception:
        pass
    return ","


def _read_version() -> str:
    """Read application version from version.txt (same as ProAutomation Studio build)."""
    try:
        if VERSION_FILE.exists():
            return VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return "0.0.0"


def _format_version_for_scl(version: str) -> str:
    """Format version for SCL: major.minor with patch in comment, e.g. '1.0    // patch: .2'."""
    parts = (version or "0.0.0").strip().split(".")
    major = parts[0] if len(parts) > 0 else "0"
    minor = parts[1] if len(parts) > 1 else "0"
    patch = parts[2] if len(parts) > 2 else "0"
    return f"{major}.{minor}    // patch: .{patch}"


# ---------------------------------------------------------------------------
# CSV loading (reuses logic from monitoring variable_loader)
# ---------------------------------------------------------------------------

@dataclass
class VariableRow:
    """Single variable from CSV."""
    variable: str
    type_str: str
    plc_var_name: str
    array_base_type: Optional[str] = None
    array_size: Optional[int] = None
    is_array: bool = False


def load_exchange_csv(path: str) -> Tuple[List[VariableRow], List[VariableRow]]:
    """
    Load exchange variables CSV.
    Returns (scalar_vars, array_vars) for separate handling.
    """
    scalars = []
    arrays = []
    if not path or not os.path.isfile(path):
        return scalars, arrays

    try:
        delim = _detect_delimiter(path)
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                var = (row.get("Variable") or "").strip()
                if not var:
                    continue
                type_str = (row.get("Type") or "").strip()
                plc_var = (row.get("PLC_VAR_NAME") or "").strip()
                if not plc_var:
                    plc_var = var
                array_base = (row.get("ArrayBaseType") or "").strip() or None
                array_size_str = (row.get("ArraySize") or "").strip()
                array_size = int(array_size_str) if array_size_str.isdigit() else None

                base_type, parsed_size = _parse_type(type_str)
                is_arr = base_type == "ARRAY" or parsed_size is not None
                v = VariableRow(
                    variable=var,
                    type_str=type_str,
                    plc_var_name=plc_var,
                    array_base_type=array_base,
                    array_size=array_size or parsed_size,
                    is_array=is_arr,
                )
                if is_arr:
                    arrays.append(v)
                else:
                    scalars.append(v)
    except Exception as e:
        logging.error("Error loading exchange CSV %s: %s", path, e)

    return scalars, arrays


def load_recipe_csv(path: str) -> Tuple[List[VariableRow], List[VariableRow]]:
    """Load recipe variables CSV. Returns (scalar_vars, array_vars)."""
    scalars = []
    arrays = []
    if not path or not os.path.isfile(path):
        return scalars, arrays

    try:
        delim = _detect_delimiter(path)
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                var = (row.get("Variable") or "").strip()
                if not var:
                    continue
                type_str = (row.get("Type") or "").strip()
                plc_var = (row.get("PLC_VAR_NAME") or "").strip()
                if not plc_var:
                    plc_var = var
                array_base = (row.get("ArrayBaseType") or "").strip() or None
                array_size_str = (row.get("ArraySize") or "").strip()
                array_size = int(array_size_str) if array_size_str.isdigit() else None

                base_type, parsed_size = _parse_type(type_str)
                is_arr = base_type == "ARRAY" or parsed_size is not None
                v = VariableRow(
                    variable=var,
                    type_str=type_str,
                    plc_var_name=plc_var,
                    array_base_type=array_base,
                    array_size=array_size or parsed_size,
                    is_array=is_arr,
                )
                if is_arr:
                    arrays.append(v)
                else:
                    scalars.append(v)
    except Exception as e:
        logging.error("Error loading recipe CSV %s: %s", path, e)

    return scalars, arrays


def _parse_type(type_str: str) -> Tuple[str, Optional[int]]:
    """Parse Type column: (base_type, array_size or None)."""
    if not type_str:
        return "REAL", None
    t = type_str.strip().upper()
    m = re.match(r"(\w+)\[(\d+)\]", t)
    if m:
        return m.group(1), int(m.group(2))
    return t, None


# ---------------------------------------------------------------------------
# SCL generation (uses data_declaration)
# ---------------------------------------------------------------------------

def _format_variable_declaration(v: VariableRow) -> str:
    """Format one variable for DB STRUCT using data_declaration rules."""
    from .Step7_Templates.data_declaration import declaration_for_variable
    return declaration_for_variable(
        v.variable,
        v.type_str,
        array_base_type=v.array_base_type,
        array_size=v.array_size,
    )


def _format_variables_section(scalars: List[VariableRow], arrays: List[VariableRow]) -> str:
    """Format {VARIABLES} or {RECIPES} section: declarations for all variables."""
    lines = []
    for v in scalars + arrays:
        lines.append("\t" + _format_variable_declaration(v))
    return "\n".join(lines) if lines else "\t// (no variables)"


def _format_plc_var_for_scl(plc_var: str) -> str:
    """
    Ensure PLC variable is in SCL format: "DB_Name".path or "Symbol"."With Spaces".
    CSV may strip quotes; add them for DB/symbol access.
    """
    s = (plc_var or "").strip()
    if not s:
        return s
    if s.startswith('"') and s.count('"') >= 2:
        return s  # Already has proper quoting
    # Split by . and quote: first segment (DB/instance) and any with spaces/special chars
    parts = s.split(".")
    result = []
    for i, p in enumerate(parts):
        p = p.strip().strip('"')  # normalize: remove existing quotes
        if not p:
            continue
        needs_quotes = (
            i == 0  # first segment (DB/instance) always quoted in SCL
            or " " in p
            or "-" in p
            or not all(c.isalnum() or c == "_" for c in p)
        )
        result.append(f'"{p}"' if needs_quotes else p)
    return ".".join(result) if result else s


def _is_custom_code_block(plc_var: str) -> bool:
    """True if PLC_VAR_NAME contains IF (custom code block instead of simple assignment)."""
    return plc_var and "IF" in plc_var.upper()


def _replace_var_with_db_ref(code: str, var_name: str, db_name: str) -> str:
    """
    Replace exact occurrences of var_name in code with "DB_Name".var_name.
    Uses word boundaries to avoid replacing inside other identifiers.
    """
    if not code or not var_name:
        return code
    # Escape special regex chars in var_name (e.g. underscores are fine)
    pattern = r"\b" + re.escape(var_name) + r"\b"
    replacement = f'"{db_name}".{var_name}'
    return re.sub(pattern, replacement, code)


def _format_variable_assignment(v: VariableRow, db_name: str) -> str:
    """
    Format assignment line. If PLC_VAR_NAME contains IF (custom code block),
    use the full code and replace variable name with DB reference.
    Otherwise: "DB_ProAutomation_VARS".VarName := PLC_VAR_NAME;
    """
    plc = (v.plc_var_name or "").strip()
    if _is_custom_code_block(plc):
        code = _replace_var_with_db_ref(plc, v.variable, db_name)
        # Indent each line with a tab
        lines = [line if line.strip() else "" for line in code.split("\n")]
        return "\n".join("\t" + line for line in lines)
    rhs = _format_plc_var_for_scl(plc)
    return f'\t"{db_name}".{v.variable} := {rhs};'


def _format_variables_assignments(scalars: List[VariableRow], db_name: str = "DB_ProAutomation_VARS") -> str:
    """Format {VARIABLES_ASSIGNMENTS} - only scalars (arrays go in ARRAY_ASSIGNMENTS)."""
    lines = []
    for v in scalars:
        lines.append(_format_variable_assignment(v, db_name))
    return "\n".join(lines) if lines else "\t// (no scalar variables)"


def _format_recipes_assignments(scalars: List[VariableRow], arrays: List[VariableRow], db_name: str = "DB_ProAutomation_RECIPES") -> str:
    """Format {RECIPES_ASSIGNMENTS} - all recipe vars (scalars + arrays as single assignments)."""
    lines = []
    for v in scalars + arrays:
        lines.append(_format_variable_assignment(v, db_name))
    return "\n".join(lines) if lines else "\t// (no recipes)"


# Array assignment template (commented) - one block per array variable
# Uses DB_ProAutomation_VARS (flat structure) for our exchange DB
ARRAY_ASSIGNMENT_TEMPLATE = '''    //Array: {var_name}
(*
    IF ("DB_ProAutomation_VARS".FlexPTS_running OR "DB_FlexPTS".bIsBusy) AND "DB_Divers".arrValueCounter < #MAX_ARRAY_VAL THEN
        IF "DB_Param".bTriggerRecording THEN
            FOR #i := 1 TO #MAX_ARRAY_VAL DO
                "DB_ProAutomation_VARS".{var_name}[#i] := 0.0;
            END_FOR;
            "DB_Param".bTriggerRecording := FALSE;
        END_IF;
        "DB_ProAutomation_VARS".{var_name}["DB_Divers".arrValueCounter] := {plc_var_name};
        "DB_Divers".arrValueCounter := "DB_Divers".arrValueCounter + 1;
    ELSIF NOT "DB_FlexPTS".bIsBusy THEN
        "DB_Param".bTriggerRecording := TRUE;
        "DB_Divers".arrValueCounter := 0;
    END_IF;
*)'''


def _format_array_assignments(arrays: List[VariableRow]) -> str:
    """Format {ARRAY_ASSIGNMENTS} - commented template block per array variable."""
    if not arrays:
        return "\t// (no array variables)"
    lines = []
    for v in arrays:
        plc_formatted = _format_plc_var_for_scl(v.plc_var_name)
        block = ARRAY_ASSIGNMENT_TEMPLATE.format(
            var_name=v.variable,
            plc_var_name=plc_formatted,
        )
        lines.append(block)
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate(
    exchange_csv: str,
    recipe_csv: str,
    output_path: Optional[str] = None,
    template_path: Optional[str] = None,
) -> str:
    """
    Generate Step7 exchange blocks SCL file.

    Parameters
    ----------
    exchange_csv : str
        Path to exchange_variables.csv (or exchange_variables_DB20.csv)
    recipe_csv : str
        Path to recipe_variables.csv
    output_path : str, optional
        Where to write the .scl file. Default: same dir as exchange_csv, name "Exchange_Blocks.scl"
    template_path : str, optional
        Path to template. Default: Step7_Templates/Exchange_Blocks_Template.scl

    Returns
    -------
    str
        Path to generated file.
    """
    template_path = template_path or str(EXCHANGE_TEMPLATE)
    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")

    ex_scalars, ex_arrays = load_exchange_csv(exchange_csv)
    rec_scalars, rec_arrays = load_recipe_csv(recipe_csv)

    version = _read_version()

    # Build replacements
    variables_decl = _format_variables_section(ex_scalars, ex_arrays)
    recipes_decl = _format_variables_section(rec_scalars, rec_arrays)
    variables_assign = _format_variables_assignments(ex_scalars)
    recipes_assign = _format_recipes_assignments(rec_scalars, rec_arrays)
    array_assign = _format_array_assignments(ex_arrays)

    template = Path(template_path).read_text(encoding="utf-8")
    result = template
    result = result.replace("{VERSION}", _format_version_for_scl(version))
    result = result.replace("{VARIABLES}", variables_decl)
    result = result.replace("{RECIPES}", recipes_decl)
    result = result.replace("{VARIABLES_ASSIGNMENTS}", variables_assign)
    result = result.replace("{RECIPES_ASSIGNMENTS}", recipes_assign)
    result = result.replace("{ARRAY_ASSIGNMENTS}", array_assign)

    if output_path is None:
        out_dir = os.path.dirname(os.path.abspath(exchange_csv))
        output_path = os.path.join(out_dir, "Output", "Exchange_Blocks.scl")

    out_dir = os.path.dirname(output_path)
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)

    Path(output_path).write_text(result, encoding="utf-8")
    logging.info("Generated: %s", output_path)
    return output_path
