#!/usr/bin/env python3
"""Check package metadata and embedded README license attribution."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


COPYRIGHT_RE = re.compile(r"^\s*Copyright\s+.*$", re.IGNORECASE | re.MULTILINE)
LICENSE_MARKER_RE = re.compile(r"\b(?:The\s+)?MIT\s+License\b", re.IGNORECASE)


def copyright_lines(text):
    return {" ".join(match.group(0).split()) for match in COPYRIGHT_RE.finditer(text)}


def main(argv):
    parser = argparse.ArgumentParser(description="Validate README license attribution against LICENSE.")
    parser.add_argument("package", help="MicroPython driver package directory")
    args = parser.parse_args(argv)
    package = Path(args.package)
    readme = package / "README.md"
    license_file = package / "LICENSE"
    errors = []

    if not package.is_dir():
        errors.append(f"PACKAGE_NOT_FOUND: {package}")
    if not readme.is_file():
        errors.append("README_MISSING: README.md is required")
    if not license_file.is_file():
        errors.append("LICENSE_MISSING: LICENSE is required")
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1

    readme_text = readme.read_text(encoding="utf-8-sig")
    license_text = license_file.read_text(encoding="utf-8-sig")
    license_copyrights = copyright_lines(license_text)
    readme_copyrights = copyright_lines(readme_text)

    if not license_copyrights:
        errors.append("LICENSE_COPYRIGHT_MISSING: LICENSE has no copyright attribution")
    if LICENSE_MARKER_RE.search(readme_text) and not readme_copyrights:
        errors.append("README_LICENSE_ATTRIBUTION_MISSING: README embeds a license heading without copyright attribution")
    if readme_copyrights and readme_copyrights != license_copyrights:
        errors.append(
            "README_LICENSE_COPYRIGHT_MISMATCH: README copyright must exactly match LICENSE; "
            f"README={sorted(readme_copyrights)} LICENSE={sorted(license_copyrights)}"
        )

    for error in errors:
        print(f"ERROR {error}")
    print(f"Checked {package}; findings={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
