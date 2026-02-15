"""
Generate FC + DBs from parsed FB SCL.
Creates FC that calls the FB, DB_HMI_To_PLC (inputs), DB_PLC_To_HMI (outputs).
Reuses scl_parser and step7_exchange data_declaration for SCL types.
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scl_parser import parse_scl_file, expand_udt_refs, _normalize_type

# Reuse step7 data_declaration for SCL type mapping
import sys as _sys
_root = Path(__file__).resolve().parent.parent
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))
try:
    from step7_exchange.Step7_Templates.data_declaration import (
        declaration_for_variable,
        TYPE_MAP,
        parse_type,
    )
except ImportError:
    # Fallback if step7_exchange not on path
    TYPE_MAP = {"INT": "Int", "DINT": "DInt", "REAL": "Real", "BOOL": "Bool", "TIME": "Time"}

    def parse_type(t):
        if not t:
            return "REAL", None
        m = re.match(r"(\w+)\[(\d+)\]", (t or "").strip().upper())
        return (m.group(1), int(m.group(2))) if m else (t.strip().upper(), None)

    def declaration_for_variable(name, type_str, array_base_type=None, array_size=None):
        base, size = parse_type(type_str)
        scl = TYPE_MAP.get(base, "Real")
        return f'{name} {{ ExternalWritable := \'False\' }} : {scl};'


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
FC_TEMPLATE = TEMPLATES_DIR / "FC_FB_Caller_Template.scl"
DB_HMI_TEMPLATE = TEMPLATES_DIR / "DB_HMI_To_PLC_Template.scl"
DB_PLC_TEMPLATE = TEMPLATES_DIR / "DB_PLC_To_HMI_Template.scl"


def _flatten_name(name: str) -> str:
    """Cmd.Run -> Cmd_Run, St.Busy -> St_Busy."""
    return name.replace(".", "_")


def _scl_type_from_parsed(t: str) -> str:
    """Map parsed type to SCL type."""
    u = (t or "").strip().upper()
    return TYPE_MAP.get(u, "Real")


def _is_simulated_input(name: str) -> bool:
    """True if input is i* (feedback from IOs, simulated in app)."""
    parts = name.split(".")
    last = parts[-1] if parts else ""
    return last.startswith("i") and len(last) > 1 and last[1:2].isupper()


def _is_control_input(name: str) -> bool:
    """True if input is control (user sends from HMI)."""
    return not _is_simulated_input(name)


def _format_db_declaration(name: str, type_str: str) -> str:
    """Format variable for DB STRUCT."""
    flat = _flatten_name(name)
    scl_type = _scl_type_from_parsed(type_str)
    return f'\t{flat} : {scl_type};'


def _format_input_assignment(fb_name: str, var: Dict, db_name: str) -> str:
    """FB.Cmd.Run := "DB".Cmd_Run;"""
    flat = _flatten_name(var["name"])
    return f'\t\t#{fb_name}.{var["name"]} := "{db_name}".{flat};'


def _format_output_assignment(fb_name: str, var: Dict, db_name: str) -> str:
    """"DB".St_Busy := FB.St.Busy;"""
    flat = _flatten_name(var["name"])
    return f'\t\t"{db_name}".{flat} := #{fb_name}.{var["name"]};'


def _fb_call_arg(var: Dict, db_name: str) -> str:
    """Format for FB call: Cmd.Run := "DB".Cmd_Run"""
    flat = _flatten_name(var["name"])
    return f'{var["name"]} := "{db_name}".{flat}'


def _fb_call_arg_inout(var: Dict, db_plc: str) -> str:
    """In_out: passed by reference. Pass DB struct."""
    return f'{var["name"]} := "{db_plc}".{var["name"]}'


def generate_fc_and_dbs(
    scl_path: str,
    output_dir: Optional[str] = None,
    fb_name: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Parse FB SCL, generate FC + DB_HMI_To_PLC + DB_PLC_To_HMI.
    Returns (fc_path, db_hmi_path, db_plc_path).
    """
    scl_dir = os.path.dirname(os.path.abspath(scl_path))
    parsed = parse_scl_file(scl_path)
    parsed["inputs"] = expand_udt_refs(parsed.get("inputs", []), scl_dir)
    parsed["outputs"] = expand_udt_refs(parsed.get("outputs", []), scl_dir)
    # Keep in_out non-expanded for FC (pass UDT by reference)
    in_out_raw = list(parsed.get("in_out", []))

    name = fb_name or parsed.get("name", "FB_Unknown")
    if name.startswith("FB_"):
        short = name[3:]
    else:
        short = name

    db_hmi = f"DB_{short}_HMI_To_PLC"
    db_plc = f"DB_{short}_PLC_To_HMI"
    fc_name = f"FC_{short}_Caller"
    instance_name = f"fb_{short}"

    # Inputs for DB_HMI: control + i* (simulated). Skip complex UDTs (Parameters, Settings, Timers).
    skip_prefixes = ("Parameters", "Settings", "Timers")
    inputs_for_db = [
        v for v in parsed["inputs"]
        if not any(v["name"].startswith(p + ".") or v["name"] == p for p in skip_prefixes)
    ]
    # UDT refs we skip - need separate DBs. Add to call with placeholder.
    udt_inputs = [v for v in parsed["inputs"] if v["name"] in ("Parameters", "Settings", "Timers")]

    # DB_HMI variables
    hmi_vars = []
    for v in inputs_for_db:
        hmi_vars.append(_format_db_declaration(v["name"], v["type"]))
    hmi_vars_txt = "\n".join(hmi_vars) if hmi_vars else "\t// (no inputs)"

    # DB_PLC variables: outputs (expanded) + in_out as UDT refs (non-expanded)
    plc_vars = []
    for v in parsed["outputs"]:
        plc_vars.append(_format_db_declaration(v["name"], v["type"]))
    for v in in_out_raw:
        t = v.get("type", "")
        if isinstance(t, str) and ("UDT_" in t or "_HMI" in t):
            udt = t.strip('"').replace("UDT_", "")
            plc_vars.append(f'\t{v["name"]} : "UDT_{udt}";')
        else:
            plc_vars.append(_format_db_declaration(v["name"], v["type"]))
    plc_vars_txt = "\n".join(plc_vars) if plc_vars else "\t// (no outputs)"

    # FC: FB call args - inputs from DB_HMI + UDT refs from placeholder DBs + in_out
    call_args = [_fb_call_arg(v, db_hmi) for v in inputs_for_db]
    for v in udt_inputs:
        db_udt = f"DB_{short}_{v['name']}"
        call_args.append(f'{v["name"]} := "{db_udt}".{v["name"]}')
    for v in in_out_raw:
        call_args.append(_fb_call_arg_inout(v, db_plc))
    call_args_txt = ",\n\t\t\t".join(call_args) if call_args else ""

    # FC: output assignments (in_out is by reference, no copy back needed)
    output_assigns = []
    for v in parsed["outputs"]:
        output_assigns.append(_format_output_assignment(instance_name, v, db_plc))
    output_assigns_txt = "\n".join(output_assigns) if output_assigns else "\t\t// (no outputs)"

    out_dir = Path(output_dir or os.path.join(scl_dir, "Output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate FC
    fc_tpl = FC_TEMPLATE.read_text(encoding="utf-8")
    fc_tpl = fc_tpl.replace("{FB_NAME}", short)
    fc_tpl = fc_tpl.replace("{SOURCE}", os.path.basename(scl_path))
    fc_tpl = fc_tpl.replace("{FB_INSTANCE}", f'{instance_name} : "{name}";')
    fc_tpl = fc_tpl.replace("{FB_INSTANCE_NAME}", instance_name)
    fc_tpl = fc_tpl.replace("{FB_CALL_ARGS}", call_args_txt)
    fc_tpl = fc_tpl.replace("{OUTPUT_ASSIGNMENTS}", output_assigns_txt)
    fc_path = out_dir / f"FC_{short}_Caller.scl"
    fc_path.write_text(fc_tpl, encoding="utf-8")

    # Generate DB_HMI
    db_hmi_tpl = DB_HMI_TEMPLATE.read_text(encoding="utf-8")
    db_hmi_tpl = db_hmi_tpl.replace("{FB_NAME}", short)
    db_hmi_tpl = db_hmi_tpl.replace("{VARIABLES}", hmi_vars_txt)
    db_hmi_path = out_dir / f"DB_{short}_HMI_To_PLC.scl"
    db_hmi_path.write_text(db_hmi_tpl, encoding="utf-8")

    # Generate DB_PLC
    db_plc_tpl = DB_PLC_TEMPLATE.read_text(encoding="utf-8")
    db_plc_tpl = db_plc_tpl.replace("{FB_NAME}", short)
    db_plc_tpl = db_plc_tpl.replace("{VARIABLES}", plc_vars_txt)
    db_plc_path = out_dir / f"DB_{short}_PLC_To_HMI.scl"
    db_plc_path.write_text(db_plc_tpl, encoding="utf-8")

    return str(fc_path), str(db_hmi_path), str(db_plc_path)
