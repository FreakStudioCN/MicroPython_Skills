#!/usr/bin/env python3
"""Validate generated sipeed_vision artifacts for stage A."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REQUIRED_JSONL_KEYS = ['"type"', '"label"', '"score"', '"x"', '"y"', '"w"', '"h"']
FORBIDDEN_MAIN_TOKENS = [
    "from machine import",
    "import machine",
    "mpremote",
    "esptool",
    "mip.install",
    "project-manifest.json",
    "firmware/",
]
README_REQUIRED = [
    "MaixCAM",
    "MaixPy",
    "not the MicroPython master",
    "UART1",
    "A19",
    "A18",
    "115200",
    "JSON Lines",
    "3.3",
    "5 V",
    "https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html",
    "https://wiki.sipeed.com/maixpy/",
    "https://github.com/sipeed/maixpy",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def validate(project_root: Path) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    warnings: list[str] = []
    out_dir = project_root / "sipeed_vision"
    main_py = out_dir / "main.py"
    readme = out_dir / "README.md"

    if not main_py.exists():
        errors.append("missing sipeed_vision/main.py")
    if not readme.exists():
        errors.append("missing sipeed_vision/README.md")
    if errors:
        return errors, {"errors": errors, "warnings": warnings}

    main_text = read_text(main_py)
    readme_text = read_text(readme)

    if "from maix import" not in main_text:
        errors.append("main.py must use MaixPy imports from maix")
    for token in FORBIDDEN_MAIN_TOKENS:
        if token in main_text:
            errors.append(f"main.py contains forbidden token: {token}")
    for token in ["UART", "A19", "A18", "115200"]:
        if token not in main_text:
            errors.append(f"main.py missing UART default token: {token}")
    for token in REQUIRED_JSONL_KEYS:
        if token not in main_text:
            errors.append(f"main.py missing JSONL field token: {token}")

    for token in README_REQUIRED:
        if token not in readme_text:
            errors.append(f"README.md missing required text: {token}")
    if "firmware flashing" not in readme_text.lower():
        warnings.append("README.md should mention firmware flashing is manual/external")
    if "maixhub" not in readme_text.lower():
        warnings.append("README.md should include MaixHub/model preparation guidance when AI models are involved")

    summary = {
        "project_root": str(project_root),
        "files": [
            {"path": "sipeed_vision/main.py", "sha256": sha256(main_py)},
            {"path": "sipeed_vision/README.md", "sha256": sha256(readme)},
        ],
        "warnings": warnings,
        "errors": errors,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args(argv)

    errors, summary = validate(Path(args.project_root).resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
