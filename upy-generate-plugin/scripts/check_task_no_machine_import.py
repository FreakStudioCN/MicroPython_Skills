#!/usr/bin/env python3
"""Ensure business tasks do not import machine or instantiate hardware."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


FORBIDDEN_MODULES = {"machine", "pyb"}
FORBIDDEN_CALLS = {"Pin", "I2C", "SPI", "UART", "ADC", "PWM"}


def check_file(path: Path, project_dir: Path) -> list[dict[str, Any]]:
    rel = path.relative_to(project_dir).as_posix()
    errors: list[dict[str, Any]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        return [
            {
                "code": "TASK_SYNTAX_ERROR",
                "path": rel,
                "line": exc.lineno,
                "message": str(exc),
            }
        ]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    errors.append(
                        {
                            "code": "TASK_IMPORTS_MACHINE",
                            "path": rel,
                            "line": node.lineno,
                            "module": root,
                            "message": "business task must not import hardware modules",
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_MODULES:
                errors.append(
                    {
                        "code": "TASK_IMPORTS_MACHINE",
                        "path": rel,
                        "line": node.lineno,
                        "module": root,
                        "message": "business task must not import hardware modules",
                    }
                )
        elif isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in FORBIDDEN_CALLS:
                errors.append(
                    {
                        "code": "TASK_INSTANTIATES_HARDWARE",
                        "path": rel,
                        "line": node.lineno,
                        "call": name,
                        "message": "business task must receive injected drivers, not instantiate hardware",
                    }
                )
    return errors


def check(project_dir: Path) -> dict[str, Any]:
    tasks_dir = project_dir / "firmware" / "tasks"
    files = sorted(tasks_dir.glob("*.py")) if tasks_dir.exists() else []
    errors = []
    for path in files:
        errors.extend(check_file(path, project_dir))
    return {
        "check": "task_no_machine_import",
        "files_checked": len(files),
        "errors": errors,
        "warnings": [],
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Check tasks do not import machine")
    parser.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    result = check(Path(args.project_dir))
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
