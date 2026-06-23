#!/usr/bin/env python3
"""Create/check a skill-local esptool environment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import venv
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
VENV_DIR = SCRIPT_DIR / ".venv-esptool"
REQ_FILE = SCRIPT_DIR / "requirements-esptool.txt"


def venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--install", action="store_true", help="Install dependencies if missing")
    return parser.parse_args(argv)


def write_result(data: dict, output: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def esptool_version(py: Path) -> str | None:
    proc = subprocess.run([str(py), "-m", "esptool", "version"], text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    py = venv_python()
    if not py.exists():
        if not args.install:
            write_result(
                {
                    "status": "missing",
                    "python": str(py),
                    "action_required": "install",
                    "message": "run with --install after permission",
                },
                args.output_json,
            )
            return 0
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    if args.install:
        proc = subprocess.run([str(py), "-m", "pip", "install", "-r", str(REQ_FILE)], text=True, capture_output=True)
        if proc.returncode != 0:
            write_result({"status": "failed", "python": str(py), "error": {"code": "esptool_install_failed", "message": proc.stderr or proc.stdout}}, args.output_json)
            return proc.returncode or 2
    version = esptool_version(py)
    if not version:
        write_result({"status": "failed", "python": str(py), "error": {"code": "esptool_missing", "message": "esptool is not importable in skill-local environment"}}, args.output_json)
        return 2
    write_result({"status": "success", "python": str(py), "esptool_version": version}, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
