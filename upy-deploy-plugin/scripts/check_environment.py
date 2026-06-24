#!/usr/bin/env python3
"""Check host runtime requirements for upy-deploy-plugin."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from common import configure_stdio, print_json, write_json
from mpremote_runtime import availability_summary


def module_status(name: str, *, required: bool) -> dict[str, Any]:
    spec = importlib.util.find_spec(name)
    status = "available" if spec is not None else ("missing" if required else "optional_missing")
    result = {
        "module": name,
        "status": status,
        "required": required,
    }
    if spec and spec.origin:
        result["origin"] = spec.origin
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="Use mock mpremote availability for contract tests")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    mpremote = availability_summary(["mpremote"] if args.mock else None)
    modules = [
        module_status("serial", required=False),
    ]
    missing_required = []
    if mpremote["status"] != "available":
        missing_required.append("mpremote")
    result = {
        "status": "success" if not missing_required else "action_required",
        "python": sys.executable,
        "tools": {
            "mpremote": mpremote,
        },
        "python_modules": modules,
        "requirements_file": "upy-deploy-plugin/scripts/requirements-runtime.txt",
        "install_hint": "python -m pip install -r upy-deploy-plugin/scripts/requirements-runtime.txt",
        "missing_required": missing_required,
    }
    if args.output_json:
        write_json(args.output_json, result)
    print_json(result)
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
