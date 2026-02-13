"""
Generate snap7_node_ids.json from CSV files with DB numbers in their filenames.

Scans the external/ directory for CSV files matching:
  - exchange_variables_DB<N>.csv  -> exchange variables for DB number N
  - recipe_variables_DB<N>.csv    -> recipe variables for DB number N

The DB number is extracted from the filename by looking for 'DB' followed by digits.
Byte offsets are auto-calculated based on S7 variable types, starting at 0 for each DB.
If exchange and recipe CSVs share the same DB number, recipe offsets continue after exchange.

S7 alignment rules (standard / non-optimized DB):
  - Types > 1 byte are aligned to even byte boundaries.

Array syntax in the CSV Type column:
  - REAL[600] means an array of 600 REALs.
  - INT[100]  means an array of 100 INTs.  etc.

Usage:
  python generate_snap7_config.py                  # scan directory where this script lives
  python generate_snap7_config.py /path/to/folder   # scan a specific folder
"""

import csv
import json
import logging
import os
import re
import sys


# ---------------------------------------------------------------------------
# S7 variable type sizes in bytes
# ---------------------------------------------------------------------------
TYPE_SIZES = {
    "BOOL": 1,
    "BYTE": 1,
    "INT": 2,
    "WORD": 2,
    "DINT": 4,
    "DWORD": 4,
    "REAL": 4,
    "STRING": 256,  # default S7 string length (254 chars + 2 header bytes)
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_db_number(filename):
    """Extract the DB number from *filename* by matching 'DB' followed by digits.

    >>> extract_db_number("exchange_variables_DB20.csv")
    20
    >>> extract_db_number("recipe_variables_DB21.csv")
    21
    >>> extract_db_number("some_file.csv") is None
    True
    """
    match = re.search(r"DB(\d+)", filename)
    if match:
        return int(match.group(1))
    return None


def parse_type(type_str):
    """Parse the Type column.  Handles plain types and arrays.

    Returns (base_type, array_size) where *array_size* is ``None`` for scalars.

    >>> parse_type("REAL")
    ('REAL', None)
    >>> parse_type("Real[600]")
    ('REAL', 600)
    >>> parse_type("INT")
    ('INT', None)
    """
    type_str = type_str.strip().upper()
    array_match = re.match(r"(\w+)\[(\d+)\]", type_str)
    if array_match:
        return array_match.group(1), int(array_match.group(2))
    return type_str, None


def align_offset(offset, type_size):
    """Align *offset* to an even byte boundary when *type_size* > 1.

    This mirrors the standard (non-optimized) S7 Data-Block layout where
    WORD / INT / DINT / REAL must start on an even byte.
    """
    if type_size > 1 and offset % 2 != 0:
        offset += 1
    return offset


def detect_delimiter(path):
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


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_csv(csv_path, db_number, start_offset=0):
    """Read a CSV and calculate byte offsets for each variable.

    Parameters
    ----------
    csv_path : str
        Path to the CSV file (must have at least a ``Variable`` and ``Type`` column).
    db_number : int
        The S7 Data-Block number (extracted from the filename).
    start_offset : int
        Starting byte offset (used for chaining when two CSVs share one DB).

    Returns
    -------
    variables : list of (var_name, entry)
        Ordered list where *entry* is ``[db, offset, type]`` or
        ``[db, offset, type, array_size]``.
    end_offset : int
        First free byte after all variables (handy for chaining).
    """
    variables = []
    offset = start_offset

    delimiter = detect_delimiter(csv_path)
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            var_name = (row.get("Variable") or "").strip()
            if not var_name:
                continue

            type_str = (row.get("Type") or "").strip()
            base_type, array_size = parse_type(type_str)

            type_size = TYPE_SIZES.get(base_type, 0)
            if type_size == 0:
                logging.warning("Unknown type '%s' for variable '%s' — skipping", base_type, var_name)
                continue

            # Align to even byte for types > 1 byte
            offset = align_offset(offset, type_size)

            if array_size:
                entry = [db_number, offset, base_type, array_size]
                offset += type_size * array_size
            else:
                entry = [db_number, offset, base_type]
                offset += type_size

            variables.append((var_name, entry))

    return variables, offset


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_db_csvs(directory):
    """Find CSV files whose names contain a DB number.

    Returns a dict::

        {
            "exchange": [(filepath, db_number), ...],
            "recipe":   [(filepath, db_number), ...],
        }

    Multiple exchange or recipe files are supported (rare but possible).
    """
    found = {"exchange": [], "recipe": []}

    if not os.path.isdir(directory):
        return found

    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith(".csv"):
            continue

        db_num = extract_db_number(fname)
        if db_num is None:
            continue

        lower = fname.lower()
        full = os.path.join(directory, fname)

        if lower.startswith("exchange_variables"):
            found["exchange"].append((full, db_num))
        elif lower.startswith("recipe_variables"):
            found["recipe"].append((full, db_num))

    return found


def discover_csv_files(directory):
    """Find exchange and recipe CSV files.  Prefers DB-named versions, falls back to plain names.

    Returns (exchange_path_or_None, recipe_path_or_None).
    Useful for variable_loader / simulator that just need the CSV paths.
    """
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
            # DB-named file takes priority
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


# ---------------------------------------------------------------------------
# JSON generation
# ---------------------------------------------------------------------------

def generate_snap7_config(directory=None, exchange_csv=None, recipe_csv=None):
    """Generate ``snap7_node_ids.json`` from DB-named CSVs.

    The function can work in two modes:

    1. **Auto-discover** — scan *directory* for CSV files whose names contain
       ``DB<N>`` (e.g. ``exchange_variables_DB20.csv``).
    2. **Explicit paths** — pass *exchange_csv* and/or *recipe_csv* directly
       (e.g. a user-browsed file).  The DB number is still extracted from the
       filename; files without ``DB<N>`` in the name are skipped.

    Parameters
    ----------
    directory : str or None
        Folder to scan (mode 1) and where the JSON is written.
        Defaults to the directory this script lives in.
    exchange_csv : str or None
        Explicit path to an exchange CSV.  Overrides auto-discovery for exchange.
    recipe_csv : str or None
        Explicit path to a recipe CSV.  Overrides auto-discovery for recipes.

    Returns
    -------
    output_path : str or None
        Path to the generated JSON, or ``None`` if no usable CSVs were found.
    """
    if directory is None:
        directory = os.path.dirname(os.path.abspath(__file__))

    # Start with auto-discovered CSVs
    found = discover_db_csvs(directory)

    # Override with explicit paths if provided (must still have DB<N> in name)
    if exchange_csv and os.path.isfile(exchange_csv):
        db_num = extract_db_number(os.path.basename(exchange_csv))
        if db_num is not None:
            found["exchange"] = [(exchange_csv, db_num)]

    if recipe_csv and os.path.isfile(recipe_csv):
        db_num = extract_db_number(os.path.basename(recipe_csv))
        if db_num is not None:
            found["recipe"] = [(recipe_csv, db_num)]

    has_exchange = bool(found["exchange"])
    has_recipe = bool(found["recipe"])

    if not has_exchange and not has_recipe:
        logging.info("No CSV files with DB numbers found in %s", directory)
        return None

    config = {"snap7_variables": {}}
    node_config = config["snap7_variables"]

    # Track end offsets per DB number so we can chain when two CSVs share one DB
    db_end_offsets = {}

    # ------------------------------------------------------------------
    # Exchange variables  (top-level keys in the JSON)
    # ------------------------------------------------------------------
    for csv_path, db_num in found["exchange"]:
        start = db_end_offsets.get(db_num, 0)
        variables, end_offset = process_csv(csv_path, db_num, start)
        db_end_offsets[db_num] = end_offset

        for var_name, entry in variables:
            node_config[var_name] = entry

        logging.info(
            "Exchange: %s -> DB%d, %d variables, offsets %d..%d",
            os.path.basename(csv_path), db_num, len(variables), start, end_offset - 1,
        )

    # ------------------------------------------------------------------
    # Recipe variables  (nested under "recipes" key)
    # ------------------------------------------------------------------
    for csv_path, db_num in found["recipe"]:
        start = db_end_offsets.get(db_num, 0)
        variables, end_offset = process_csv(csv_path, db_num, start)
        db_end_offsets[db_num] = end_offset

        recipes = node_config.setdefault("recipes", {})
        for var_name, entry in variables:
            recipes[var_name] = entry

        logging.info(
            "Recipe:   %s -> DB%d, %d variables, offsets %d..%d",
            os.path.basename(csv_path), db_num, len(variables), start, end_offset - 1,
        )

    # ------------------------------------------------------------------
    # Write JSON
    # ------------------------------------------------------------------
    output_path = os.path.join(directory, "snap7_node_ids.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    logging.info("Generated: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Pretty-print summary (for standalone usage)
# ---------------------------------------------------------------------------

def print_summary(directory=None):
    """Print a human-readable offset table (useful for verifying against TIA Portal)."""
    if directory is None:
        directory = os.path.dirname(os.path.abspath(__file__))

    found = discover_db_csvs(directory)
    if not found["exchange"] and not found["recipe"]:
        print("No DB-named CSV files found.")
        return

    db_end_offsets = {}

    for label, key in [("EXCHANGE VARIABLES", "exchange"), ("RECIPE VARIABLES", "recipe")]:
        for csv_path, db_num in found[key]:
            start = db_end_offsets.get(db_num, 0)
            variables, end_offset = process_csv(csv_path, db_num, start)
            db_end_offsets[db_num] = end_offset

            print(f"\n{'=' * 70}")
            print(f"  {label}  —  {os.path.basename(csv_path)}  —  DB{db_num}")
            print(f"{'=' * 70}")
            print(f"  {'Variable':<35} {'DB':>4}  {'Offset':>7}  {'Type':<10} {'Size':>6}")
            print(f"  {'-' * 35} {'-' * 4}  {'-' * 7}  {'-' * 10} {'-' * 6}")

            for var_name, entry in variables:
                db = entry[0]
                off = entry[1]
                vtype = entry[2]
                if len(entry) == 4:
                    arr = entry[3]
                    size = TYPE_SIZES.get(vtype, 0) * arr
                    print(f"  {var_name:<35} {db:>4}  {off:>7}  {vtype + f'[{arr}]':<10} {size:>6}")
                else:
                    size = TYPE_SIZES.get(vtype, 0)
                    print(f"  {var_name:<35} {db:>4}  {off:>7}  {vtype:<10} {size:>6}")

            print(f"\n  Total bytes used in DB{db_num}: {end_offset}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    target_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))

    print_summary(target_dir)
    print()

    result = generate_snap7_config(target_dir)
    if result:
        print(f"\nGenerated: {result}")
    else:
        print("\nNo DB-named CSV files found.  Name your CSVs like:")
        print("  exchange_variables_DB20.csv")
        print("  recipe_variables_DB21.csv")
