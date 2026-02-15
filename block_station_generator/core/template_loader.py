"""
Load and discover Siemens templates (FB_Template, FB_MPTS, etc.).
"""
import os


def get_templates_dir() -> str:
    """Return path to Templates/Blocks/Siemens."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "Templates", "Blocks", "Siemens")


def list_templates() -> list[dict]:
    """
    List available templates. Returns list of {name, path, is_template}.
    - FB_Template.scl = base template (placeholders)
    - FB_MPTS.scl = reference implementation
    """
    templates_dir = get_templates_dir()
    if not os.path.isdir(templates_dir):
        return []
    result = []
    for f in sorted(os.listdir(templates_dir)):
        if f.endswith(".scl"):
            path = os.path.join(templates_dir, f)
            name = os.path.splitext(f)[0]
            is_template = "Template" in name or "template" in f.lower()
            result.append({"name": name, "path": path, "is_template": is_template})
    return result
