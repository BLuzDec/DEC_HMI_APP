"""
Data declaration rules for SCL DB generation.
Maps CSV Type column to SCL declaration format.
Used when replacing {VARIABLES} and {RECIPES} in templates.
"""

import re
from typing import Optional, Tuple

# Default array size when Type is "Array" without explicit size
DEFAULT_ARRAY_SIZE = 600

# SCL type mapping: CSV type -> SCL type name
TYPE_MAP = {
    "INT": "Int",
    "DINT": "DInt",
    "REAL": "Real",
    "BOOL": "Bool",
    "BYTE": "Byte",
    "WORD": "Word",
    "DWORD": "DWord",
}


def parse_type(type_str: str) -> Tuple[str, Optional[int]]:
    """
    Parse Type column. Returns (base_type, array_size).
    array_size is None for scalars.

    Examples:
        "Real" -> ("REAL", None)
        "Real[600]" -> ("REAL", 600)
        "Array" -> ("ARRAY", None)  # caller uses ArrayBaseType + ArraySize
    """
    if not type_str or not isinstance(type_str, str):
        return "REAL", None
    t = type_str.strip().upper()
    match = re.match(r"(\w+)\[(\d+)\]", t)
    if match:
        return match.group(1), int(match.group(2))
    return t, None


def format_scalar_declaration(var_name: str, scl_type: str) -> str:
    """
    Format scalar variable for DB STRUCT.
    E.g.: Dose_number { ExternalWritable := 'False'} : Int;
    """
    return f'{var_name} {{ ExternalWritable := \'False\' }} : {scl_type};'


def format_array_declaration(var_name: str, base_type: str, size: int) -> str:
    """
    Format array variable for DB STRUCT.
    E.g.: arrPT_chamber : Array[0..600] of Real;
    """
    scl_type = TYPE_MAP.get(base_type.upper(), "Real")
    return f"{var_name} : Array[0..{size - 1}] of {scl_type};"


def declaration_for_variable(
    var_name: str,
    type_str: str,
    array_base_type: Optional[str] = None,
    array_size: Optional[int] = None,
) -> str:
    """
    Generate SCL declaration for a variable from CSV row.

    Parameters
    ----------
    var_name : str
        Variable name (e.g. Dose_number, arrPT_chamber)
    type_str : str
        Type from CSV (e.g. Int, Real, Bool, Array, Real[600])
    array_base_type : str, optional
        When type_str is "Array", the base type (Real, Int, Bool)
    array_size : int, optional
        When type_str is "Array", the array size (default 600)

    Returns
    -------
    str
        SCL declaration line
    """
    base_type, parsed_size = parse_type(type_str)

    if base_type == "ARRAY" or parsed_size is not None:
        # Array type: "Real[600]" gives base_type=REAL, parsed_size=600
        # "Array" gives base_type=ARRAY, use array_base_type + array_size
        size = parsed_size or array_size or DEFAULT_ARRAY_SIZE
        base = base_type if base_type != "ARRAY" else (array_base_type or "Real").strip().upper()
        return format_array_declaration(var_name, base, size)

    # Scalar
    scl_type = TYPE_MAP.get(base_type, "Real")
    return format_scalar_declaration(var_name, scl_type)
