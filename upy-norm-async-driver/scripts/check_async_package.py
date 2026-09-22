#!/usr/bin/env python3
"""Validate a generated MicroPython async driver package without hardware."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path


EXTERNAL_MODULES = {
    "array", "binascii", "bluetooth", "collections", "errno", "gc", "json",
    "machine", "math", "micropython", "network", "os", "select", "socket",
    "ssl", "struct", "sys", "time", "uasyncio", "ubinascii", "ujson",
    "uos", "uselect", "usocket", "ussl", "utime",
}
SKIP_RUNTIME = {"main.py", "__pycache__"}
SOURCE_BLOCKING_CALLS = {"time.sleep", "time.sleep_ms", "utime.sleep", "utime.sleep_ms", "sleep_ms", "sleep_us"}
SYNC_DELEGATE_ATTRIBUTES = {"_sync", "_source", "_driver", "_base", "_device"}


@dataclass
class Finding:
    severity: str
    path: Path
    line: int
    code: str
    message: str


@dataclass(frozen=True)
class SourceExample:
    """One explicit synchronous-to-async example mapping."""
    source: Path
    sync_baseline: Path
    async_example: Path
    role: str = ""


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


def read_source_tree(path, findings, allow_legacy_syntax, source_context):
    """Parse a source file, optionally translating legacy syntax in memory only."""
    cache = source_context.setdefault("source_tree_cache", {})
    if path in cache:
        return cache[path]
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        tree = ast.parse(text)
        cache[path] = tree
        return tree
    except SyntaxError as exc:
        source_context["legacy_syntax"] = True
        if not allow_legacy_syntax:
            add(findings, "ERROR", path, exc.lineno or 1, "SOURCE_LEGACY_SYNTAX", "source syntax requires --allow-source-legacy-syntax with a README declaration")
            cache[path] = None
            return None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", PendingDeprecationWarning)
                from lib2to3.refactor import RefactoringTool, get_fixers_from_package

                tool = RefactoringTool(get_fixers_from_package("lib2to3.fixes"), explicit=True)
                translated = str(tool.refactor_string(text, str(path)))
            tree = ast.parse(translated)
        except (ImportError, SyntaxError, ValueError, TypeError) as legacy_exc:
            source_context["legacy_unparseable"] = True
            add(findings, "WARN", path, exc.lineno or 1, "SOURCE_LEGACY_UNPARSEABLE", f"legacy source could not be parsed in memory: {legacy_exc}")
            cache[path] = None
            return None
        source_context["legacy_translated"] = True
        add(findings, "WARN", path, exc.lineno or 1, "SOURCE_LEGACY_SYNTAX", "source parsed through an in-memory legacy syntax translation; source fidelity is partial")
        cache[path] = tree
        return tree
    except OSError as exc:
        add(findings, "ERROR", path, 1, "PYTHON_READ", str(exc))
        cache[path] = None
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


def source_preflight(source, findings, allow_source_main_missing, allow_source_metadata_missing, examples=None):
    """Return whether a deliberate source-incomplete conversion is in progress."""
    incomplete = False
    has_examples = examples is not None
    sync_main = source_main(source)
    if has_examples:
        source_examples_present = bool(examples)
    else:
        source_examples_present = sync_main is not None
    if not source_examples_present:
        incomplete = True
        severity = "WARN" if allow_source_main_missing else "ERROR"
        add(
            findings,
            severity,
            source,
            1,
            "SOURCE_EXAMPLE_MISSING" if has_examples else "SOURCE_MAIN_MISSING",
            "the source-example manifest declares no usable source example" if has_examples else "source main.py is required for a formal fidelity conversion; use --allow-source-main-missing only for an explicitly declared library-only, partial, or user-specified demo",
        )

    metadata = source / "package.json"
    if not metadata.is_file():
        incomplete = True
        severity = "WARN" if allow_source_metadata_missing else "ERROR"
        add(
            findings,
            severity,
            metadata,
            1,
            "SOURCE_PACKAGE_JSON_MISSING",
            "source package.json is required to preserve package metadata and deployment boundaries; use --allow-source-metadata-missing only with an explicit README declaration",
        )
    else:
        try:
            json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            add(findings, "ERROR", metadata, 1, "SOURCE_PACKAGE_JSON_INVALID", str(exc))
    return incomplete


def safe_relative_path(value):
    """Return a safe package-relative path, or None for an escaping path."""
    if not isinstance(value, str) or not value:
        return None
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        return None
    return path


def source_example_manifest(package, source, findings):
    """Read and validate optional explicit multi-example fidelity mappings."""
    manifest_path = package / "async_source_examples.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", str(exc))
        return []
    if not isinstance(data, dict) or not isinstance(data.get("examples"), list) or not data["examples"]:
        add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", "manifest needs a non-empty examples array")
        return []
    source_package = safe_relative_path(data.get("source_package"))
    if source_package is None:
        add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", "source_package must be a safe relative package path")
    elif source is not None and source_package.name != source.name:
        add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_SOURCE_MISMATCH", "source_package must name the package passed through --source")

    default_source = safe_relative_path(data.get("default_example"))
    if default_source is None:
        add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", "default_example must be a safe relative source path")
    examples = []
    sources = set()
    baselines = set()
    roles = set()
    for index, entry in enumerate(data["examples"], 1):
        if not isinstance(entry, dict):
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", f"examples[{index}] must be an object")
            continue
        source_path = safe_relative_path(entry.get("source"))
        baseline_path = safe_relative_path(entry.get("sync_baseline"))
        async_path = safe_relative_path(entry.get("async_example"))
        if source_path is None or baseline_path is None or async_path is None:
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", f"examples[{index}] has an invalid relative path")
            continue
        if source_path.suffix != ".py":
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", f"examples[{index}].source must be a Python file")
            continue
        if not baseline_path.parts or baseline_path.parts[0] != "examples" or not baseline_path.stem.endswith("_sync"):
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", f"examples[{index}].sync_baseline must be an examples/*_sync.py file")
            continue
        if async_path != Path("code/main.py") and (
            not async_path.parts
            or async_path.parts[0] != "examples"
            or not async_path.stem.endswith("_async")
            or async_path.suffix != ".py"
        ):
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", f"examples[{index}].async_example must be code/main.py or examples/*_async.py")
            continue
        if source_path in sources or baseline_path in baselines:
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", f"examples[{index}] duplicates a source or synchronous baseline")
            continue
        role = entry.get("role", "")
        if role is not None and not isinstance(role, str):
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", f"examples[{index}].role must be text")
            continue
        if len(data["examples"]) > 1 and not role:
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_ROLE_MISSING", f"examples[{index}] needs a role in a multi-example package")
            continue
        if role and role in roles:
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_ROLE_DUPLICATE", f"examples[{index}] duplicates role '{role}'")
            continue
        sources.add(source_path)
        baselines.add(baseline_path)
        if role:
            roles.add(role)
        examples.append(SourceExample(source_path, baseline_path, async_path, role or ""))

    inventory = data.get("source_example_inventory")
    if not isinstance(inventory, list) or not inventory:
        add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_INVENTORY_MISSING", "manifest needs a non-empty source_example_inventory array")
    else:
        inventory_paths = set()
        mapped_inventory = set()
        for index, entry in enumerate(inventory, 1):
            if not isinstance(entry, dict):
                add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_INVENTORY_INVALID", f"source_example_inventory[{index}] must be an object")
                continue
            path = safe_relative_path(entry.get("source"))
            disposition = entry.get("disposition")
            reason = entry.get("reason", "")
            if path is None or path.suffix != ".py" or disposition not in {"mapped", "excluded"}:
                add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_INVENTORY_INVALID", f"source_example_inventory[{index}] needs a Python source and mapped/excluded disposition")
                continue
            if path in inventory_paths:
                add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_INVENTORY_INVALID", f"source_example_inventory[{index}] duplicates source '{path}'")
                continue
            if disposition == "excluded" and not isinstance(reason, str):
                add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_INVENTORY_INVALID", f"source_example_inventory[{index}].reason must be text")
                continue
            if disposition == "excluded" and not reason.strip():
                add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_EXCLUSION_UNEXPLAINED", f"source_example_inventory[{index}] needs a reason for exclusion")
                continue
            inventory_paths.add(path)
            if disposition == "mapped":
                mapped_inventory.add(path)
        if mapped_inventory != sources:
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_INVENTORY_MISMATCH", "inventory mapped examples must exactly match manifest examples")

    if default_source is not None:
        default = next((item for item in examples if item.source == default_source), None)
        if default is None or default.async_example != Path("code/main.py"):
            add(findings, "ERROR", manifest_path, 1, "SOURCE_EXAMPLE_MANIFEST_INVALID", "default_example must map to code/main.py")
    for item in examples:
        source_file = source / item.source if source is not None else None
        baseline = package / item.sync_baseline
        async_file = package / item.async_example
        if source_file is not None and not source_file.is_file():
            add(findings, "ERROR", source_file, 1, "SOURCE_EXAMPLE_MISSING", f"declared source example is absent: {item.source}")
        if not baseline.is_file():
            add(findings, "ERROR", baseline, 1, "SYNC_EXAMPLE_BASELINE_MISSING", "declared synchronous baseline is absent")
        elif source_file is not None and source_file.is_file() and source_file.read_bytes() != baseline.read_bytes():
            add(findings, "ERROR", baseline, 1, "SYNC_EXAMPLE_BASELINE_CHANGED", "synchronous baseline must be byte-identical to its declared source example")
        if not async_file.is_file():
            add(findings, "ERROR", async_file, 1, "ASYNC_EXAMPLE_MISSING", "declared async example is absent")
        else:
            read_tree(async_file, findings)
    return examples


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


def source_dependency_checks(source, code_dir, output_trees, findings, sync_example, async_example, async_tree, allow_legacy_syntax, source_context):
    """Check one declared source example's local-import closure and API fidelity."""
    if not sync_example.is_file() or not async_example.is_file():
        return
    source_dir = source_code_dir(source)
    source_files = runtime_files(source_dir)
    source_trees = {
        path: read_source_tree(path, findings, allow_legacy_syntax, source_context)
        for path in source_files
    }
    source_modules = {module_name(source_dir, path): path for path in source_trees}
    output_modules = {module_name(code_dir, path): path for path in output_trees}
    output_symbols = {
        name: public_symbols(tree)
        for name, tree in ((module_name(code_dir, path), tree) for path, tree in output_trees.items())
    }
    example_module = module_name(source_dir, sync_example)
    if example_module not in source_modules:
        return

    pending = [example_module]
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
                    add(findings, "ERROR", path, node.lineno, "SOURCE_DEPENDENCY_MISSING", f"source local module '{target}' reachable from {sync_example.name} is absent from output code/")
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

    source_direct, source_methods = local_driver_calls(source_trees[source_modules[example_module]], set(source_modules))
    output_example = output_trees.get(async_example) or async_tree
    output_direct, output_methods = local_driver_calls(output_example, set(output_modules))
    output_declared_methods = constructed_driver_methods(output_example, output_modules, output_trees, code_dir)
    missing_direct = {name for name in source_direct if name not in output_direct and name + "Async" not in output_direct}
    if missing_direct:
        add(findings, "ERROR", async_example, 1, "EXAMPLE_DRIVER_CONSTRUCTOR_FIDELITY", "async example omits source driver constructor(s): " + ", ".join(sorted(missing_direct)))
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
        add(findings, "ERROR", async_example, 1, "EXAMPLE_DRIVER_API_FIDELITY", "async example omits source driver API call(s): " + ", ".join(sorted(missing_methods)))


