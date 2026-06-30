#!/usr/bin/env python3
"""Static semantic checks for generated MicroPython business code."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


PLACEHOLDER_TOKENS = ("base64_placeholder", "placeholder", "TODO: implement")
SYNC_HTTP_METHODS = {"http_post", "http_get", "request", "post", "get", "put", "delete"}
BLOCKING_ASYNC_CALLS = {
    "sleep",
    "sleep_ms",
    "read_samples",
    "readinto",
    "read_audio",
    "record",
    "play_samples",
    "play_audio",
    "write_samples",
    "connect",
    "scan",
}
BLOCKING_ASYNC_FULL_CALLS = {
    "time.sleep",
    "time.sleep_ms",
    "utime.sleep",
    "utime.sleep_ms",
}
ASYNC_SLEEP_CALLS = {
    "asyncio.sleep",
    "asyncio.sleep_ms",
    "uasyncio.sleep",
    "uasyncio.sleep_ms",
}
STATE_RESET_NAMES = {"state", "last_state", "last_trigger", "trigger_event", "mode"}
STATE_RESET_VALUES = {"idle", "IDLE", "none", "None", "0"}
RESOURCE_TASK_MARKERS = ("create_inmp441", "create_max98357", "machine.I2S", "I2S(")
VIRTUAL_TIMER_ONLY_MARKERS = ("pico", "rp2", "rp2040", "rp2350", "zephyr")
LOGGER_METHODS = {"debug", "info", "warning", "error", "critical", "exception"}
TIME_MARKERS = ("ticks_ms", "ticks_diff", "localtime", "asctime", "timestamp", "chrono", "uptime")
TIME_VALUE_NAMES = {"asctime", "timestamp", "chrono", "uptime", "uptime_ms", "ts", "now_ms"}
TIME_CALL_NAMES = {"ticks_ms", "ticks_diff", "localtime"}


def project_py_files(project_dir: Path) -> list[Path]:
    roots = [
        project_dir / "firmware" / "main.py",
        project_dir / "firmware" / "drivers",
        project_dir / "firmware" / "tasks",
    ]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(root.rglob("*.py"))
    return sorted(set(files))


def rel_path(project_dir: Path, path: Path) -> str:
    return path.relative_to(project_dir).as_posix()


def parse_file(path: Path) -> tuple[ast.Module | None, list[dict[str, Any]]]:
    try:
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path)), []
    except SyntaxError as exc:
        return None, [{"code": "PY_SYNTAX_ERROR", "path": str(path), "line": exc.lineno, "message": str(exc)}]


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def is_negative_one(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and node.operand.value == 1
    )


def full_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = full_call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def literal_name(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        return repr(node.value).strip("'\"")
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def assigned_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.extend(item.id for item in target.elts if isinstance(item, ast.Name))
    return names


def constant_string(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def is_blocking_method_name(value: str) -> bool:
    return value in BLOCKING_ASYNC_CALLS or value in SYNC_HTTP_METHODS


def dynamic_blocking_lookup_name(node: ast.AST) -> str:
    if not isinstance(node, ast.Call):
        return ""
    func_name = full_call_name(node.func)
    if func_name == "getattr" and len(node.args) >= 2:
        method_name = constant_string(node.args[1])
        return method_name if is_blocking_method_name(method_name) else ""
    if func_name.endswith(".__getattribute__") and node.args:
        method_name = constant_string(node.args[0])
        return method_name if is_blocking_method_name(method_name) else ""
    return ""


def contains_blocking_call(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = call_name(child.func)
        full_name = full_call_name(child.func)
        if name in BLOCKING_ASYNC_CALLS or full_name in BLOCKING_ASYNC_FULL_CALLS:
            return True
        if dynamic_blocking_lookup_name(child):
            return True
    return False


def collect_blocking_wrappers(tree: ast.Module) -> set[str]:
    wrappers: set[str] = set()
    for func in [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]:
        if contains_blocking_call(func):
            wrappers.add(func.name)
    return wrappers


def node_contains_name(node: ast.AST, name: str, *, include_self: bool = True) -> bool:
    nodes = ast.walk(node) if include_self else (child for child in ast.walk(node) if child is not node)
    return any(isinstance(child, ast.Name) and child.id == name for child in nodes)


def check_placeholders(project_dir: Path, path: Path, text: str) -> list[dict[str, Any]]:
    errors = []
    rel = rel_path(project_dir, path)
    for lineno, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        for token in PLACEHOLDER_TOKENS:
            if token.lower() in lowered:
                errors.append(
                    {
                        "code": "SEMANTIC_PLACEHOLDER_IN_RUNTIME",
                        "path": rel,
                        "line": lineno,
                        "token": token,
                        "message": "Generated runtime code must not contain placeholder payloads or TODO implementations",
                    }
                )
    return errors


def check_async_sync_calls(project_dir: Path, path: Path, tree: ast.Module) -> list[dict[str, Any]]:
    errors = []
    rel = rel_path(project_dir, path)
    blocking_wrappers = collect_blocking_wrappers(tree)
    for func in [node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]:
        dynamic_aliases: dict[str, str] = {}
        reported_dynamic_lookup_nodes: set[int] = set()
        for node in ast.walk(func):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                if isinstance(node.value, ast.Call):
                    method_name = dynamic_blocking_lookup_name(node.value)
                    if method_name:
                        for alias in assigned_names(node):
                            dynamic_aliases[alias] = method_name
                        reported_dynamic_lookup_nodes.add(id(node.value))
                        errors.append(
                            {
                                "code": "SEMANTIC_ASYNC_DYNAMIC_BLOCKING_LOOKUP",
                                "path": rel,
                                "line": node.lineno,
                                "function": func.name,
                                "method": method_name,
                                "message": "Async code must not hide blocking driver/network calls behind getattr or __getattribute__",
                            }
                        )
                if isinstance(node.value, ast.Lambda) and contains_blocking_call(node.value):
                    for alias in assigned_names(node):
                        dynamic_aliases[alias] = "lambda"
                    errors.append(
                        {
                            "code": "SEMANTIC_ASYNC_BLOCKING_LAMBDA",
                            "path": rel,
                            "line": node.lineno,
                            "function": func.name,
                            "message": "Async code must not hide blocking driver/network calls behind a lambda or callable alias",
                        }
                    )
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node.func)
            full_name = full_call_name(node.func)
            dynamic_method = dynamic_blocking_lookup_name(node)
            if dynamic_method and id(node) not in reported_dynamic_lookup_nodes:
                errors.append(
                    {
                        "code": "SEMANTIC_ASYNC_DYNAMIC_BLOCKING_LOOKUP",
                        "path": rel,
                        "line": node.lineno,
                        "function": func.name,
                        "method": dynamic_method,
                        "message": "Async code must not hide blocking driver/network calls behind getattr or __getattribute__",
                    }
                )
            if isinstance(node.func, ast.Name) and node.func.id in dynamic_aliases:
                errors.append(
                    {
                        "code": "SEMANTIC_ASYNC_DYNAMIC_BLOCKING_CALL",
                        "path": rel,
                        "line": node.lineno,
                        "function": func.name,
                        "call": node.func.id,
                        "method": dynamic_aliases[node.func.id],
                        "message": "Async code calls a blocking driver/network method through a dynamic alias",
                    }
                )
            if isinstance(node.func, ast.Name) and node.func.id in blocking_wrappers:
                errors.append(
                    {
                        "code": "SEMANTIC_ASYNC_BLOCKING_WRAPPER",
                        "path": rel,
                        "line": node.lineno,
                        "function": func.name,
                        "call": node.func.id,
                        "message": "Async code calls a local synchronous wrapper around blocking driver/time/network I/O",
                    }
                )
            if name in SYNC_HTTP_METHODS and ("http" in name or "urequests" in full_name or full_name.endswith((".post", ".get"))):
                errors.append(
                    {
                        "code": "SEMANTIC_ASYNC_SYNC_IO",
                        "path": rel,
                        "line": node.lineno,
                        "function": func.name,
                        "call": full_name,
                        "message": "Async task calls a likely synchronous network operation; generate a cooperative state machine or mark partial",
                    }
                )
            if isinstance(getattr(node, "parent", None), ast.Await) and full_name in ASYNC_SLEEP_CALLS:
                continue
            if name in BLOCKING_ASYNC_CALLS or full_name in BLOCKING_ASYNC_FULL_CALLS:
                errors.append(
                    {
                        "code": "SEMANTIC_ASYNC_BLOCKING_IO",
                        "path": rel,
                        "line": node.lineno,
                        "function": func.name,
                        "call": full_name,
                        "message": "Async task calls a likely blocking driver/time operation without await or an async adapter",
                    }
                )
    return errors


def attach_parents(tree: ast.Module) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)


def check_state_reset(project_dir: Path, path: Path, tree: ast.Module) -> list[dict[str, Any]]:
    errors = []
    rel = rel_path(project_dir, path)
    for func in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.endswith("_tick")]:
        for stmt in func.body[:8]:
            if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                continue
            value = literal_name(stmt.value)
            for name in assigned_names(stmt):
                if name in STATE_RESET_NAMES and value in STATE_RESET_VALUES:
                    errors.append(
                        {
                            "code": "SEMANTIC_STATE_RESETS_EACH_TICK",
                            "path": rel,
                            "line": stmt.lineno,
                            "function": func.name,
                            "name": name,
                            "message": "Tick/state-machine functions must persist state across calls instead of resetting it each tick",
                        }
                    )
    return errors


def check_discarded_sensor_data(project_dir: Path, path: Path, tree: ast.Module) -> list[dict[str, Any]]:
    errors = []
    rel = rel_path(project_dir, path)
    for func in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        body = list(ast.walk(func))
        discarded_names = set()
        for node in body:
            if isinstance(node, ast.Assign) and any(name == "_" for name in assigned_names(node)):
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Name):
                        discarded_names.add(child.id)
        for node in body:
            if not isinstance(node, ast.Assign):
                continue
            names = assigned_names(node)
            if not names:
                continue
            if not isinstance(node.value, ast.Call):
                continue
            call = full_call_name(node.value.func)
            if not any(marker in call for marker in ("read_samples", "record", "read_audio")):
                continue
            for name in names:
                if name in discarded_names or not any(node_contains_name(other, name, include_self=False) for other in body if other is not node):
                    errors.append(
                        {
                            "code": "SEMANTIC_DATA_READ_UNUSED",
                            "path": rel,
                            "line": node.lineno,
                            "function": func.name,
                            "name": name,
                            "message": "Captured device data is not used by later payload/output logic",
                        }
                    )
    return errors


def check_unused_generated_params(project_dir: Path, path: Path, tree: ast.Module) -> list[dict[str, Any]]:
    warnings = []
    rel = rel_path(project_dir, path)
    for func in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        args = list(func.args.args) + list(func.args.kwonlyargs)
        for arg in args:
            name = arg.arg
            if name in {"self", "cls"}:
                continue
            if name.endswith(("_ms", "_s", "_interval", "_interval_ms", "_timeout", "_timeout_ms", "_max")):
                if not any(node_contains_name(stmt, name, include_self=False) for stmt in func.body):
                    warnings.append(
                        {
                            "code": "SEMANTIC_PARAMETER_UNUSED",
                            "path": rel,
                            "line": arg.lineno,
                            "function": func.name,
                            "name": name,
                            "message": "Generated behavior parameter is not used inside the task",
                        }
                    )
    return warnings


def load_manifest(project_dir: Path, manifest_path: str) -> dict[str, Any]:
    path = Path(manifest_path) if manifest_path else project_dir / "project-manifest.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return {}


def manifest_contains_marker(manifest: dict[str, Any], markers: tuple[str, ...]) -> bool:
    def contains_marker(value: Any) -> bool:
        if isinstance(value, str):
            lowered = value.lower()
            return any(marker in lowered for marker in markers)
        if isinstance(value, dict):
            return any(contains_marker(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_marker(item) for item in value)
        return False

    return contains_marker(manifest.get("mcu")) or contains_marker(manifest.get("board")) or contains_marker(manifest.get("target"))


def target_allows_virtual_timer(manifest: dict[str, Any]) -> bool:
    return manifest_contains_marker(manifest, VIRTUAL_TIMER_ONLY_MARKERS)


def manifest_devices(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    devices = manifest.get("devices") if isinstance(manifest, dict) else []
    return [item for item in devices if isinstance(item, dict)] if isinstance(devices, list) else []


def manifest_has_i2c_device(manifest: dict[str, Any]) -> bool:
    for device in manifest_devices(manifest):
        text = json.dumps(device, ensure_ascii=False).lower()
        if "i2c" in text:
            return True
    for item in manifest.get("pinout") or []:
        if not isinstance(item, dict):
            continue
        type_text = str(item.get("type") or "").lower()
        bus_text = str(item.get("bus") or "").lower()
        if type_text.startswith("i2c") or bus_text.startswith("i2c"):
            return True
    return False


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def pin_call_gpio(node: ast.AST | None) -> int | None:
    if not isinstance(node, ast.Call) or call_name(node.func) != "Pin" or not node.args:
        return None
    if isinstance(node.args[0], ast.Constant):
        return parse_int(node.args[0].value)
    return None


def i2c_call_pins(node: ast.Call) -> dict[str, int]:
    pins: dict[str, int] = {}
    for kw in node.keywords:
        if kw.arg not in {"scl", "sda"}:
            continue
        gpio = pin_call_gpio(kw.value)
        if gpio is not None:
            pins[kw.arg] = gpio
    return pins


def manifest_non_i2c_gpio_owners(manifest: dict[str, Any]) -> dict[int, list[str]]:
    owners: dict[int, list[str]] = {}
    for item in manifest.get("pinout") or []:
        if not isinstance(item, dict):
            continue
        gpio = parse_int(item.get("gpio"))
        if gpio is None:
            continue
        type_text = str(item.get("type") or "").lower()
        bus_text = str(item.get("bus") or "").lower()
        if type_text.startswith("i2c") or bus_text.startswith("i2c"):
            continue
        if type_text.startswith(("power", "gnd")) or type_text in {"nc", "none"}:
            continue
        owner = "{}.{}".format(item.get("device") or "device", item.get("pin_name") or item.get("type") or "pin")
        owners.setdefault(gpio, []).append(owner)
    return owners


def check_i2c_assembly_contract(project_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    main_py = project_dir / "firmware" / "main.py"
    if not main_py.exists():
        return []
    tree, parse_errors = parse_file(main_py)
    if tree is None:
        return parse_errors
    errors: list[dict[str, Any]] = []
    has_i2c_device = manifest_has_i2c_device(manifest)
    non_i2c_owners = manifest_non_i2c_gpio_owners(manifest)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node.func) != "I2C":
            continue
        pins = i2c_call_pins(node)
        if not has_i2c_device:
            errors.append(
                {
                    "code": "SEMANTIC_UNDECLARED_I2C_SCAN",
                    "path": "firmware/main.py",
                    "line": node.lineno,
                    "pins": pins,
                    "message": "main.py creates/scans I2C even though manifest has no I2C device; do not generate default I2C scan unless hardware facts require it",
                }
            )
        conflicts = {
            role: {"gpio": gpio, "owners": non_i2c_owners[gpio]}
            for role, gpio in pins.items()
            if gpio in non_i2c_owners
        }
        if conflicts:
            errors.append(
                {
                    "code": "SEMANTIC_I2C_PIN_CONFLICT",
                    "path": "firmware/main.py",
                    "line": node.lineno,
                    "conflicts": conflicts,
                    "message": "main.py I2C pins overlap non-I2C peripheral pins from manifest pinout; resource_plan/main assembly must not reuse GPIO across incompatible buses",
                }
            )
    return errors


def check_resource_plan(project_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    main_py = project_dir / "firmware" / "main.py"
    if not main_py.exists():
        return []
    text = main_py.read_text(encoding="utf-8-sig")
    if not all(marker in text for marker in ("create_inmp441", "create_max98357")):
        return []
    generate = manifest.get("generate") if isinstance(manifest, dict) else {}
    resource_plan = generate.get("resource_plan") if isinstance(generate, dict) else None
    if isinstance(resource_plan, dict) and ("i2s" in resource_plan or "i2s0" in resource_plan):
        return []
    return [
        {
            "code": "SEMANTIC_SHARED_I2S_WITHOUT_RESOURCE_PLAN",
            "path": "firmware/main.py",
            "line": 1,
            "message": "INMP441 and MAX98357 share I2S-class resources; generate.resource_plan must describe ownership/half-duplex strategy",
        }
    ]


def scheduler_methods(project_dir: Path) -> set[str]:
    path = project_dir / "firmware" / "lib" / "scheduler" / "timer_sched.py"
    if not path.exists():
        return set()
    tree, _errors = parse_file(path)
    if tree is None:
        return set()
    methods: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Scheduler":
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.add(item.name)
    return methods


def scheduler_timer_default_is_negative_one(project_dir: Path) -> bool:
    path = project_dir / "firmware" / "lib" / "scheduler" / "timer_sched.py"
    if not path.exists():
        return False
    tree, _errors = parse_file(path)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Scheduler":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "__init__":
                continue
            defaults = list(item.args.defaults)
            args = list(item.args.args)
            if not defaults:
                continue
            default_by_arg = dict(zip([arg.arg for arg in args[-len(defaults):]], defaults))
            if is_negative_one(default_by_arg.get("timer_id")):
                return True
    return False


def collect_scheduler_vars(tree: ast.Module) -> set[str]:
    vars_: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if isinstance(value, ast.Call) and call_name(value.func) == "Scheduler":
                for target in targets:
                    if isinstance(target, ast.Name):
                        vars_.add(target.id)
        elif isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.context_expr, ast.Call) and call_name(item.context_expr.func) == "Scheduler":
                    if isinstance(item.optional_vars, ast.Name):
                        vars_.add(item.optional_vars.id)
    return vars_


def scheduler_timer_arg(node: ast.Call) -> ast.AST | None:
    if node.args:
        return node.args[0]
    for kw in node.keywords:
        if kw.arg == "timer_id":
            return kw.value
    return None


def scheduler_error_arg(node: ast.Call) -> ast.AST | None:
    for kw in node.keywords:
        if kw.arg == "error_cb":
            return kw.value
    if len(node.args) >= 3:
        return node.args[2]
    return None


def is_none_literal(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def uses_rotating_logger(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_text = ast.unparse(node.func) if hasattr(ast, "unparse") else call_name(node.func)
        call_text = ast.unparse(node) if hasattr(ast, "unparse") else func_text
        if "install_rotating" in func_text or "install_rotating" in call_text:
            return True
    return False


def try_logs_exception(handler: ast.ExceptHandler) -> bool:
    has_print_exception = False
    has_logger_exception = False
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        full = full_call_name(node.func)
        if name == "print_exception" or full.endswith(".print_exception"):
            has_print_exception = True
        if name == "exception" or full.endswith(".exception"):
            has_logger_exception = True
    return has_print_exception and has_logger_exception


def has_startup_exception_guard(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if try_logs_exception(handler):
                return True
    return False


def has_time_expression(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            continue
        if isinstance(child, ast.Name) and child.id.lower() in TIME_VALUE_NAMES:
            return True
        if isinstance(child, ast.Attribute) and child.attr.lower() in TIME_VALUE_NAMES | TIME_CALL_NAMES:
            return True
        if isinstance(child, ast.Call):
            name = call_name(child.func).lower()
            if name in TIME_CALL_NAMES:
                return True
    return False


def check_rotating_logger_timestamp_contract(project_dir: Path, tree: ast.Module) -> list[dict[str, Any]]:
    rel = "firmware/main.py"
    timed_names: set[str] = set()
    errors: list[dict[str, Any]] = []
    uses_rotating = uses_rotating_logger(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and has_time_expression(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    timed_names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and node.value is not None and has_time_expression(node.value):
            if isinstance(node.target, ast.Name):
                timed_names.add(node.target.id)
    if not uses_rotating:
        return []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LOGGER_METHODS:
            continue
        uses_timed_name = any(isinstance(arg, ast.Name) and arg.id in timed_names for arg in node.args)
        if uses_timed_name or has_time_expression(node):
            continue
        errors.append(
            {
                "code": "LOGGER_ROTATING_TIMESTAMP_MISSING",
                "path": rel,
                "line": node.lineno,
                "message": "main.py installs rotating logger; generated logger calls must mix timestamp/uptime into message text instead of modifying scaffold logger source",
            }
        )
    return errors


def check_startup_exception_logging_contract(tree: ast.Module) -> list[dict[str, Any]]:
    if not uses_rotating_logger(tree) or has_startup_exception_guard(tree):
        return []
    return [
        {
            "code": "LOGGER_STARTUP_FATAL_GUARD_MISSING",
            "path": "firmware/main.py",
            "line": 1,
            "message": "main.py installs rotating logger but lacks a top-level startup fatal guard that prints and writes exceptions to the device log",
        }
    ]


def check_timer_scheduler_contract(project_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    main_path = project_dir / "firmware" / "main.py"
    if not main_path.exists():
        return []
    rel = "firmware/main.py"
    text = main_path.read_text(encoding="utf-8-sig")
    tree, parse_errors = parse_file(main_path)
    if tree is None:
        return parse_errors
    errors: list[dict[str, Any]] = []
    if not target_allows_virtual_timer(manifest):
        scheduler_default_bad = scheduler_timer_default_is_negative_one(project_dir)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if call_name(node.func) != "Timer":
                continue
            first = node.args[0] if node.args else None
            for kw in node.keywords:
                if kw.arg == "id":
                    first = kw.value
            if is_negative_one(first):
                errors.append(
                    {
                        "code": "SCHEDULER_TIMER_INVALID_FOR_PORT",
                        "path": rel,
                        "line": node.lineno,
                        "message": "Only RP2/Pico and Zephyr targets should use virtual Timer(-1); keep scaffold scheduler internals unchanged and pass an explicit valid hardware timer id at the entrypoint",
                    }
                )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or call_name(node.func) != "Scheduler":
                continue
            timer_arg = scheduler_timer_arg(node)
            if is_negative_one(timer_arg) or (timer_arg is None and scheduler_default_bad):
                errors.append(
                    {
                        "code": "SCHEDULER_TIMER_INVALID_FOR_PORT",
                        "path": rel,
                        "line": node.lineno,
                        "message": "Only RP2/Pico and Zephyr targets should instantiate Scheduler with timer_id=-1 or rely on a Scheduler default that maps to Timer(-1); pass an explicit valid hardware timer id in main.py",
                    }
                )
    errors.extend(check_rotating_logger_timestamp_contract(project_dir, tree))
    errors.extend(check_startup_exception_logging_contract(tree))
    methods = scheduler_methods(project_dir)
    if "Scheduler" not in text or not methods:
        return errors
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node.func) != "Scheduler":
            continue
        error_arg = scheduler_error_arg(node)
        if error_arg is None or is_none_literal(error_arg):
            errors.append(
                {
                    "code": "SCHEDULER_ERROR_CALLBACK_MISSING",
                    "path": rel,
                    "line": node.lineno,
                    "message": "main.py must pass Scheduler(error_cb=...) so task exceptions are printed and written to the rotating device log",
                }
            )
    scheduler_vars = collect_scheduler_vars(tree)
    inline_scheduler_calls = {"add_task", "register", "start", "run"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        value = node.func.value
        is_scheduler_call = False
        if isinstance(value, ast.Name) and value.id in scheduler_vars:
            is_scheduler_call = True
        elif isinstance(value, ast.Call) and call_name(value.func) == "Scheduler":
            is_scheduler_call = True
        if not is_scheduler_call or method not in inline_scheduler_calls:
            continue
        if method not in methods:
            errors.append(
                {
                    "code": "SCHEDULER_API_METHOD_MISSING",
                    "path": rel,
                    "line": node.lineno,
                    "method": method,
                    "available_methods": sorted(methods),
                    "message": "main.py must call methods implemented by firmware/lib/scheduler/timer_sched.py Scheduler",
                }
            )
    return errors


def check_project(project_dir: Path, manifest_path: str = "") -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    files_checked = 0
    for path in project_py_files(project_dir):
        files_checked += 1
        text = path.read_text(encoding="utf-8-sig")
        errors.extend(check_placeholders(project_dir, path, text))
        tree, parse_errors = parse_file(path)
        errors.extend(parse_errors)
        if tree is None:
            continue
        attach_parents(tree)
        errors.extend(check_async_sync_calls(project_dir, path, tree))
        errors.extend(check_state_reset(project_dir, path, tree))
        errors.extend(check_discarded_sensor_data(project_dir, path, tree))
        warnings.extend(check_unused_generated_params(project_dir, path, tree))
    manifest = load_manifest(project_dir, manifest_path)
    errors.extend(check_resource_plan(project_dir, manifest))
    errors.extend(check_i2c_assembly_contract(project_dir, manifest))
    errors.extend(check_timer_scheduler_contract(project_dir, manifest))
    return {
        "check": "generated_semantics",
        "project_dir": str(project_dir),
        "files_checked": files_checked,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Check generated MicroPython business semantics")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--manifest", default="", help="Optional project-manifest.json path")
    args = parser.parse_args()
    result = check_project(Path(args.project_dir), args.manifest)
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
