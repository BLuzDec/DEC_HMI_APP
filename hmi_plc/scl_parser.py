"""
Parse Siemens SCL (.scl) to extract VAR_INPUT, VAR_OUTPUT, VAR_IN_OUT.
Output JSON for block_definitions.
Supports UDT expansion when .udt files are in same directory.
"""
import re
import json
import os
from typing import List, Dict, Tuple, Optional


def _normalize_type(t: str) -> str:
    """Map SCL types to simple names."""
    t = t.strip().upper()
    if "REAL" in t or "LREAL" in t:
        return "Real"
    if "BOOL" in t:
        return "Bool"
    if "INT" in t or "DINT" in t or "SINT" in t:
        return "Int"
    if "TIME" in t:
        return "Time"
    return t


def _strip_comment(line: str) -> str:
    """Remove // and (* *) comments from line."""
    # Remove (* ... *) 
    while "(*" in line and "*)" in line:
        line = re.sub(r'\(\*.*?\*\)', '', line, flags=re.DOTALL)
    # Remove // to end
    if "//" in line:
        line = line[:line.index("//")]
    return line.strip()


def _parse_var_section(lines: List[str], start: int) -> Tuple[List[Dict], int]:
    """
    Parse a VAR section from lines[start:].
    Returns (list of {name, type, comment}, index after END_VAR).
    """
    vars_list = []
    i = start
    while i < len(lines):
        line = lines[i]
        raw = line
        line = _strip_comment(line)
        if not line:
            i += 1
            continue
        if re.match(r'END_VAR', line, re.I):
            return vars_list, i + 1
        # Match: name : type  or  name : "UDT_Name"
        m = re.match(r'(\w+(?:\.\w+)*)\s*:\s*(.+?)(?:\s*:=|;|$)', line)
        if m:
            name = m.group(1).strip()
            type_part = m.group(2).strip().rstrip(';')
            type_part = re.sub(r'\s*:=.*$', '', type_part).strip()
            if type_part.startswith('"') and type_part.endswith('"'):
                type_part = type_part[1:-1]
            vars_list.append({
                "name": name,
                "type": _normalize_type(type_part) if not type_part.startswith("UDT_") and not type_part.startswith('"') else type_part.strip('"'),
                "desc": "",
            })
        i += 1
    return vars_list, i


def parse_scl(content: str) -> Dict:
    """
    Parse SCL content. Returns dict with inputs, outputs, in_out.
    """
    lines = content.split('\n')
    result = {
        "inputs": [],
        "outputs": [],
        "in_out": [],
        "name": "",
        "title": "",
    }
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match(r'FUNCTION_BLOCK\s+"?(\w+)"?', stripped, re.I):
            m = re.search(r'"(\w+)"', stripped)
            if m:
                result["name"] = m.group(1)
                result["title"] = m.group(1).replace("FB_", "")
        elif re.match(r'VAR_INPUT', stripped, re.I):
            result["inputs"], i = _parse_var_section(lines, i + 1)
            continue
        elif re.match(r'VAR_OUTPUT', stripped, re.I):
            result["outputs"], i = _parse_var_section(lines, i + 1)
            continue
        elif re.match(r'VAR_IN_OUT', stripped, re.I):
            result["in_out"], i = _parse_var_section(lines, i + 1)
            continue
        i += 1
    return result


def parse_scl_file(path: str) -> Dict:
    """Parse SCL file and return block definition dict."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return parse_scl(content)


def to_block_definition(parsed: Dict, default_direction: str = "request") -> Dict:
    """
    Convert parsed SCL to block_definitions format.
    default_direction: "request" for inputs (user sends), "status" for in_out (user receives)
    """
    def add_direction(items, direction):
        for item in items:
            item["direction"] = item.get("direction", direction)

    inputs = [dict(x) for x in parsed.get("inputs", [])]
    add_direction(inputs, "request")
    outputs = [dict(x) for x in parsed.get("outputs", [])]
    in_out = [dict(x) for x in parsed.get("in_out", [])]
    add_direction(in_out, "status")

    return {
        "name": parsed.get("name", "Unknown"),
        "title": parsed.get("title", parsed.get("name", "Block")),
        "source": parsed.get("source", ""),
        "inputs": inputs,
        "outputs": outputs,
        "in_out": in_out,
    }


def parse_udt_file(path: str) -> List[Dict]:
    """Parse UDT .udt file, return list of {name, type, desc}."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    lines = content.split('\n')
    result = []
    in_struct = False
    for line in lines:
        stripped = _strip_comment(line)
        if re.match(r'STRUCT', stripped, re.I):
            in_struct = True
            continue
        if re.match(r'END_STRUCT', stripped, re.I):
            break
        if in_struct and stripped:
            m = re.match(r'(\w+)\s*:\s*(.+?)(?:\s*:=|;|$)', stripped)
            if m:
                result.append({
                    "name": m.group(1),
                    "type": _normalize_type(m.group(2).strip().rstrip(';').split(':=')[0].strip()),
                    "desc": "",
                })
    return result


def expand_udt_refs(vars_list: List[Dict], scl_dir: str) -> List[Dict]:
    """Expand UDT references (type starting with UDT_) using .udt files in scl_dir."""
    expanded = []
    for v in vars_list:
        t = v.get("type", "")
        if isinstance(t, str) and ("UDT_" in t or t.endswith("_Commands") or t.endswith("_Status") or t.endswith("_HMI")):
            udt_name = t.replace("UDT_", "").strip('"')
            udt_path = os.path.join(scl_dir, f"UDT_{udt_name}.udt")
            if not os.path.isfile(udt_path):
                udt_path = os.path.join(scl_dir, f"{udt_name}.udt")
            if os.path.isfile(udt_path):
                members = parse_udt_file(udt_path)
                prefix = v["name"]
                for m in members:
                    expanded.append({
                        "name": f"{prefix}.{m['name']}",
                        "type": m["type"],
                        "desc": m.get("desc", ""),
                    })
            else:
                expanded.append(v)
        else:
            expanded.append(v)
    return expanded


def scl_to_json(scl_path: str, json_path: Optional[str] = None, expand_udt: bool = True) -> str:
    """
    Parse SCL and write JSON. Returns JSON string.
    If json_path given, also writes to file.
    If expand_udt=True, expand UDT refs using .udt files in same dir as scl_path.
    """
    parsed = parse_scl_file(scl_path)
    parsed["source"] = os.path.basename(scl_path)
    scl_dir = os.path.dirname(os.path.abspath(scl_path))
    if expand_udt:
        parsed["inputs"] = expand_udt_refs(parsed.get("inputs", []), scl_dir)
        parsed["outputs"] = expand_udt_refs(parsed.get("outputs", []), scl_dir)
        parsed["in_out"] = expand_udt_refs(parsed.get("in_out", []), scl_dir)
    block = to_block_definition(parsed)
    j = json.dumps(block, indent=2)
    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(j)
    return j


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scl_parser.py <file.scl> [output.json]")
        sys.exit(1)
    scl_path = sys.argv[1]
    json_path = sys.argv[2] if len(sys.argv) > 2 else None
    print(scl_to_json(scl_path, json_path))
