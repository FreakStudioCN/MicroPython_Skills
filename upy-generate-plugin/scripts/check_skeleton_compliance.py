#!/usr/bin/env python3
"""Check that generated code still complies with scaffold choices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump, load_manifest_arg


def load_project_manifest(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "project-manifest.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace") if path.exists() else ""


def detect_mode(manifest: dict[str, Any]) -> str:
    for key in ("scaffold_mode", "mode"):
        value = manifest.get(key)
        if isinstance(value, str) and value:
            return value
    scaffold = manifest.get("scaffold")
    if isinstance(scaffold, dict):
        for key in ("mode", "scaffold_mode"):
            value = scaffold.get(key)
            if isinstance(value, str) and value:
                return value
    return "timer"


def check_project(project_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    main_py = text(project_dir / "firmware" / "main.py")
    board_py = text(project_dir / "firmware" / "board.py")
    mode = detect_mode(manifest or load_project_manifest(project_dir))

    if "time.sleep(3)" not in main_py and "sleep(3)" not in main_py:
        errors.append(
            {
                "code": "BOOT_DELAY_MISSING",
                "path": "firmware/main.py",
                "message": "main.py must keep a 3 second boot delay for deploy/mpremote reconnect",
            }
        )
    if mode == "timer" and "Scheduler" not in main_py and "timer_sched" not in main_py:
        warnings.append(
            {
                "code": "SCHEDULER_MODE_REVIEW",
                "path": "firmware/main.py",
                "message": "timer scaffold should normally use scheduler/timer tick wiring",
            }
        )
    if mode == "async" and "uasyncio" not in main_py:
        errors.append(
            {
                "code": "SCHEDULER_MODE_MISMATCH",
                "path": "firmware/main.py",
                "message": "async scaffold must use uasyncio in main.py",
            }
        )
    if mode == "thread" and "_thread" not in main_py:
        errors.append(
            {
                "code": "SCHEDULER_MODE_MISMATCH",
                "path": "firmware/main.py",
                "message": "thread scaffold must use _thread in main.py",
            }
        )
    if "Pin(" in board_py or "I2C(" in board_py or "SPI(" in board_py:
        errors.append(
            {
                "code": "BOARD_INSTANTIATES_HARDWARE",
                "path": "firmware/board.py",
                "message": "board.py should only expose pin constants/helpers, not instantiate hardware",
            }
        )
    logger_wired = "lib.logger" in main_py or "from lib import logger" in main_py
    if (project_dir / "firmware" / "lib" / "logger").exists() and not logger_wired:
        warnings.append(
            {
                "code": "LOGGER_NOT_WIRED",
                "path": "firmware/main.py",
                "message": "scaffold logger exists but main.py does not import lib.logger",
            }
        )
    if (project_dir / "firmware" / "lib" / "time_helper.py").exists():
        task_text = "\n".join(text(path) for path in (project_dir / "firmware" / "tasks").glob("*.py"))
        if "timed_function" not in task_text and "timed_coro" not in task_text:
            warnings.append(
                {
                    "code": "TIME_HELPER_NOT_USED",
                    "path": "firmware/tasks",
                    "message": "time_helper exists but generated tasks do not use timing decorators",
                }
            )
    return {
        "check": "skeleton_compliance",
        "project_dir": str(project_dir),
        "scaffold_mode": mode,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Check generate output against scaffold skeleton")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--manifest", default="", help="Optional manifest or phase_complete path")
    args = parser.parse_args()
    manifest = load_manifest_arg(args.manifest) if args.manifest else {}
    result = check_project(Path(args.project_dir), manifest)
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
