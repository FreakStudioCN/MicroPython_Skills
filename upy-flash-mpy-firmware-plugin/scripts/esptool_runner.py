#!/usr/bin/env python3
"""Run skill-local esptool or plan an esptool command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
VENV_PY = SCRIPT_DIR / (".venv-esptool/Scripts/python.exe" if sys.platform.startswith("win") else ".venv-esptool/bin/python")


def esptool_python() -> Path:
    if VENV_PY.exists():
        return VENV_PY
    raise FileNotFoundError(
        f"skill-local esptool environment missing: {VENV_PY}; run bootstrap_esptool.py --install after permission"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("esptool_args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.esptool_args:
        print(json.dumps({"status": "failed", "error": {"code": "missing_esptool_args", "message": "no esptool args supplied"}}, indent=2))
        return 2
    try:
        py = esptool_python()
    except FileNotFoundError as exc:
        result = {
            "status": "failed",
            "error": {"code": "esptool_env_missing", "message": str(exc)},
        }
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output_json:
            path = Path(args.output_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 2
    command = [str(py), "-m", "esptool"] + args.esptool_args
    result = {"status": "planned", "command": command, "rendered_command": subprocess.list2cmdline(command), "returncode": None, "stdout": "", "stderr": ""}
    if args.execute:
        proc = subprocess.run(command, text=True, capture_output=True)
        result.update({"status": "success" if proc.returncode == 0 else "failed", "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] in {"planned", "success"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
