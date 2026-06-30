#!/usr/bin/env python3
"""Check firmware imports against a conservative MicroPython module allowlist."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


MPY_ALLOWED = {
    "sys", "os", "time", "machine", "micropython", "gc", "math", "cmath", "struct", "json",
    "binascii", "collections", "errno", "hashlib", "io", "platform", "random", "re", "select",
    "socket", "ssl", "array", "network", "bluetooth", "framebuf", "uctypes", "cryptolib",
    "deflate", "btree", "vfs", "openamp", "lcd160cr", "neopixel", "esp", "esp32", "espnow",
    "rp2", "mimxrt", "zephyr", "wipy", "stm", "uasyncio", "uarray", "ubinascii",
    "ucollections", "ucryptolib", "uerrno", "uhashlib", "uheapq", "uio", "ujson", "uos",
    "uplatform", "urandom", "ure", "uselect", "usocket", "ussl", "ustruct", "utime", "uzlib",
    "_thread", "threading",
}

CPYTHON_RISKY = {
    "typing",
    "dataclasses",
    "pathlib",
    "logging",
    "asyncio",
    "subprocess",
    "multiprocessing",
    "concurrent",
    "inspect",
    "importlib",
}

CPYTHON_FALLBACKS = {
    "array": {"uarray"},
    "asyncio": {"uasyncio"},
    "binascii": {"ubinascii"},
    "collections": {"ucollections"},
    "errno": {"uerrno"},
    "hashlib": {"uhashlib"},
    "io": {"uio"},
    "json": {"ujson"},
    "os": {"uos"},
    "random": {"urandom"},
    "re": {"ure"},
    "select": {"uselect"},
    "socket": {"usocket"},
    "ssl": {"ussl"},
    "struct": {"ustruct"},
    "time": {"utime"},
    "zlib": {"uzlib"},
}

IMPORT_ERROR_NAMES = {"ImportError", "ModuleNotFoundError"}
MICROPYTHON_GUARD_NAMES = {"_IS_MICROPYTHON", "IS_MICROPYTHON"}


def iter_firmware_files(project_dir: Path, include_lib: bool) -> list[Path]:
    firmware = project_dir / "firmware"
    if not firmware.exists():
        return []
    files = []
    for path in firmware.rglob("*.py"):
        rel = path.relative_to(project_dir).as_posix()
        if not include_lib and rel.startswith("firmware/lib/"):
            continue
        files.append(path)
    return sorted(files)


def local_roots(project_dir: Path) -> set[str]:
    firmware = project_dir / "firmware"
    roots = {"conf", "board", "lib", "drivers", "tasks"}
    if firmware.exists():
        for child in firmware.iterdir():
            if child.suffix == ".py":
                roots.add(child.stem)
            elif child.is_dir():
                roots.add(child.name)
    return roots


def import_records_from_nodes(nodes: list[ast.stmt]) -> list[dict[str, Any]]:
    imports: list[dict[str, Any]] = []
    for parent in nodes:
        for node in ast.walk(parent):
            if isinstance(node, ast.Try):
                # Nested try blocks are handled by the outer ast.walk caller too.
                # Imports inside them are still collected below by walking node.
                pass
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"module": alias.name.split(".")[0], "line": node.lineno, "kind": "import"})
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module:
                    imports.append({"module": node.module.split(".")[0], "line": node.lineno, "kind": "from"})
    return imports


def catches_import_error(handler: ast.ExceptHandler) -> bool:
    exc_type = handler.type
    if exc_type is None:
        return False
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
                alternatives = CPYTHON_FALLBACKS.get(module, set())
                fallback_for = sorted(try_roots & alternatives)
                if fallback_for:
                    fallbacks[(module, item["line"], item["kind"])] = {
                        "fallback_for": fallback_for,
                        "handler": "ImportError",
                    }
    return fallbacks


def _micropython_guard_state(test: ast.AST) -> bool | None:
    """Return True for `if _IS_MICROPYTHON`, False for `if not _IS_MICROPYTHON`."""
    if isinstance(test, ast.Name) and test.id in MICROPYTHON_GUARD_NAMES:
        return True
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        operand = test.operand
        if isinstance(operand, ast.Name) and operand.id in MICROPYTHON_GUARD_NAMES:
            return False
    return None


def cpython_only_guarded_imports(tree: ast.AST) -> dict[tuple[str, int, str], dict[str, Any]]:
    guarded: dict[tuple[str, int, str], dict[str, Any]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        state = _micropython_guard_state(node.test)
        if state is None:
            continue
        cpython_nodes = node.orelse if state else node.body
        for item in import_records_from_nodes(cpython_nodes):
            guarded[(item["module"], item["line"], item["kind"])] = {
                "cpython_only_guard": "_IS_MICROPYTHON",
            }
    return guarded


def imports_from_file(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        return [], [{"code": "PY_SYNTAX_ERROR", "path": str(path), "line": exc.lineno, "message": str(exc)}]
    fallback_by_key = fallback_imports(tree)
    cpython_only_by_key = cpython_only_guarded_imports(tree)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                item = {"module": module, "line": node.lineno, "kind": "import"}
                item.update(fallback_by_key.get((module, node.lineno, "import"), {}))
                item.update(cpython_only_by_key.get((module, node.lineno, "import"), {}))
                imports.append(item)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                module = node.module.split(".")[0]
                item = {"module": module, "line": node.lineno, "kind": "from"}
                item.update(fallback_by_key.get((module, node.lineno, "from"), {}))
                item.update(cpython_only_by_key.get((module, node.lineno, "from"), {}))
                imports.append(item)
    return imports, []


def check_project(project_dir: Path, include_lib: bool) -> dict[str, Any]:
    roots = local_roots(project_dir)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    files_checked = 0
    for path in iter_firmware_files(project_dir, include_lib):
        files_checked += 1
        rel = path.relative_to(project_dir).as_posix()
        imports, parse_errors = imports_from_file(path)
        errors.extend(parse_errors)
        for item in imports:
            module = item["module"]
            if item.get("fallback_for"):
                warnings.append(
                    {
                        "code": "MPY_IMPORT_CPYTHON_FALLBACK",
                        "path": rel,
                        "line": item["line"],
                        "module": module,
                        "fallback_for": item["fallback_for"],
                        "message": (
                            f"module '{module}' is used only as a CPython test fallback after "
                            f"MicroPython import(s): {', '.join(item['fallback_for'])}"
                        ),
                    }
                )
                continue
            if item.get("cpython_only_guard"):
                warnings.append(
                    {
                        "code": "MPY_IMPORT_CPYTHON_ONLY_GUARD",
                        "path": rel,
                        "line": item["line"],
                        "module": module,
                        "guard": item["cpython_only_guard"],
                        "message": (
                            f"module '{module}' is imported only in a CPython branch guarded by "
                            f"{item['cpython_only_guard']}"
                        ),
                    }
                )
                continue
            if module in MPY_ALLOWED or module in roots:
                continue
            record = {
                "code": "MPY_IMPORT_UNSUPPORTED",
                "path": rel,
                "line": item["line"],
                "module": module,
                "message": f"module '{module}' is not in the MicroPython allowlist or project local roots",
            }
            if module in CPYTHON_RISKY:
                errors.append(record)
            else:
                record["code"] = "MPY_IMPORT_REVIEW"
                warnings.append(record)
    return {
        "check": "mpy_imports",
        "project_dir": str(project_dir),
        "files_checked": files_checked,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Check MicroPython firmware imports")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--include-lib", action="store_true", help="Also scan external firmware/lib files")
    args = parser.parse_args()
    result = check_project(Path(args.project_dir), args.include_lib)
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
