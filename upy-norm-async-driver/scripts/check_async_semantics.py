#!/usr/bin/env python3
"""Audit async-driver lifecycle and callback semantics beyond package fidelity."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "build", "dist"}
LIFECYCLE_NAMES = {"__init__", "start", "stop", "close", "aclose", "deinit"}
BLOCKING_NAMES = {"time.sleep", "time.sleep_ms", "utime.sleep", "utime.sleep_ms", "sleep_ms", "sleep_us"}
IRQ_IO_NAMES = {"read", "readinto", "readline", "readfrom", "readfrom_into", "write", "writeto", "write_readinto", "open", "connect"}
CLEANUP_NAMES = {"stop", "close", "aclose", "deinit"}
RUNTIME_MODULES = {"asyncio", "machine", "micropython", "time", "utime"}


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


def code_module_name(code_dir, path):
    relative = path.relative_to(code_dir).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def load_runtime_roles(package, code_files, findings):
    """Load optional roles for retained synchronous compatibility modules."""
    roles = {path: "async_runtime" for path in code_files}
    manifest = package / "async_runtime_roles.json"
    if not manifest.is_file():
        return roles
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add(findings, "ERROR", manifest, manifest, "RUNTIME_ROLES_INVALID", str(exc))
        return roles
    declared = data.get("roles") if isinstance(data, dict) else None
    if not isinstance(declared, dict):
        add(findings, "ERROR", manifest, manifest, "RUNTIME_ROLES_INVALID", "roles must be an object of code-relative paths")
        return roles
    code_dir = package / "code"
    known = {path.relative_to(code_dir).as_posix(): path for path in code_files}
    for relative, role in declared.items():
        if role not in {"async_runtime", "sync_compatibility"}:
            add(findings, "ERROR", manifest, manifest, "RUNTIME_ROLE_UNKNOWN", f"unsupported runtime role for {relative}: {role}")
            continue
        path = known.get(relative)
        if path is None:
            add(findings, "ERROR", manifest, manifest, "RUNTIME_ROLE_PATH", f"role path is not a code/*.py runtime file: {relative}")
            continue
        if path.name == "main.py" and role == "sync_compatibility":
            add(findings, "ERROR", manifest, manifest, "RUNTIME_ROLE_ENTRY", "code/main.py must remain async_runtime")
            continue
        roles[path] = role
    return roles


def imported_internal_modules(code_dir, path, tree, modules):
    current = code_module_name(code_dir, path).split(".")
    targets = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Import):
            candidates = [alias.name for alias in node.names]
        else:
            if node.level:
                base = current[:-1]
                if node.level > 1:
                    base = base[: 1 - node.level]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            candidates = [prefix]
            if prefix:
                candidates.extend(f"{prefix}.{alias.name}" for alias in node.names)
        for candidate in candidates:
            if candidate in modules:
                targets.add(candidate)
    return targets


def compatibility_reachability(package, trees, roles, findings):
    code_dir = package / "code"
    code_trees = {path: tree for path, tree in trees.items() if path.is_relative_to(code_dir) and tree is not None}
    modules = {code_module_name(code_dir, path): path for path in code_trees}
    graph = {
        module: imported_internal_modules(code_dir, path, tree, modules)
        for module, (path, tree) in ((code_module_name(code_dir, path), (path, tree)) for path, tree in code_trees.items())
    }
    compatibility = {code_module_name(code_dir, path) for path, role in roles.items() if role == "sync_compatibility"}
    for module, path in modules.items():
        if roles.get(path) != "async_runtime":
            continue
        pending = list(graph[module])
        visited = set()
        while pending:
            target = pending.pop()
            if target in visited:
                continue
            visited.add(target)
            if target in compatibility:
                add(findings, "ERROR", path, trees[path], "SYNC_COMPAT_REACHABLE", f"async runtime module '{module}' imports sync_compatibility module '{target}'")
                continue
            pending.extend(graph.get(target, ()))


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


def callback_value(call, keyword_name):
    keyword = next((item for item in call.keywords if item.arg == keyword_name), None)
    if keyword is not None:
        return keyword.value
    return call.args[0] if call.args else None


def catches_runtime_error(node):
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, ast.Try):
            for handler in parent.handlers:
                handler_type = handler.type
                if handler_type is None:
                    return True
                if isinstance(handler_type, ast.Name) and handler_type.id == "RuntimeError":
                    return True
                if isinstance(handler_type, ast.Tuple) and any(
                    isinstance(item, ast.Name) and item.id == "RuntimeError" for item in handler_type.elts
                ):
                    return True
        parent = getattr(parent, "parent", None)
    return False


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


def is_public(node):
    return not node.name.startswith("_")


def is_property_definition(node):
    return any(
        isinstance(decorator, ast.Name) and decorator.id == "property"
        or isinstance(decorator, ast.Attribute) and decorator.attr in {"setter", "deleter"}
        for decorator in node.decorator_list
    )


def definition_findings(path, tree, findings):
    scopes = [tree] + [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    for scope in scopes:
        groups = {}
        for node in scope.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_public(node):
                groups.setdefault(node.name, []).append(node)
            if isinstance(node, ast.AsyncFunctionDef) and is_public(node) and (node.args.vararg or node.args.kwarg):
                add(findings, "ERROR", path, node, "PUBLIC_ASYNC_DYNAMIC_SIGNATURE", "public async APIs must declare explicit parameters; *args/**kwargs hides source API fidelity")
        for name, nodes in groups.items():
            if len(nodes) > 1 and not all(is_property_definition(node) for node in nodes):
                for node in nodes[1:]:
                    add(findings, "ERROR", path, node, "DUPLICATE_PUBLIC_DEFINITION", f"public definition '{name}' is overwritten later in the same scope")


def has_timeout_evidence(node):
    return any(
        isinstance(child, ast.Call)
        and call_name(child.func).rsplit(".", 1)[-1] in {"ticks_add", "ticks_diff", "wait_for", "wait_for_ms"}
        for child in ast.walk(node)
    )


def is_long_lived_loop(function, loop):
    name = function.name.lower()
    if any(token in name for token in {"worker", "serve", "listen", "background"}):
        return True
    return any(
        isinstance(child, ast.Attribute) and child.attr.lower() in {"running", "active", "stopped", "closed", "cancelled"}
        for child in ast.walk(loop.test)
    )


def poll_timeout_findings(path, tree, findings):
    for function in ast.walk(tree):
        if not isinstance(function, ast.AsyncFunctionDef):
            continue
        for loop in ast.walk(function):
            if not isinstance(loop, ast.While) or is_long_lived_loop(function, loop):
                continue
            waits = any(isinstance(child, ast.Await) for child in ast.walk(loop))
            polling = isinstance(loop.test, (ast.UnaryOp, ast.Compare))
            if waits and polling and not has_timeout_evidence(function):
                add(findings, "ERROR", path, loop, "ASYNC_POLL_NO_TIMEOUT", "async polling loop awaits but has no deadline, bounded retry, or wait_for timeout")


def runtime_module_findings(path, tree, findings):
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in RUNTIME_MODULES:
                    bound.add(alias.asname or root)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.update(argument.arg for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs))
            if node.args.vararg:
                bound.add(node.args.vararg.arg)
            if node.args.kwarg:
                bound.add(node.args.kwarg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in RUNTIME_MODULES and node.value.id not in bound:
            add(findings, "ERROR", path, node, "RUNTIME_MODULE_UNBOUND", f"'{node.value.id}.{node.attr}' is used without binding the runtime module at module scope")


def registered_callbacks(path, tree, findings):
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "irq":
            value = callback_value(node, "handler")
            if isinstance(value, ast.Lambda):
                add(findings, "ERROR", path, value, "IRQ_ANONYMOUS_CALLBACK", "IRQ callback must be a named pre-bound handler, not an inline lambda")
                if isinstance(value.body, ast.Call):
                    name = callback_name(value.body.func)
                    if name:
                        names.add(name)
            else:
                name = callback_name(value)
                if name:
                    names.add(name)
        elif node.func.attr == "init":
            value = callback_value(node, "callback")
            if isinstance(value, ast.Lambda):
                add(findings, "ERROR", path, value, "IRQ_ANONYMOUS_CALLBACK", "timer callback must be a named pre-bound handler, not an inline lambda")
                if isinstance(value.body, ast.Call):
                    name = callback_name(value.body.func)
                    if name:
                        names.add(name)
            else:
                name = callback_name(value)
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
            if not catches_runtime_error(child):
                add(findings, "ERROR", path, child, "IRQ_SCHEDULE_UNGUARDED", "IRQ schedule() must catch RuntimeError from a full scheduler queue")
            target = callback_name(child.args[0])
            if target:
                scheduled.add(target)
    return scheduled


def audit_tree(path, tree, findings, role):
    if role == "sync_compatibility":
        if any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree)):
            add(findings, "ERROR", path, tree, "SYNC_COMPAT_ASYNC_DEF", "sync_compatibility modules must not define async functions")
        return
    definition_findings(path, tree, findings)
    poll_timeout_findings(path, tree, findings)
    runtime_module_findings(path, tree, findings)
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

    callback_roots = registered_callbacks(path, tree, findings)
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


def parse_tree(path, findings):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        add(findings, "ERROR", path, exc, "SEMANTIC_PARSE", str(exc))
        return None
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node
    return tree


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
    code_files = [path for path in files if path.is_relative_to(package / "code")]
    roles = load_runtime_roles(package, code_files, findings)
    trees = {path: parse_tree(path, findings) for path in files}
    compatibility_reachability(package, trees, roles, findings)
    for path, tree in trees.items():
        if tree is not None:
            audit_tree(path, tree, findings, roles.get(path, "async_runtime"))
    findings.sort(key=lambda item: (str(item.path), item.line, item.code))
    for item in findings:
        try:
            path = item.path.relative_to(package)
        except ValueError:
            path = item.path
        print(f"{item.severity} {path}:{item.line} {item.code}: {item.message}")
    errors = [item for item in findings if item.severity == "ERROR"]
    async_count = sum(1 for path in files if roles.get(path, "async_runtime") == "async_runtime")
    print(f"Audited {async_count} async runtime Python file(s), parsed {len(files)} total; findings={len(findings)}, errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
