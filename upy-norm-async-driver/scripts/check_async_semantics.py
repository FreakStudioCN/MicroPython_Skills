#!/usr/bin/env python3
"""Audit async-driver lifecycle and callback semantics beyond package fidelity."""

from __future__ import annotations

import argparse
import ast
import os
import sys
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "build", "dist"}
LIFECYCLE_NAMES = {"__init__", "start", "stop", "close", "aclose", "deinit"}
BLOCKING_NAMES = {"time.sleep", "time.sleep_ms", "utime.sleep", "utime.sleep_ms", "sleep_ms", "sleep_us"}
IRQ_IO_NAMES = {"read", "readinto", "readline", "readfrom", "readfrom_into", "write", "writeto", "write_readinto", "open", "connect"}
CLEANUP_NAMES = {"stop", "close", "aclose", "deinit"}


@dataclass
class Finding:
    severity: str
    path: Path
    line: int
    code: str
    message: str


def add(findings, severity, path, node, code, message):
    findings.append(Finding(severity, path, getattr(node, "lineno", 1), code, message))


def call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return call_name(node.func)
    return ""


def iter_py_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def audit_files(package):
    files = list(iter_py_files(package / "code"))
    examples = package / "examples"
    if examples.is_dir():
        files.extend(sorted(examples.rglob("*_async.py")))
    return files


def is_asyncio_run_main(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
        and node.func.attr == "run"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Call)
        and isinstance(node.args[0].func, ast.Name)
        and node.args[0].func.id == "main"
    )


def has_cleanup_finally(main_node):
    for node in ast.walk(main_node):
        if not isinstance(node, ast.Try) or not node.finalbody:
            continue
        for child in ast.walk(ast.Module(body=node.finalbody, type_ignores=[])):
            if isinstance(child, ast.Call) and call_name(child.func).rsplit(".", 1)[-1] in CLEANUP_NAMES:
                return True
    return False


def callback_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def is_irq_io(name):
    return name.rsplit(".", 1)[-1] in IRQ_IO_NAMES


def is_user_callback(name):
    last = name.rsplit(".", 1)[-1].lower()
    return "callback" in last or last.startswith("on_")


def function_nodes(tree):
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.setdefault(node.name, []).append(node)
    return result


def registered_callbacks(tree):
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "irq":
            keyword = next((item for item in node.keywords if item.arg == "handler"), None)
            if keyword:
                name = callback_name(keyword.value)
                if name:
                    names.add(name)
        elif node.func.attr == "init":
            keyword = next((item for item in node.keywords if item.arg == "callback"), None)
            if keyword:
                name = callback_name(keyword.value)
                if name:
                    names.add(name)
    return names


def callback_findings(path, node, findings, label):
    scheduled = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = call_name(child.func)
        if name == "print" or is_irq_io(name) or is_user_callback(name):
            add(findings, "ERROR", path, child, "IRQ_CALLBACK_WORK", f"{label} performs print, I/O, or a user callback")
        if name in {"micropython.schedule", "schedule"} and child.args:
            target = callback_name(child.args[0])
            if target:
                scheduled.add(target)
    return scheduled


def audit_tree(path, tree, findings):
    functions = function_nodes(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                add(findings, "ERROR", path, child, "FUNCTION_LOCAL_IMPORT", "runtime imports must be module-level unless an explicit memory exception is documented")
            if isinstance(child, ast.Call):
                name = call_name(child.func)
                if node.name in LIFECYCLE_NAMES and name in BLOCKING_NAMES:
                    add(findings, "ERROR", path, child, "LIFECYCLE_BLOCKING_CALL", f"{node.name}() contains blocking {name}()")
                if name in {"asyncio.create_task", "create_task"} and isinstance(getattr(child, "parent", None), ast.Expr):
                    add(findings, "ERROR", path, child, "UNSTORED_TASK", "device task must be stored for cancellation and shutdown")

    callback_roots = registered_callbacks(tree)
    visited = set()
    pending = list(callback_roots)
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for node in functions.get(name, []):
            pending.extend(callback_findings(path, node, findings, "IRQ/Timer callback"))

    is_example = "examples" in path.parts and path.name.endswith("_async.py")
    if path.name == "main.py" or is_example:
        main_node = next((item for item in tree.body if isinstance(item, ast.AsyncFunctionDef) and item.name == "main"), None)
        if main_node is None:
            add(findings, "ERROR", path, tree, "ASYNC_ENTRY_MAIN_MISSING", "async entry must define async def main()")
        else:
            if not any(is_asyncio_run_main(item) for item in ast.walk(tree)):
                add(findings, "ERROR", path, main_node, "ASYNC_ENTRY_NO_RUN", "async entry must execute asyncio.run(main())")
            if not has_cleanup_finally(main_node):
                add(findings, "ERROR", path, main_node, "ASYNC_ENTRY_NO_FINALLY", "async entry must clean up in try/finally")


def parse_and_audit(path, findings):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        add(findings, "ERROR", path, exc, "SEMANTIC_PARSE", str(exc))
        return
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node
    audit_tree(path, tree, findings)


def main(argv):
    parser = argparse.ArgumentParser(description="Audit MicroPython async lifecycle, callback, and import semantics.")
    parser.add_argument("package", help="Generated async package directory")
    args = parser.parse_args(argv)
    package = Path(args.package)
    if not package.is_dir():
        print(f"Package directory not found: {package}", file=sys.stderr)
        return 2
    files = audit_files(package)
    findings = []
    if not files:
        add(findings, "ERROR", package, package, "SEMANTIC_RUNTIME_EMPTY", "package has no code/**/*.py files")
    for path in files:
        parse_and_audit(path, findings)
    findings.sort(key=lambda item: (str(item.path), item.line, item.code))
    for item in findings:
        try:
            path = item.path.relative_to(package)
        except ValueError:
            path = item.path
        print(f"{item.severity} {path}:{item.line} {item.code}: {item.message}")
    errors = [item for item in findings if item.severity == "ERROR"]
    print(f"Audited {len(files)} async Python file(s); findings={len(findings)}, errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
