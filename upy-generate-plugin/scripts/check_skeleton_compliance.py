#!/usr/bin/env python3
"""Check that generated code still complies with scaffold choices."""

from __future__ import annotations

import argparse
import ast
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


MIN_BOOT_DELAY_SECONDS = 3.0


def _literal_number(node: ast.AST, constants: dict[str, float]) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _literal_number(node.operand, constants)
        return -value if value is not None else None
    return None


def _module_constants(tree: ast.Module) -> dict[str, float]:
    constants: dict[str, float] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = _literal_number(node.value, constants)
            if value is not None:
                constants[node.targets[0].id] = value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            value = _literal_number(node.value, constants)
            if value is not None:
                constants[node.target.id] = value
    return constants


def _conf_constants(project_dir: Path) -> dict[str, float]:
    conf_path = project_dir / "firmware" / "conf.py"
    if not conf_path.exists():
        return {}
    try:
        tree = ast.parse(text(conf_path), filename=str(conf_path))
    except SyntaxError:
        return {}
    return _module_constants(tree)


def _imported_conf_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "conf":
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _sleep_seconds(
    node: ast.Call,
    constants: dict[str, float],
    conf_constants: dict[str, float],
    imported_conf_names: set[str],
) -> float | None:
    name = ""
    if isinstance(node.func, ast.Name):
        name = node.func.id
    elif isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name):
            name = f"{node.func.value.id}.{node.func.attr}"
        else:
            name = node.func.attr
    if name not in {"sleep", "time.sleep", "utime.sleep", "sleep_ms", "time.sleep_ms", "utime.sleep_ms"}:
        return None
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "conf":
        seconds = conf_constants.get(arg.attr)
    elif isinstance(arg, ast.Name) and arg.id in imported_conf_names:
        seconds = conf_constants.get(arg.id)
    else:
        seconds = _literal_number(arg, constants)
    if seconds is None:
        return None
    if name.endswith("sleep_ms"):
        return seconds / 1000
    return seconds


def has_boot_delay(project_dir: Path, main_py: str) -> bool:
    try:
        tree = ast.parse(main_py, filename="firmware/main.py")
    except SyntaxError:
        return False
    constants = _module_constants(tree)
    conf_constants = _conf_constants(project_dir)
    imported_conf_names = _imported_conf_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        seconds = _sleep_seconds(node, constants, conf_constants, imported_conf_names)
        if seconds is not None and seconds >= MIN_BOOT_DELAY_SECONDS:
            return True
    return False


def check_project(project_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    main_py = text(project_dir / "firmware" / "main.py")
    board_py = text(project_dir / "firmware" / "board.py")
    mode = detect_mode(manifest or load_project_manifest(project_dir))

    if not has_boot_delay(project_dir, main_py):
        errors.append(
            {
                "code": "BOOT_DELAY_MISSING",
                "path": "firmware/main.py",
                "minimum_seconds": MIN_BOOT_DELAY_SECONDS,
                "accepted_forms": [
                    "time.sleep(3)",
                    "utime.sleep(3)",
                    "time.sleep(BOOT_DELAY_SECONDS)",
                    "time.sleep(conf.BOOT_DELAY_SECONDS)",
                    "sleep_ms(3000)",
                ],
                "message": "main.py must keep a boot delay of at least 3 seconds for deploy/mpremote reconnect; canonical form: time.sleep(3)",
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