def source_methods_with_blocking_waits(source_trees):
    """Return source method names that directly or transitively call blocking waits."""
    functions = {}
    for tree in source_trees.values():
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.setdefault(node.name, []).append(node)
    blocked = {
        name
        for name, nodes in functions.items()
        if any(
            call_name(call.func) in SOURCE_BLOCKING_CALLS
            for node in nodes
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
        )
    }
    changed = True
    while changed:
        changed = False
        for name, nodes in functions.items():
            if name in blocked:
                continue
            if any(
                call_name(call.func).rsplit(".", 1)[-1] in blocked
                for node in nodes
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
            ):
                blocked.add(name)
                changed = True
    return blocked


def is_sync_delegate(call):
    if not isinstance(call.func, ast.Attribute):
        return False
    receiver = call.func.value
    if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id == "super":
        return True
    if isinstance(receiver, ast.Attribute) and isinstance(receiver.value, ast.Name) and receiver.value.id == "self":
        return receiver.attr in SYNC_DELEGATE_ATTRIBUTES
    return False


def async_delegation_checks(source, code_dir, output_trees, findings, allow_legacy_syntax, source_context):
    """Reject async facades that delegate to source methods with blocking waits."""
    source_trees = {
        path: read_source_tree(path, findings, allow_legacy_syntax, source_context)
        for path in runtime_files(source_code_dir(source))
    }
    blocked = source_methods_with_blocking_waits(source_trees)
    if not blocked:
        return
    for path, tree in output_trees.items():
        if path == code_dir / "main.py" or tree is None:
            continue
        for method in ast.walk(tree):
            if not isinstance(method, ast.AsyncFunctionDef):
                continue
            for call in ast.walk(method):
                if not isinstance(call, ast.Call) or not is_sync_delegate(call):
                    continue
                target = call.func.attr
                if target in blocked:
                    add(
                        findings,
                        "ERROR",
                        path,
                        call.lineno,
                        "ASYNC_DELEGATES_BLOCKING_SOURCE",
                        f"async method '{method.name}' delegates to source '{target}()', which contains a blocking wait; split the wait into cooperative steps",
                    )


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
    cleanup_names = {"aclose", "close", "deinit", "stop"}
    for node in ast.walk(main_node):
        if not isinstance(node, ast.Try) or not node.finalbody:
            continue
        for child in ast.walk(ast.Module(body=node.finalbody, type_ignores=[])):
            if isinstance(child, ast.Call) and call_name(child.func).rsplit(".", 1)[-1] in cleanup_names:
                return True
    return False


