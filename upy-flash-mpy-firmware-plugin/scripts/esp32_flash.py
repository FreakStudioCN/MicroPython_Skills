#!/usr/bin/env python3
"""Plan or execute ESP32 flashing from parsed MicroPython page instructions."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
VENV_PY = SCRIPT_DIR / (".venv-esptool/Scripts/python.exe" if sys.platform.startswith("win") else ".venv-esptool/bin/python")

CHIP_BY_BOARD = {
    "ESP32_GENERIC": "esp32",
    "ESP32_GENERIC_S2": "esp32s2",
    "ESP32_GENERIC_S3": "esp32s3",
    "ESP32_GENERIC_C2": "esp32c2",
    "ESP32_GENERIC_C3": "esp32c3",
    "ESP32_GENERIC_C5": "esp32c5",
    "ESP32_GENERIC_C6": "esp32c6",
}


def infer_chip(board_name: str, chip_family: str | None) -> str:
    chip = (chip_family or "").lower().replace("-", "").replace("_", "")
    if chip.startswith("esp32"):
        return chip
    return CHIP_BY_BOARD.get(board_name.upper(), "auto")


def command_style(help_text: str) -> str:
    if "write_flash" in help_text:
        return "underscore"
    if "write-flash" in help_text:
        return "hyphen"
    return "underscore"


def esptool_python(required: bool) -> Path:
    if VENV_PY.exists():
        return VENV_PY
    if required:
        raise FileNotFoundError(
            f"skill-local esptool environment missing: {VENV_PY}; run bootstrap_esptool.py --install after permission"
        )
    return VENV_PY


def resolve_style(explicit: str, *, require_env: bool) -> tuple[str, list[str]]:
    if explicit != "auto":
        return explicit, []
    py = esptool_python(require_env)
    if not py.exists():
        return "underscore", [
            "skill-local esptool environment is missing; plan uses esptool 4.11 underscore command style"
        ]
    proc = subprocess.run([str(py), "-m", "esptool", "--help"], text=True, capture_output=True)
    return command_style(proc.stdout + proc.stderr), []


def esptool_version() -> str | None:
    if not VENV_PY.exists():
        return None
    proc = subprocess.run([str(VENV_PY), "-m", "esptool", "version"], text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else None


def op_name(name: str, style: str) -> str:
    if style == "hyphen":
        return name.replace("_", "-")
    return name.replace("-", "_")


def build_commands(resolved: dict[str, Any], firmware: str, port: str, chip_family: str | None, style: str) -> tuple[str, int, str, list[list[str]]]:
    board_name = resolved["board_name"]
    install = resolved.get("install") or {}
    chip = infer_chip(board_name, chip_family)
    baud = int(install.get("baud") or 460800)
    offset = install.get("write_offset")
    if not offset:
        write_commands = install.get("write_commands") or []
        if write_commands:
            m = re.search(r"write[-_]flash\s+(\S+)", write_commands[0])
            if m:
                offset = m.group(1)
    if not offset:
        raise ValueError("write offset missing from parsed MicroPython page")

    common = [str(esptool_python(required=False)), "-m", "esptool", "--chip", chip, "--port", port]
    return chip, baud, offset, [
        common + [op_name("erase_flash", style)],
        common + ["--baud", str(baud), op_name("write_flash", style), offset, firmware],
    ]


def write_json(data: dict[str, Any], output: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def artifact_path(path: str, root: str | None) -> str | None:
    if not root:
        return None
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


def render_posix_command(command: list[str]) -> str:
    return shlex.join(command)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolved-json", required=True)
    parser.add_argument("--firmware", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--chip-family")
    parser.add_argument("--command-style", choices=("auto", "underscore", "hyphen"), default="auto")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--artifact-root")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        resolved = json.loads(Path(args.resolved_json).read_text(encoding="utf-8"))
        should_execute = bool(args.execute and not args.plan_only)
        if should_execute:
            esptool_python(required=True)
        style, warnings = resolve_style(args.command_style, require_env=should_execute)
        chip, baud, offset, commands = build_commands(resolved, args.firmware, args.port, args.chip_family, style)
        result: dict[str, Any] = {
            "status": "planned",
            "execute": should_execute,
            "tool": "esptool",
            "tool_version": esptool_version(),
            "command_style": style,
            "board_name": resolved.get("board_name"),
            "chip": chip,
            "port": args.port,
            "baud": baud,
            "write_offset": offset,
            "erased_first": True,
            "firmware": args.firmware,
            "commands": commands,
            "rendered_commands": [subprocess.list2cmdline(c) for c in commands],
            "rendered_commands_posix": [render_posix_command(c) for c in commands],
            "runs": [],
            "warnings": warnings,
        }
        rel_firmware = artifact_path(args.firmware, args.artifact_root)
        if args.artifact_root:
            if rel_firmware:
                result["firmware_artifact_path"] = rel_firmware
            else:
                result["warnings"].append("firmware path is not under artifact_root")
        if result["execute"]:
            if not Path(args.firmware).is_file():
                raise FileNotFoundError(f"firmware file not found: {args.firmware}")
            for command in commands:
                proc = subprocess.run(command, text=True, capture_output=True)
                result["runs"].append({"command": subprocess.list2cmdline(command), "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
                if proc.returncode != 0:
                    result["status"] = "failed"
                    result["error"] = {"code": "esptool_failed", "message": f"command failed with exit code {proc.returncode}"}
                    write_json(result, args.output_json)
                    return proc.returncode or 2
            result["status"] = "success"
        write_json(result, args.output_json)
        return 0
    except (OSError, ValueError) as exc:
        write_json({"status": "failed", "error": {"code": "esptool_failed", "message": str(exc)}}, args.output_json)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
