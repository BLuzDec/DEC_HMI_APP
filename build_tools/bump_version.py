"""Read version.txt, increment the build (patch) number, and write it back.

Usage:  python build_tools/bump_version.py
Prints the NEW version to stdout so the caller can capture it.

Format: MAJOR.MINOR.BUILD  (e.g. 1.0.0 -> 1.0.1 -> 1.0.2 ...)
"""

import os

VERSION_FILE = os.path.join(os.path.dirname(__file__), "..", "version.txt")


def bump() -> str:
    with open(VERSION_FILE, "r") as f:
        version = f.read().strip()

    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")

    major, minor, build = int(parts[0]), int(parts[1]), int(parts[2])
    build += 1
    new_version = f"{major}.{minor}.{build}"

    with open(VERSION_FILE, "w") as f:
        f.write(new_version)

    return new_version


if __name__ == "__main__":
    new_ver = bump()
    print(new_ver)
