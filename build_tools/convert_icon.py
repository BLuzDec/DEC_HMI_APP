"""Convert a PNG image to a multi-size .ico file for use as app/installer icon.

Usage:  python build_tools/convert_icon.py <input.png> <output.ico>
"""

import sys
from PIL import Image


def png_to_ico(png_path: str, ico_path: str) -> None:
    """Create a multi-resolution .ico from a PNG source."""
    img = Image.open(png_path).convert("RGBA")
    # Standard Windows icon sizes (16 through 256)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=sizes)
    print(f"[OK] Icon created: {ico_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_icon.py <input.png> <output.ico>")
        sys.exit(1)
    png_to_ico(sys.argv[1], sys.argv[2])