def async_entry_checks(async_example, tree, findings):
    """Validate a standalone mapped async demo, including cancellation cleanup."""
    main_node = next((node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "main"), None)
    if main_node is None:
        add(findings, "ERROR", async_example, 1, "ASYNC_EXAMPLE_MAIN_MISSING", "async example must define async def main()")
        return
    if not any(is_asyncio_run_main(node) for node in ast.walk(tree)):
        add(findings, "ERROR", async_example, 1, "ASYNC_EXAMPLE_NO_ASYNC_RUN", "async example must execute asyncio.run(main())")
    if not has_cleanup_finally(main_node):
        add(findings, "ERROR", async_example, main_node.lineno, "ASYNC_EXAMPLE_NO_CLEANUP_FINALLY", "async main() must use try/finally with a real cleanup call")


def async_example_checks(async_example, code_dir, trees, findings):
    """Require every declared async example to exercise an internal driver."""
    tree = trees.get(async_example) or read_tree(async_example, findings)
    if tree is None:
        return
    runtime_modules = {module_name(code_dir, path) for path in trees if path.relative_to(code_dir) != Path("main.py")}
    imported_runtime_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") in runtime_modules:
            imported_runtime_names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in runtime_modules:
                    imported_runtime_names.add(alias.asname or alias.name.split(".", 1)[0])
    if not imported_runtime_names:
        add(findings, "ERROR", async_example, 1, "ASYNC_EXAMPLE_NO_DRIVER_IMPORT", "async example does not import an internal runtime driver module")
        return
    if not any(
        call_name(node.func).split(".", 1)[0] in imported_runtime_names
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    ):
        add(findings, "ERROR", async_example, 1, "ASYNC_EXAMPLE_NO_DRIVER_CALL", "async example imports an internal driver but does not call its API")


