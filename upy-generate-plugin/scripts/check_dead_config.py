#!/usr/bin/env python3
"""Detect conf.py constants that are never referenced by firmware or tests."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


CONST_RE = re.compile(r"^([A-Z][A-Z0-9_]+)\s=", re.MULTILINE)
RESERVED_CONSTANTS = {
    "PROJECT_NAME",
    "VERSION",
    "FW_VERSION",
    "BOARD_NAME",
    "LOG_DIR",
    "LOG_MAX_FILES",
    "LOG_FILES_MAX",
    "LOG_LINES_PER_FILE",
    "LOG_LEVEL",
}


def constants_from_conf(conf_path: Path) -> list[str]:
    if not conf_path.exists():
        return []
    text = conf_path.read_text(encoding="utf-8-sig")
    return sorted(set(CONST_RE.findall(text)))


def project_texts(project_dir: Path) -> dict[str, str]:
    texts = {}
    for root_name in ("firmware", "test"):
        root = project_dir / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            rel = path.relative_to(project_dir).as_posix()
            if rel == "firmware/conf.py" or rel.startswith("firmware/lib/"):
                continue
            texts[rel] = path.read_text(encoding="utf-8-sig", errors="replace")
    return texts


def import_usage(text: str, constant: str) -> bool:
    if re.search(rf"\bconf\.{re.escape(constant)}\b", text):
        return True
    if re.search(rf"\b{re.escape(constant)}\b", text):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return True
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "conf":
                imported_names.update(alias.asname or alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "conf":
                        imported_names.add(alias.asname or alias.name)
        if constant in imported_names:
            return True
        if "conf" in imported_names and re.search(rf"\bconf\.{re.escape(constant)}\b", text):
            return True
    return False


def check_project(project_dir: Path) -> dict[str, Any]:
    conf_path = project_dir / "firmware" / "conf.py"
    constants = constants_from_conf(conf_path)
    texts = project_texts(project_dir)
    used: dict[str, list[str]] = {name: [] for name in constants}
    for rel, text in texts.items():
        for constant in constants:
            if import_usage(text, constant):
                used[constant].append(rel)
    dead = [name for name in constants if not used[name] and name not in RESERVED_CONSTANTS]
    reserved_unused = [name for name in constants if not used[name] and name in RESERVED_CONSTANTS]
    warnings = [
        {
            "code": "DEAD_CONFIG",
            "constant": name,
            "message": f"{name} is defined in firmware/conf.py but not referenced by firmware or tests",
        }
        for name in dead
    ]
    warnings.extend(
        {
            "code": "RESERVED_CONFIG_UNUSED",
            "constant": name,
            "message": f"{name} is scaffold/framework configuration and is allowed to be unused by business code",
        }
        for name in reserved_unused
    )
    return {
        "check": "dead_config",
        "project_dir": str(project_dir),
        "constants": constants,
        "used": used,
        "dead_config": dead,
        "reserved_unused": reserved_unused,
        "warnings": warnings,
        "errors": [],
        "ok": not dead,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Check unused firmware/conf.py constants")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args()
    result = check_project(Path(args.project_dir))
    json_dump(result)
    return 0 if result["ok"] or args.warn_only else 2


if __name__ == "__main__":
    raise SystemExit(main())
