#!/usr/bin/env python3
"""Check generated MPOS App imports against MicroPython runtime risks."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


MPY_ALLOWED = {
    "sys", "os", "time", "utime", "gc", "math", "struct", "ustruct", "json", "ujson",
    "binascii", "ubinascii", "collections", "ucollections", "errno", "uerrno",
    "hashlib", "uhashlib", "io", "uio", "random", "urandom", "re", "ure",
    "select", "uselect", "socket", "usocket", "ssl", "ussl", "array", "uarray",
    "machine", "micropython", "network", "bluetooth", "framebuf", "uctypes",
    "deflate", "neopixel", "esp", "esp32", "espnow", "rp2", "zephyr", "_thread",
    "uasyncio", "lvgl", "mpos", "webcam", "pdm_mic", "adc_mic", "qrdecode",
}

CPYTHON_RISKY = {
    "asyncio",
    "typing",
    "dataclasses",
    "pathlib",
    "logging",
    "requests",
    "subprocess",
    "multiprocessing",
    "concurrent",
    "inspect",
    "importlib",
    "tempfile",
    "unittest",
}

CPYTHON_FALLBACKS = {
    "asyncio": {"uasyncio"},
    "json": {"ujson"},
    "time": {"utime"},
    "os": {"uos"},
    "struct": {"ustruct"},
    "socket": {"usocket"},
    "ssl": {"ussl"},
    "select": {"uselect"},
}

IMPORT_ERROR_NAMES = {"ImportError", "ModuleNotFoundError"}


def local_roots(app_dir: Path) -> set[str]:
    roots = set()
    assets = app_dir / "assets"
    if assets.exists():
        for child in assets.iterdir():
            if child.suffix == ".py":
                roots.add(child.stem)
            elif child.is_dir():
                roots.add(child.name)
    return roots


def iter_files(app_dir: Path) -> list[Path]:
    assets = app_dir / "assets"
    if not assets.exists():
        return []
    return sorted(path for path in assets.rglob("*.py") if "__pycache__" not in path.parts)


def import_records_from_nodes(nodes: list[ast.stmt]) -> list[dict[str, Any]]:
    imports: list[dict[str, Any]] = []
    for parent in nodes:
        for node in ast.walk(parent):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"module": alias.name.split(".")[0], "line": node.lineno, "kind": "import"})
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.append({"module": node.module.split(".")[0], "line": node.lineno, "kind": "from"})
    return imports


def catches_import_error(handler: ast.ExceptHandler) -> bool:
    exc_type = handler.type
    if isinstance(exc_type, ast.Name):
        return exc_type.id in IMPORT_ERROR_NAMES
    if isinstance(exc_type, ast.Attribute):
        return exc_type.attr in IMPORT_ERROR_NAMES
    if isinstance(exc_type, ast.Tuple):
        return any(
            isinstance(item, ast.Name) and item.id in IMPORT_ERROR_NAMES
            or isinstance(item, ast.Attribute) and item.attr in IMPORT_ERROR_NAMES
            for item in exc_type.elts
        )
    return False


def fallback_imports(tree: ast.AST) -> dict[tuple[str, int, str], dict[str, Any]]:
    fallbacks: dict[tuple[str, int, str], dict[str, Any]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        try_roots = {item["module"] for item in import_records_from_nodes(node.body)}
        for handler in node.handlers:
            if not catches_import_error(handler):
                continue
            for item in import_records_from_nodes(handler.body):
                module = item["module"]
                fallback_for = sorted(try_roots & CPYTHON_FALLBACKS.get(module, set()))
                if fallback_for:
                    fallbacks[(module, item["line"], item["kind"])] = {"fallback_for": fallback_for}
    return fallbacks


def check_file(path: Path, allowed_roots: set[str], strict_unknown: bool) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        return ([{"code": "PY_SYNTAX_ERROR", "path": str(path), "line": exc.lineno, "message": str(exc)}], warnings)

    fallback_by_key = fallback_imports(tree)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name.split(".")[0], node.lineno, "import"))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append((node.module.split(".")[0], node.lineno, "from"))

    for module, line, kind in imports:
        rel = str(path)
        fallback = fallback_by_key.get((module, line, kind))
        if fallback:
            warnings.append({
                "code": "MPY_IMPORT_CPYTHON_FALLBACK",
                "path": rel,
                "line": line,
                "module": module,
                "fallback_for": fallback["fallback_for"],
            })
            continue
        if module in CPYTHON_RISKY:
            errors.append({
                "code": "MPY_IMPORT_RISK",
                "path": rel,
                "line": line,
                "module": module,
                "message": f"direct runtime import of CPython-risky module '{module}'",
            })
        elif module not in allowed_roots:
            item = {
                "code": "MPY_IMPORT_UNKNOWN",
                "path": rel,
                "line": line,
                "module": module,
                "message": f"module '{module}' is not in the local app roots or conservative MicroPython allowlist",
            }
            if strict_unknown:
                errors.append(item)
            else:
                warnings.append(item)
    return errors, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check MPOS App imports for MicroPython runtime risks")
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--strict-unknown", action="store_true")
    args = parser.parse_args(argv)

    app_dir = Path(args.app_dir)
    allowed_roots = set(MPY_ALLOWED) | local_roots(app_dir)
    errors: list[dict] = []
    warnings: list[dict] = []
    files = iter_files(app_dir)
    for path in files:
        file_errors, file_warnings = check_file(path, allowed_roots, args.strict_unknown)
        errors.extend(file_errors)
        warnings.extend(file_warnings)
    result = {
        "ok": not errors,
        "app_dir": str(app_dir),
        "files_checked": [str(path) for path in files],
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
