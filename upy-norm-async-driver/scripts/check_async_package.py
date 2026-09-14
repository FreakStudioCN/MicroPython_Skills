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
                meaningful = [
                    item for item in target_tree.body
                    if not isinstance(item, ast.Pass)
                    and not (isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant))
                ] if target_tree else []
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


def source_code_dir(source):
    code_dir = source / "code"
    return code_dir if code_dir.is_dir() else source


def resolve_import_target(current_module, node):
    """Return the module path named by an import, before local resolution."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    if node.level:
        base = current_module.split(".")[:-1]
        if node.level > 1:
            base = base[: 1 - node.level]
        if node.module:
            base.extend(node.module.split("."))
        return [".".join(part for part in base if part)]
    return [node.module or ""]


def output_module_for(source_module, output_modules):
    """Map a source module to the usual same-name or top-level async name."""
    candidates = [source_module]
    parts = source_module.split(".")
    if parts and parts[0]:
        candidates.append(".".join([parts[0] + "_async"] + parts[1:]))
    return next((candidate for candidate in candidates if candidate in output_modules), None)


def output_symbol_for(source_symbol, symbols):
    """Allow the conventional public class/function Foo -> FooAsync rename."""
    candidates = [source_symbol]
    if source_symbol and not source_symbol.startswith("_"):
        candidates.append(source_symbol + "Async")
    return next((candidate for candidate in candidates if candidate in symbols), None)


def local_driver_calls(tree, local_modules):
    """Infer direct source-demo calls made through locally imported drivers."""
    if tree is None:
        return set(), set()
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") in local_modules:
            imported_names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in local_modules:
                    imported_names.add(alias.asname or alias.name.split(".", 1)[0])

    instances = set()
    direct_calls = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        if name in imported_names:
            direct_calls.add(name)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(getattr(node, "value", None), ast.Call):
            value = node.value
            if isinstance(value.func, ast.Name) and value.func.id in imported_names:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                instances.update(target.id for target in targets if isinstance(target, ast.Name))

    methods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id in instances:
                methods.add(node.func.attr)
    return direct_calls, methods


def constructed_driver_methods(main_tree, output_modules, output_trees, code_dir):
    """Return methods actually defined by locally imported classes constructed in main.py."""
    if main_tree is None:
        return set()
    imported = {}
    for node in ast.walk(main_tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") in output_modules:
            for alias in node.names:
                imported[alias.asname or alias.name] = (node.module, alias.name)

    constructed = set()
    for node in ast.walk(main_tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(getattr(node, "value", None), ast.Call):
            continue
        constructor = node.value.func
        if isinstance(constructor, ast.Name) and constructor.id in imported:
            constructed.add(imported[constructor.id])

    methods = set()
    for module, class_name in constructed:
        module_path = output_modules.get(module)
        tree = output_trees.get(module_path)
        if tree is None:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                methods.update(item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return methods


def source_dependency_checks(source, package, code_dir, output_trees, findings):
    """Check the source demo's reachable local-import closure against output code/."""
    sync_main = source_main(source)
    if sync_main is None:
        return
    source_dir = source_code_dir(source)
    source_files = runtime_files(source_dir)
    source_trees = {path: read_tree(path, findings) for path in source_files}
    source_modules = {module_name(source_dir, path): path for path in source_trees}
    output_modules = {module_name(code_dir, path): path for path in output_trees}
    output_symbols = {
        name: public_symbols(tree)
        for name, tree in ((module_name(code_dir, path), tree) for path, tree in output_trees.items())
    }
    main_module = module_name(source_dir, sync_main)
    if main_module not in source_modules:
        return

    pending = [main_module]
    visited = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        path = source_modules.get(current)
        tree = source_trees.get(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for target in resolve_import_target(current, node):
                if not target or target not in source_modules:
                    continue
                mapped = output_module_for(target, output_modules)
                if mapped is None:
                    add(findings, "ERROR", path, node.lineno, "SOURCE_DEPENDENCY_MISSING", f"source local module '{target}' reachable from main.py is absent from output code/")
                    continue
                pending.append(target)
                # MicroPython package imports need their parent initializers as well.
                parts = target.split(".")
                for index in range(1, len(parts)):
                    parent = ".".join(parts[:index])
                    if parent in source_modules:
                        pending.append(parent)
                if not isinstance(node, ast.ImportFrom):
                    continue
                for alias in node.names:
                    child = f"{target}.{alias.name}"
                    if child in source_modules:
                        pending.append(child)
                        continue
                    if alias.name == "*":
                        continue
                    if output_symbol_for(alias.name, output_symbols[mapped]) is None:
                        add(findings, "ERROR", path, node.lineno, "SOURCE_SYMBOL_MISSING", f"source import '{target}.{alias.name}' is absent from output module '{mapped}'")

        # Attribute-style module references are not covered by ImportFrom checks.
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in source_modules:
                        aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name
            elif isinstance(node, ast.ImportFrom):
                targets = resolve_import_target(current, node)
                target = targets[0] if targets else ""
                for alias in node.names:
                    child = f"{target}.{alias.name}"
                    if child in source_modules:
                        aliases[alias.asname or alias.name] = child
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                continue
            target = aliases.get(node.value.id)
            mapped = output_module_for(target, output_modules) if target else None
            if mapped and node.attr not in output_symbols[mapped]:
                add(findings, "ERROR", path, node.lineno, "SOURCE_ATTRIBUTE_MISSING", f"source attribute '{target}.{node.attr}' is absent from output module '{mapped}'")

    source_direct, source_methods = local_driver_calls(source_trees[source_modules[main_module]], set(source_modules))
    output_main = output_trees.get(code_dir / "main.py")
    output_direct, output_methods = local_driver_calls(output_main, set(output_modules))
    output_declared_methods = constructed_driver_methods(output_main, output_modules, output_trees, code_dir)
    missing_direct = {name for name in source_direct if name not in output_direct and name + "Async" not in output_direct}
    if missing_direct:
        add(findings, "ERROR", code_dir / "main.py", 1, "MAIN_DRIVER_CONSTRUCTOR_FIDELITY", "main.py omits source driver constructor(s): " + ", ".join(sorted(missing_direct)))
    allowed_method_renames = {"deinit": "aclose", "close": "aclose"}
    missing_methods = {
        name for name in source_methods
        if name not in output_methods
        and name + "_async" not in output_methods
        and allowed_method_renames.get(name) not in output_methods
        or (name + "_async" in output_methods and name + "_async" not in output_declared_methods)
        or (name in output_methods and name not in output_declared_methods)
        or (allowed_method_renames.get(name) in output_methods and allowed_method_renames.get(name) not in output_declared_methods)
    }
    if missing_methods:
        add(findings, "ERROR", code_dir / "main.py", 1, "MAIN_DRIVER_API_FIDELITY", "main.py omits source driver API call(s): " + ", ".join(sorted(missing_methods)))


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
    source_dependency_checks(source, package, code_dir, trees, findings)


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