def example_fidelity(package, source, code_dir, trees, findings, example, allow_legacy_syntax, source_context):
    """Validate the baseline, hardware construction, and behavior of one mapping."""
    sync_example = source / example.source
    async_example = package / example.async_example
    if not sync_example.is_file() or not async_example.is_file():
        return
    source_tree = read_source_tree(sync_example, findings, allow_legacy_syntax, source_context)
    async_tree = trees.get(async_example) or read_tree(async_example, findings)
    if async_tree is None:
        return
    if async_example != code_dir / "main.py":
        async_entry_checks(async_example, async_tree, findings)
    async_example_checks(async_example, code_dir, trees, findings)
    required_hardware = machine_calls(source_tree)
    async_hardware = machine_calls(async_tree)
    missing_hardware = required_hardware - async_hardware
    if missing_hardware:
        add(findings, "ERROR", async_example, 1, "EXAMPLE_HARDWARE_FIDELITY", "async example omits source hardware constructor(s): " + ", ".join(sorted(missing_hardware)))
    source_dependency_checks(
        source,
        code_dir,
        trees,
        findings,
        sync_example,
        async_example,
        async_tree,
        allow_legacy_syntax,
        source_context,
    )


def main_fidelity(package, source, code_dir, trees, findings, examples=None, allow_legacy_syntax=False, source_context=None):
    source_context = source_context if source_context is not None else {}
    main_path = code_dir / "main.py"
    if not main_path.is_file():
        add(findings, "ERROR", main_path, 1, "MAIN_MISSING", "code/main.py is required")
        return
    main_tree = trees.get(main_path)
    if main_tree is None:
        return
    async_entry_checks(main_path, main_tree, findings)

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
    if examples is None:
        sync_main = source_main(source)
        if sync_main is None:
            return
        baseline = package / "examples" / "main_sync.py"
        if not baseline.is_file():
            add(findings, "ERROR", baseline, 1, "SYNC_BASELINE_MISSING", "examples/main_sync.py must preserve the source synchronous main.py")
        elif hashlib.sha256(sync_main.read_bytes()).digest() != hashlib.sha256(baseline.read_bytes()).digest():
            add(findings, "ERROR", baseline, 1, "SYNC_BASELINE_CHANGED", "examples/main_sync.py must be byte-identical to source main.py")
        example_fidelity(
            package,
            source,
            code_dir,
            trees,
            findings,
            SourceExample(sync_main.relative_to(source), Path("examples/main_sync.py"), Path("code/main.py")),
            allow_legacy_syntax,
            source_context,
        )
        return
    for example in examples:
        example_fidelity(package, source, code_dir, trees, findings, example, allow_legacy_syntax, source_context)


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


