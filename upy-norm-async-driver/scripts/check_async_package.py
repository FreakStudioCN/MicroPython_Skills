#!/usr/bin/env python3
"""Validate a generated MicroPython async driver package without hardware."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


EXTERNAL_MODULES = {
    "array", "binascii", "bluetooth", "collections", "errno", "gc", "json",
    "machine", "math", "micropython", "network", "os", "select", "socket",
    "ssl", "struct", "sys", "time", "uasyncio", "ubinascii", "ujson",
    "uos", "uselect", "usocket", "ussl", "utime",
}
SKIP_RUNTIME = {"main.py", "__pycache__"}


@dataclass
class Finding:
    severity: str
    path: Path
    line: int
    code: str
    message: str


def add(findings, severity, path, line, code, message):
    findings.append(Finding(severity, path, line, code, message))


def call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return (base + "." if base else "") + node.attr
    if isinstance(node, ast.Call):
        return call_name(node.func)
    return ""


def read_tree(path, findings):
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            add(findings, "ERROR", path, 1, "UTF8_BOM", "MicroPython source must be UTF-8 without BOM")
        return ast.parse(raw.decode("utf-8-sig", errors="replace"))
    except SyntaxError as exc:
        add(findings, "ERROR", path, exc.lineno or 1, "PYTHON_SYNTAX", exc.msg)
    except OSError as exc:
        add(findings, "ERROR", path, 1, "PYTHON_READ", str(exc))
    return None


def runtime_files(code_dir):
    if not code_dir.is_dir():
        return []
    return sorted(
        path for path in code_dir.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def module_name(code_dir, path):
    relative = path.relative_to(code_dir).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def public_symbols(tree):
    names = set()
    if tree is None:
        return names
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.rsplit(".", 1)[-1])
    return names


def imported_module(node):
    if isinstance(node, ast.Import):
        return [(alias.name, None, node.lineno) for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [(node.module or "", alias.name, node.lineno) for alias in node.names]
    return []


def internal_import_checks(code_dir, trees, findings):
    modules = {module_name(code_dir, path): path for path in trees}
    top_level = {name.split(".", 1)[0] for name in modules if name}
    symbols = {name: public_symbols(tree) for name, tree in ((module_name(code_dir, p), t) for p, t in trees.items())}

    for path, tree in trees.items():
        if tree is None:
            continue
        current = module_name(code_dir, path).split(".")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for name, imported_symbol, line in imported_module(node):
                if isinstance(node, ast.ImportFrom) and node.level:
                    base = current[:-1]
                    if node.level > 1:
                        base = base[: 1 - node.level]
                    target = ".".join(base + ([name] if name else []))
                else:
                    target = name
                root = target.split(".", 1)[0] if target else ""
                if not target or root not in top_level:
                    continue
                if target not in modules:
                    add(findings, "ERROR", path, line, "INTERNAL_IMPORT_MISSING", f"internal module '{target}' is absent from code/")
                    continue
                target_tree = trees[modules[target]]
                meaningful = [item for item in target_tree.body if not isinstance(item, ast.Expr) or not isinstance(item.value, ast.Constant)] if target_tree else []
                if not meaningful:
                    add(findings, "ERROR", path, line, "INTERNAL_MODULE_EMPTY", f"internal module '{target}' is empty or a placeholder")
                if imported_symbol and imported_symbol != "*" and imported_symbol not in symbols[target]:
                    add(findings, "ERROR", path, line, "INTERNAL_SYMBOL_MISSING", f"'{imported_symbol}' is absent from internal module '{target}'")


def source_main(source):
    for relative in (Path("code/main.py"), Path("main.py")):
        candidate = source / relative
        if candidate.is_file():
            return candidate
    return None


def machine_calls(tree):
    if tree is None:
        return set()
    machine_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "machine":
            machine_names.update(alias.asname or alias.name for alias in node.names)
    calls = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        if name.startswith("machine."):
            calls.add(name.rsplit(".", 1)[-1])
        elif name in machine_names:
            calls.add(name)
    return calls


def main_fidelity(package, source, code_dir, trees, findings):
    main_path = code_dir / "main.py"
    if not main_path.is_file():
        add(findings, "ERROR", main_path, 1, "MAIN_MISSING", "code/main.py is required")
        return
    main_tree = trees.get(main_path)
    if main_tree is None:
        return
    calls = [call_name(node.func) for node in ast.walk(main_tree) if isinstance(node, ast.Call)]
    if not any(name == "asyncio.run" or name == "run" for name in calls):
        add(findings, "ERROR", main_path, 1, "MAIN_NO_ASYNC_RUN", "main.py must execute asyncio.run(main())")

    runtime_modules = {module_name(code_dir, p) for p in trees if p != main_path}
    imports_runtime = False
    imported_runtime_names = set()
    for node in ast.walk(main_tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") in runtime_modules:
            imports_runtime = True
            imported_runtime_names.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Import) and any(alias.name in runtime_modules for alias in node.names):
            imports_runtime = True
            imported_runtime_names.update(alias.asname or alias.name.split(".", 1)[0] for alias in node.names)
    if not imports_runtime:
        add(findings, "ERROR", main_path, 1, "MAIN_NO_DRIVER_IMPORT", "main.py does not import an internal runtime driver module")
    elif not any(
        call_name(node.func).split(".", 1)[0] in imported_runtime_names
        for node in ast.walk(main_tree) if isinstance(node, ast.Call)
    ):
        add(findings, "ERROR", main_path, 1, "MAIN_NO_DRIVER_CALL", "main.py imports an internal driver but does not call its API")

    if source is None:
        return
    sync_main = source_main(source)
    if sync_main is None:
        add(findings, "WARN", source, 1, "SOURCE_MAIN_MISSING", "source main.py was not found; fidelity baseline cannot be checked")
        return
    baseline = package / "examples" / "main_sync.py"
    if not baseline.is_file():
        add(findings, "ERROR", baseline, 1, "SYNC_BASELINE_MISSING", "examples/main_sync.py must preserve the source synchronous main.py")
    elif hashlib.sha256(sync_main.read_bytes()).digest() != hashlib.sha256(baseline.read_bytes()).digest():
        add(findings, "ERROR", baseline, 1, "SYNC_BASELINE_CHANGED", "examples/main_sync.py must be byte-identical to source main.py")

    source_tree = read_tree(sync_main, findings)
    required_hardware = machine_calls(source_tree)
    async_hardware = machine_calls(main_tree)
    missing_hardware = required_hardware - async_hardware
    if missing_hardware:
        add(findings, "ERROR", main_path, 1, "MAIN_HARDWARE_FIDELITY", "main.py omits source hardware constructor(s): " + ", ".join(sorted(missing_hardware)))


def package_json_checks(package, code_dir, files, findings):
    metadata = package / "package.json"
    if not metadata.is_file():
        add(findings, "ERROR", metadata, 1, "PACKAGE_JSON_MISSING", "package.json is required")
        return
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add(findings, "ERROR", metadata, 1, "PACKAGE_JSON_INVALID", str(exc))
        return
    if data.get("name") != package.name:
        add(findings, "ERROR", metadata, 1, "PACKAGE_NAME", "package.json name must equal output directory name")
    mapped = set()
    for entry in data.get("urls", []):
        if not isinstance(entry, list) or len(entry) < 2 or not isinstance(entry[1], str):
            add(findings, "ERROR", metadata, 1, "PACKAGE_URL_INVALID", "each urls entry needs a destination path")
            continue
        mapped.add(entry[1].replace("\\", "/"))
        if Path(entry[1]).is_absolute():
            add(findings, "ERROR", metadata, 1, "PACKAGE_URL_ABSOLUTE", "urls destination must be package-relative")
            continue
        if not (package / entry[1]).is_file():
            add(findings, "ERROR", metadata, 1, "PACKAGE_URL_MISSING", f"urls path does not exist: {entry[1]}")
    for path in files:
        relative = path.relative_to(package).as_posix()
        if path.name in SKIP_RUNTIME or path.name.startswith("test_") or path.name.endswith("_test.py"):
            continue
        if relative not in mapped:
            add(findings, "ERROR", metadata, 1, "PACKAGE_URL_UNMAPPED", f"runtime Python file missing from urls: {relative}")


def readme_checks(package, findings):
    readme = package / "README.md"
    if not readme.is_file():
        add(findings, "ERROR", readme, 1, "README_MISSING", "README.md is required")
        return
    text = readme.read_text(encoding="utf-8", errors="replace")
    required = {
        "## API Async Matrix": "README must include an API async-level matrix",
        "## Source Demo to Async Demo Mapping": "README must map source demo steps to async demo steps",
        "| Source sync step |": "README demo mapping table header is missing",
        "## Hardware Acceptance": "README must report link/basic/business acceptance separately",
    }
    for marker, message in required.items():
        if marker not in text:
            add(findings, "ERROR", readme, 1, "README_CONTRACT", message)
    if "sync_adapter_only" in text and "## Sync Adapter Blocking Budget" not in text:
        add(findings, "ERROR", readme, 1, "SYNC_ADAPTER_BUDGET", "sync_adapter_only requires a blocking-budget table")
    if re.search(r"\bUART\b", text) and "## UART Concurrency Contract" not in text:
        add(findings, "WARN", readme, 1, "UART_CONCURRENCY_DOC", "UART package should declare its single-reader or lock strategy")


def main(argv):
    parser = argparse.ArgumentParser(description="Validate async package fidelity and internal runtime dependencies.")
    parser.add_argument("package", help="Generated async package directory")
    parser.add_argument("--source", help="Original synchronous package directory for main.py fidelity checks")
    parser.add_argument("--warn-as-error", action="store_true")
    args = parser.parse_args(argv)

    package = Path(args.package)
    if not package.is_dir():
        print(f"Package directory not found: {package}", file=sys.stderr)
        return 2
    source = Path(args.source) if args.source else None
    if source is not None and not source.is_dir():
        print(f"Source package directory not found: {source}", file=sys.stderr)
        return 2

    findings = []
    code_dir = package / "code"
    files = runtime_files(code_dir)
    if not files:
        add(findings, "ERROR", code_dir, 1, "RUNTIME_EMPTY", "code/ must contain Python runtime files")
    trees = {path: read_tree(path, findings) for path in files}
    internal_import_checks(code_dir, trees, findings)
    package_json_checks(package, code_dir, files, findings)
    main_fidelity(package, source, code_dir, trees, findings)
    readme_checks(package, findings)

    findings.sort(key=lambda item: (str(item.path), item.line, item.code))
    for item in findings:
        try:
            path = item.path.relative_to(package)
        except ValueError:
            path = item.path
        print(f"{item.severity} {path}:{item.line} {item.code}: {item.message}")
    errors = [item for item in findings if item.severity == "ERROR" or (args.warn_as_error and item.severity == "WARN")]
    print(f"Checked {len(files)} runtime Python file(s); findings={len(findings)}, errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