def runtime_uses_uart(trees):
    """Return whether generated runtime code declares or accesses machine.UART."""
    machine_names = {"machine"}
    for tree in trees.values():
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "machine":
                        machine_names.add(alias.asname or "machine")
            if isinstance(node, ast.ImportFrom) and node.module == "machine":
                if any(alias.name == "UART" for alias in node.names):
                    return True
    for tree in trees.values():
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "UART"
                and isinstance(node.value, ast.Name)
                and node.value.id in machine_names
            ):
                return True
    return False


def readme_checks(package, trees, findings, source_incomplete, source_legacy_syntax):
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
    if source_incomplete and "## Source Incomplete Declaration" not in text:
        add(
            findings,
            "ERROR",
            readme,
            1,
            "SOURCE_INCOMPLETE_UNDECLARED",
            "an allowed incomplete source requires a Source Incomplete Declaration with the replacement demo/metadata evidence",
        )
    if source_legacy_syntax and "## Source Legacy Syntax Declaration" not in text:
        add(
            findings,
            "ERROR",
            readme,
            1,
            "SOURCE_LEGACY_UNDECLARED",
            "an allowed legacy source syntax path requires a Source Legacy Syntax Declaration and partial-fidelity scope",
        )
    if "sync_adapter_only" in text and "## Sync Adapter Blocking Budget" not in text:
        add(findings, "ERROR", readme, 1, "SYNC_ADAPTER_BUDGET", "sync_adapter_only requires a blocking-budget table")
    if runtime_uses_uart(trees) and "## UART Concurrency Contract" not in text:
        add(findings, "WARN", readme, 1, "UART_CONCURRENCY_DOC", "UART package should declare its single-reader or lock strategy")


def main(argv):
    parser = argparse.ArgumentParser(description="Validate async package fidelity and internal runtime dependencies.")
    parser.add_argument("package", help="Generated async package directory")
    parser.add_argument("--source", help="Original synchronous package directory for fidelity and source-completeness checks")
    parser.add_argument("--allow-source-main-missing", action="store_true", help="Allow a source without main.py only for an explicitly declared library-only, partial, or user-specified demo")
    parser.add_argument("--allow-source-metadata-missing", action="store_true", help="Allow a source without package.json only with an explicit README declaration")
    parser.add_argument("--allow-source-legacy-syntax", action="store_true", help="Allow read-only legacy source syntax only with a README declaration; reports partial source fidelity")
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
    source_context = {}
    examples = source_example_manifest(package, source, findings)
    source_incomplete = False
    if source is not None:
        source_incomplete = source_preflight(
            source,
            findings,
            args.allow_source_main_missing,
            args.allow_source_metadata_missing,
            examples,
        )
    code_dir = package / "code"
    files = runtime_files(code_dir)
    if not files:
        add(findings, "ERROR", code_dir, 1, "RUNTIME_EMPTY", "code/ must contain Python runtime files")
    trees = {path: read_tree(path, findings) for path in files}
    internal_import_checks(code_dir, trees, findings)
    package_json_checks(package, code_dir, files, findings)
    main_fidelity(
        package,
        source,
        code_dir,
        trees,
        findings,
        examples,
        args.allow_source_legacy_syntax,
        source_context,
    )
    if source is not None:
        async_delegation_checks(
            source,
            code_dir,
            trees,
            findings,
            args.allow_source_legacy_syntax,
            source_context,
        )
    readme_checks(
        package,
        trees,
        findings,
        source_incomplete and (args.allow_source_main_missing or args.allow_source_metadata_missing),
        source_context.get("legacy_syntax", False),
    )

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
