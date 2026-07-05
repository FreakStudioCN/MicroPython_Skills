#!/usr/bin/env python3
"""Validate upy-gen-driver-plugin phase_complete artifacts."""

from __future__ import annotations

import argparse
import ast
import builtins
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


PHASE = "upy-gen-driver-plugin"
DOMAIN_PHASE = "gen-driver"
PHASE_COMPLETE_FILE = "phase_complete.upy_gen_driver_plugin.json"
STATE_FILE = "session_state.upy_gen_driver_plugin.json"
RESULTS = {"success", "partial", "failed"}
FILE_STATUSES = {"created", "updated", "unchanged", "skipped", "error"}
HASHED_FILE_STATUSES = {"created", "updated", "unchanged"}
FILE_ROLES = {
    "source",
    "extracted_text",
    "mapping",
    "understanding",
    "debug_driver",
    "production_driver",
    "test",
    "wiring",
    "verify_log",
    "manifest",
    "state",
    "phase_complete",
    "artifact",
}
PERMISSION_OPERATIONS = {
    "file_read",
    "file_write",
    "script_run",
    "device_scan",
    "device_run",
    "network_fetch",
    "manifest_update",
}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
BUILTIN_NAMES = set(dir(builtins)) | {"__name__"}
I2C_RW_METHODS = {"readfrom", "readfrom_into", "readfrom_mem", "readfrom_mem_into", "writeto", "writeto_mem"}
CHECKPOINT_NAMES = {
    "started",
    "input_collected",
    "source_preprocessed",
    "understanding_written",
    "debug_driver_written",
    "hardware_verify_ready",
    "hardware_verify_passed",
    "production_driver_written",
    "normalized",
    "standalone_assets_written",
    "standalone_test_passed",
    "manifest_updated",
    "phase_completed",
    "cancelled",
    "verification_exhausted",
}
VERIFICATION_MODES = {"hardware", "mock", "skipped", "none"}
PHASE_COMPLETE_SAMPLE_RE = re.compile(r"^phase_complete\.upy_gen_driver_plugin\.[A-Za-z0-9_.-]+\.json$")


def is_relative_path(value: str) -> bool:
    if not value or os.path.isabs(value):
        return False
    parts = Path(value).parts
    return ".." not in parts and not (len(value) > 1 and value[1] == ":")


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("phase_complete must be a JSON object")
    return data


def validate_input_filename(path: Path | None, errors: list[str]) -> None:
    if path is None:
        return
    name = path.name
    if name == PHASE_COMPLETE_FILE or PHASE_COMPLETE_SAMPLE_RE.fullmatch(name):
        return
    if name.startswith("phase_complete."):
        errors.append(
            f"input filename must be {PHASE_COMPLETE_FILE}; sample fixtures may use phase_complete.upy_gen_driver_plugin.<case>.json"
        )


def validate_phase_scoped_id(path: str, value: Any, session_id: Any, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{path} must be a non-empty string")
        return
    prefix = f"{PHASE}:"
    if not value.startswith(prefix):
        errors.append(f"{path} must start with {prefix}")
        return
    parts = value.split(":")
    if len(parts) >= 2 and isinstance(session_id, str) and parts[1] != session_id:
        errors.append(f"{path} session id must match envelope session_id")


def validate_nested_idempotency_keys(value: Any, path: str, session_id: Any, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key == "idempotency_key":
                validate_phase_scoped_id(child_path, child, session_id, errors)
            else:
                validate_nested_idempotency_keys(child, child_path, session_id, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_nested_idempotency_keys(child, f"{path}[{index}]", session_id, errors)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_artifact_path(root: Path, relative_path: str) -> Path:
    return root / Path(relative_path.replace("/", os.sep))


def checkpoint_name(checkpoint: dict[str, Any]) -> str:
    checkpoint_id = checkpoint.get("checkpoint_id")
    if isinstance(checkpoint_id, str) and ":" in checkpoint_id:
        return checkpoint_id.rsplit(":", 1)[-1]
    if isinstance(checkpoint_id, str):
        return checkpoint_id
    return ""


def validate_checkpoint_id(checkpoint: dict[str, Any], session_id: Any, errors: list[str]) -> None:
    checkpoint_id = checkpoint.get("checkpoint_id")
    if not isinstance(checkpoint_id, str):
        return
    parts = checkpoint_id.split(":")
    if len(parts) != 3 or parts[0] != PHASE:
        errors.append(f"payload.checkpoint.checkpoint_id must use format {PHASE}:<session_id>:<checkpoint_name>")
        return
    if parts[1] != session_id:
        errors.append("payload.checkpoint.checkpoint_id session id must match envelope session_id")
    if parts[2] not in CHECKPOINT_NAMES:
        errors.append("payload.checkpoint.checkpoint_id checkpoint name is not recognized")


def text_contains_unverified_production_label(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.lower()
    return "production driver" in normalized and "unverified" in normalized


def validate_artifacts(artifacts: Any, result: Any, hardware_verified: Any, errors: list[str]) -> None:
    if isinstance(artifacts, dict):
        errors.append("payload.artifacts must be an array; use a file_list artifact object, not a file_list map")
        return
    if not isinstance(artifacts, list):
        errors.append("payload.artifacts must be an array")
        return
    file_lists = [item for item in artifacts if isinstance(item, dict) and item.get("type") == "file_list"]
    if not file_lists:
        errors.append("payload.artifacts must include a file_list artifact")
        return
    for artifact_index, artifact in enumerate(file_lists):
        files = artifact.get("files")
        items = artifact.get("items")
        has_files = isinstance(files, list) and bool(files)
        has_items = isinstance(items, list) and bool(items)
        if not has_files and not has_items:
            errors.append(f"payload.artifacts[{artifact_index}] file_list must include non-empty files or items")
        entries: list[Any] = []
        if isinstance(files, list):
            entries.extend(files)
        if isinstance(items, list):
            entries.extend(items)
        for entry_index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            labels = [entry.get(field) for field in ("label", "role", "description", "title", "name", "display_role")]
            if any(text_contains_unverified_production_label(label) for label in labels):
                errors.append(
                    f"payload.artifacts[{artifact_index}] file_list entry {entry_index} must label unverified drivers as driver artifacts, not production drivers"
                )
            if result != "success" or hardware_verified is not True:
                if any(isinstance(label, str) and "production driver" in label.lower() for label in labels):
                    errors.append(
                        f"payload.artifacts[{artifact_index}] file_list entry {entry_index} must not use production driver labels before verification"
                    )


def validate_permission_idempotency_keys(permissions: Any, has_production_driver: bool, errors: list[str]) -> None:
    if not isinstance(permissions, list):
        return
    for index, item in enumerate(permissions):
        if not isinstance(item, dict):
            continue
        key = item.get("idempotency_key")
        if not isinstance(key, str):
            continue
        if "write_production_driver" in key and not has_production_driver:
            errors.append(
                f"permissions[{index}].idempotency_key must use write_driver_artifact for unverified driver artifacts"
            )


def names_from_target(node: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            names.update(names_from_target(item))
    return names


def names_from_import(node: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.add((alias.asname or alias.name.split(".", 1)[0]))
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            names.add(alias.asname or alias.name)
    return names


def collect_module_defs(tree: ast.Module) -> set[str]:
    defs: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.add(stmt.name)
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            defs.update(names_from_import(stmt))
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                defs.update(names_from_target(target))
        elif isinstance(stmt, ast.AnnAssign):
            defs.update(names_from_target(stmt.target))
        elif isinstance(stmt, ast.AugAssign):
            defs.update(names_from_target(stmt.target))
    return defs


class ModuleLoadVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.loads: list[tuple[str, int]] = []

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loads.append((node.id, node.lineno))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for item in list(node.decorator_list) + list(node.args.defaults) + list(node.args.kw_defaults):
            if item is not None:
                self.visit(item)
        if node.returns is not None:
            self.visit(node.returns)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for item in list(node.decorator_list) + list(node.bases):
            self.visit(item)
        for keyword in node.keywords:
            self.visit(keyword)
        for stmt in node.body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.FunctionDef, ast.AsyncFunctionDef)):
                self.visit(stmt)


class FunctionDefsVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.defs: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.defs.add(node.name)
        for arg in list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs):
            self.defs.add(arg.arg)
        if node.args.vararg:
            self.defs.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.defs.add(node.args.kwarg.arg)
        for stmt in node.body:
            self.visit(stmt)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defs.add(node.name)

    def visit_Import(self, node: ast.Import) -> None:
        self.defs.update(names_from_import(node))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.defs.update(names_from_import(node))

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.defs.add(node.id)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.defs.add(node.name)
        for stmt in node.body:
            self.visit(stmt)


class FunctionLoadVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.loads: list[tuple[str, int]] = []

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loads.append((node.id, node.lineno))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return


def collect_function_defs(node: ast.FunctionDef) -> set[str]:
    visitor = FunctionDefsVisitor()
    visitor.visit(node)
    return visitor.defs


def collect_function_loads(node: ast.FunctionDef) -> list[tuple[str, int]]:
    visitor = FunctionLoadVisitor()
    for stmt in node.body:
        visitor.visit(stmt)
    return visitor.loads


def method_arity(node: ast.FunctionDef) -> tuple[int, int | None]:
    positional = list(node.args.posonlyargs) + list(node.args.args)
    if positional and positional[0].arg in {"self", "cls"}:
        positional = positional[1:]
    max_args: int | None = None if node.args.vararg else len(positional)
    min_args = max(0, len(positional) - len(node.args.defaults))
    return min_args, max_args


class DriverStaticVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.i2c_methods_used: set[str] = set()
        self.hasattr_checks: set[str] = set()
        self.non_integer_consts: list[int] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in I2C_RW_METHODS:
            self.i2c_methods_used.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "hasattr" and len(node.args) >= 2:
            value = node.args[1]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                self.hasattr_checks.add(value.value)
        if isinstance(node.func, ast.Name) and node.func.id == "const" and node.args:
            value = node.args[0]
            if isinstance(value, ast.Constant) and not isinstance(value.value, int):
                self.non_integer_consts.append(node.lineno)
        self.generic_visit(node)


class SelfCallVisitor(ast.NodeVisitor):
    def __init__(self, method_specs: dict[str, tuple[int, int | None]], role: str, errors: list[str]) -> None:
        self.method_specs = method_specs
        self.role = role
        self.errors = errors

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
            and func.attr in self.method_specs
        ):
            min_args, max_args = self.method_specs[func.attr]
            arg_count = len(node.args)
            if arg_count < min_args or (max_args is not None and arg_count > max_args):
                max_text = "*" if max_args is None else str(max_args)
                self.errors.append(
                    f"{self.role} method call arity mismatch at line {node.lineno}: "
                    f"self.{func.attr}() accepts {min_args}-{max_text} positional args, got {arg_count}"
                )
        self.generic_visit(node)


def validate_python_static(text: str, path: Path, role: str, errors: list[str]) -> None:
    try:
        compile(text, str(path), "exec")
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        errors.append(f"{role} has invalid Python syntax at line {exc.lineno}: {exc.msg}")
        return

    module_defs = collect_module_defs(tree)
    allowed_globals = module_defs | BUILTIN_NAMES
    module_loads = ModuleLoadVisitor()
    module_loads.visit(tree)
    for name, lineno in module_loads.loads:
        if name not in allowed_globals:
            errors.append(f"{role} undefined name at line {lineno}: {name}")

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            local_defs = collect_function_defs(node)
            local_allowed = allowed_globals | local_defs
            for name, lineno in collect_function_loads(node):
                if name not in local_allowed:
                    errors.append(f"{role} undefined name at line {lineno}: {name}")

    for class_node in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
        methods = {
            item.name: method_arity(item)
            for item in class_node.body
            if isinstance(item, ast.FunctionDef)
        }
        visitor = SelfCallVisitor(methods, role, errors)
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef):
                visitor.visit(item)

    static_visitor = DriverStaticVisitor()
    static_visitor.visit(tree)
    if role in {"debug_driver", "production_driver"}:
        missing_checks = sorted(static_visitor.i2c_methods_used - static_visitor.hasattr_checks)
        if missing_checks:
            errors.append(
                f"{role} I2C capability check missing methods used later: {', '.join(missing_checks)}"
            )
    if role in {"debug_driver", "production_driver", "test"} and static_visitor.non_integer_consts:
        lines = ", ".join(str(line) for line in static_visitor.non_integer_consts)
        errors.append(f"{role} uses const(...) with non-integer literal at line(s): {lines}")
    if role == "test" and "const(" in text and "const" not in module_defs:
        errors.append("test uses const(...) but does not import or define const")


def validate_driver_text(path: Path, role: str, errors: list[str]) -> None:
    if role not in {"debug_driver", "production_driver", "test"}:
        return
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    if "_I2C_ADDR_WRITE" in text or "_I2C_ADDR_READ" in text:
        errors.append(f"{role} appears to use read/write I2C address constants; MicroPython I2C APIs require one 7-bit address")
    if re.search(r"isinstance\s*\(\s*\w+\s*,\s*I2C\s*\)", text):
        errors.append(f"{role} uses strict isinstance(..., I2C); use duck typing so SoftI2C-compatible objects work")
    validate_python_static(text, path, role, errors)


def validate_session_state(
    state_path: Path,
    data: dict[str, Any],
    payload: dict[str, Any],
    checkpoint: dict[str, Any],
    errors: list[str],
) -> None:
    if not state_path.exists():
        errors.append(f"session_state file does not exist: {state_path}")
        return
    try:
        state = load(state_path)
    except Exception as exc:
        errors.append(f"session_state could not be loaded: {exc}")
        return
    if state.get("protocol_version") != data.get("protocol_version"):
        errors.append("session_state.protocol_version does not match phase_complete")
    if state.get("session_id") != data.get("session_id"):
        errors.append("session_state.session_id does not match phase_complete")
    if state.get("phase") != PHASE:
        errors.append(f"session_state.phase must be {PHASE}")
    if state_path.name != STATE_FILE:
        errors.append(f"session_state file must be named {STATE_FILE}")
    expected_checkpoint = checkpoint_name(checkpoint)
    if state.get("checkpoint") != expected_checkpoint:
        errors.append(f"session_state.checkpoint must match phase_complete checkpoint: {expected_checkpoint}")
    if payload.get("result") == "partial" and state.get("checkpoint") == "phase_completed":
        errors.append("partial result must not leave session_state checkpoint at phase_completed")


def validate(
    data: dict[str, Any],
    artifact_root: Path | None = None,
    session_state_path: Path | None = None,
    input_path: Path | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    validate_input_filename(input_path, errors)
    for field in ("protocol_version", "msg_id", "session_id", "phase", "timestamp", "type", "idempotency_key", "payload"):
        if field not in data:
            errors.append(f"missing envelope field {field}")
    if data.get("protocol_version") != "1.0":
        errors.append("protocol_version must be 1.0")
    if data.get("phase") != PHASE:
        errors.append(f"phase must be {PHASE}")
    if data.get("type") != "phase_complete":
        errors.append("type must be phase_complete")
    if "idempotency_key" in data:
        validate_phase_scoped_id("idempotency_key", data.get("idempotency_key"), data.get("session_id"), errors)
    payload = data.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        return False, errors
    validate_nested_idempotency_keys(payload, "payload", data.get("session_id"), errors)
    if payload.get("phase") != DOMAIN_PHASE:
        errors.append(f"payload.phase must be {DOMAIN_PHASE}")
    if payload.get("domain_phase") != DOMAIN_PHASE:
        errors.append(f"payload.domain_phase must be {DOMAIN_PHASE}")
    if payload.get("result") not in RESULTS:
        errors.append("payload.result must be success, partial, or failed")
    if not payload.get("summary"):
        errors.append("payload.summary is required")
    runtime = payload.get("runtime_context")
    if not isinstance(runtime, dict):
        errors.append("payload.runtime_context must be an object")
    else:
        for field in ("artifact_root", "session_root", "project_root", "file_operation_root", "resource_root"):
            if not runtime.get(field):
                errors.append(f"payload.runtime_context.{field} is required")
        for field in ("session_root", "project_root", "file_operation_root"):
            value = runtime.get(field)
            if value and not is_relative_path(str(value)):
                errors.append(f"payload.runtime_context.{field} must be relative: {value}")
    checkpoint = payload.get("checkpoint")
    if not isinstance(checkpoint, dict):
        errors.append("payload.checkpoint must be an object")
    else:
        for field in ("checkpoint_id", "resume_phase", "resume_step"):
            if not checkpoint.get(field):
                errors.append(f"payload.checkpoint.{field} is required")
        validate_checkpoint_id(checkpoint, data.get("session_id"), errors)
        if checkpoint.get("resume_phase") != PHASE:
            errors.append(f"payload.checkpoint.resume_phase must be {PHASE}")
        state_file = checkpoint.get("state_file")
        if state_file and not is_relative_path(str(state_file)):
            errors.append("payload.checkpoint.state_file must be relative")
        if isinstance(state_file, str) and Path(state_file).name != STATE_FILE:
            errors.append(f"payload.checkpoint.state_file must be named {STATE_FILE}")
    file_manifest = payload.get("file_manifest")
    has_driver = False
    if not isinstance(file_manifest, dict):
        errors.append("payload.file_manifest must be an object")
    else:
        files = file_manifest.get("files")
        if not isinstance(files, list):
            errors.append("payload.file_manifest.files must be an array")
        else:
            for index, item in enumerate(files):
                if not isinstance(item, dict):
                    errors.append(f"file_manifest.files[{index}] must be an object")
                    continue
                path = item.get("path")
                if not isinstance(path, str) or not is_relative_path(path):
                    errors.append(f"file_manifest.files[{index}].path must be relative")
                    path = ""
                role = item.get("role")
                if role == "state" and isinstance(path, str) and Path(path).name != STATE_FILE:
                    errors.append(f"file_manifest.files[{index}].state path must be named {STATE_FILE}")
                if role == "production_driver":
                    has_driver = True
                if not role:
                    errors.append(f"file_manifest.files[{index}].role is required")
                elif role not in FILE_ROLES:
                    errors.append(f"file_manifest.files[{index}].role is not recognized")
                status = item.get("status")
                if status not in FILE_STATUSES:
                    errors.append(f"file_manifest.files[{index}].status must be created, updated, unchanged, skipped, or error")
                if "hash" in item:
                    errors.append(f"file_manifest.files[{index}] must use sha256, not hash")
                if status in HASHED_FILE_STATUSES:
                    sha256 = item.get("sha256")
                    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
                        errors.append(f"file_manifest.files[{index}].sha256 must be a 64-character hex digest")
                    byte_count = item.get("bytes")
                    if not isinstance(byte_count, int) or byte_count < 0:
                        errors.append(f"file_manifest.files[{index}].bytes must be a non-negative integer")
                    if artifact_root and path:
                        resolved = resolve_artifact_path(artifact_root, path)
                        if not resolved.exists():
                            errors.append(f"file_manifest.files[{index}].path does not exist under artifact_root: {path}")
                        elif resolved.is_file():
                            actual_sha256 = sha256_file(resolved)
                            actual_bytes = resolved.stat().st_size
                            if isinstance(sha256, str) and SHA256_RE.fullmatch(sha256) and sha256.lower() != actual_sha256:
                                errors.append(f"file_manifest.files[{index}].sha256 does not match file: {path}")
                            if isinstance(byte_count, int) and byte_count != actual_bytes:
                                errors.append(f"file_manifest.files[{index}].bytes does not match file: {path}")
                            validate_driver_text(resolved, str(role), errors)
    structured = payload.get("structured_errors")
    if not isinstance(structured, list):
        errors.append("payload.structured_errors must be an array")
    else:
        for index, item in enumerate(structured):
            if not isinstance(item, dict):
                errors.append(f"structured_errors[{index}] must be an object")
                continue
            for field in ("code", "severity", "phase_step", "retryable", "message", "details", "next_action"):
                if field not in item:
                    errors.append(f"structured_errors[{index}].{field} is required")
            details = item.get("details")
            if item.get("code") == "DEVICE_NOT_FOUND" and isinstance(details, dict) and details.get("missing_capability"):
                errors.append(
                    f"structured_errors[{index}] must use HOST_CAPABILITY_MISSING when details.missing_capability is present"
                )
            if item.get("code") == "HOST_CAPABILITY_MISSING":
                if not isinstance(details, dict) or not details.get("missing_capability"):
                    errors.append(f"structured_errors[{index}].details.missing_capability is required for HOST_CAPABILITY_MISSING")
    if payload.get("result") == "success" and structured:
        errors.append("success must not contain structured_errors")
    if payload.get("result") in {"partial", "failed"} and not structured:
        errors.append("partial/failed must include structured_errors")
    permissions = payload.get("permissions")
    if permissions is not None and not isinstance(permissions, list):
        errors.append("payload.permissions must be an array")
    elif isinstance(permissions, list):
        for index, item in enumerate(permissions):
            if not isinstance(item, dict):
                errors.append(f"permissions[{index}] must be an object")
                continue
            for field in ("permission_id", "operation", "reason", "timeout_ms", "idempotency_key"):
                if field not in item:
                    errors.append(f"permissions[{index}].{field} is required")
            if item.get("operation") and item.get("operation") not in PERMISSION_OPERATIONS:
                errors.append(f"permissions[{index}].operation is not recognized")
            if "timeout_ms" in item and not isinstance(item.get("timeout_ms"), int):
                errors.append(f"permissions[{index}].timeout_ms must be an integer")
            paths = item.get("paths", [])
            if paths is not None and not isinstance(paths, list):
                errors.append(f"permissions[{index}].paths must be an array")
                paths = []
            for path in paths or []:
                if not isinstance(path, str) or not is_relative_path(path):
                    errors.append(f"permissions[{index}].paths must be relative")
            retry_of = item.get("retry_of")
            if retry_of is not None and not isinstance(retry_of, str):
                errors.append(f"permissions[{index}].retry_of must be a string")
    validate_permission_idempotency_keys(permissions, has_driver, errors)
    warnings = payload.get("warnings")
    if warnings is None:
        warnings = []
    if not isinstance(warnings, list):
        errors.append("payload.warnings must be an array when present")
        warnings = []
    hardware_verified = payload.get("hardware_verified")
    if "hardware_verified" not in payload:
        errors.append("payload.hardware_verified is required")
    elif not isinstance(hardware_verified, bool):
        errors.append("payload.hardware_verified must be a boolean")
    verification_mode = payload.get("verification_mode")
    if verification_mode is not None and verification_mode not in VERIFICATION_MODES:
        errors.append("payload.verification_mode must be hardware, mock, skipped, or none")
    mock_verification = verification_mode == "mock" or payload.get("mock_verification") is True
    verification_skipped = payload.get("verification_skipped_by_user") is True
    validate_artifacts(payload.get("artifacts"), payload.get("result"), hardware_verified, errors)
    if verification_mode == "hardware" and hardware_verified is not True:
        errors.append("verification_mode=hardware requires hardware_verified=true")
    if verification_mode == "skipped" and not verification_skipped:
        errors.append("verification_mode=skipped requires verification_skipped_by_user=true")
    if payload.get("mock_verification") is True and verification_mode != "mock":
        errors.append("mock_verification=true requires verification_mode=mock")
    if payload.get("result") == "partial" and hardware_verified is not True and not verification_skipped and verification_mode != "none":
        errors.append("partial unverified results must set verification_mode=none")
    if payload.get("result") == "partial" and mock_verification:
        errors.append("partial no-device/timeout/cancelled results must use verification_mode=none, not mock")
    if has_driver and payload.get("result") != "success":
        errors.append("production_driver role is only allowed in a success payload")
    if has_driver and hardware_verified is not True and not verification_skipped and not mock_verification:
        errors.append("production_driver requires hardware_verified=true, verification_skipped_by_user=true, or verification_mode=mock")
    if verification_skipped and not warnings:
        errors.append("verification_skipped_by_user=true requires a warning")
    if mock_verification and not warnings:
        errors.append("verification_mode=mock requires a warning")
    if mock_verification and hardware_verified is True:
        errors.append("verification_mode=mock must not set hardware_verified=true")
    if payload.get("result") == "success":
        if not has_driver:
            errors.append("success must include a production_driver file")
        if hardware_verified is not True and not verification_skipped and not mock_verification:
            errors.append("success must set hardware_verified=true, verification_skipped_by_user=true, or verification_mode=mock")
    if payload.get("result") == "partial":
        if not isinstance(checkpoint, dict) or checkpoint.get("resume_phase") != PHASE:
            errors.append("partial must include a resumable checkpoint")
        has_trusted_file = False
        if isinstance(file_manifest, dict) and isinstance(file_manifest.get("files"), list):
            has_trusted_file = bool(file_manifest["files"])
        if not has_trusted_file:
            errors.append("partial must include at least one trusted file_manifest entry")
    if session_state_path is None and artifact_root and isinstance(checkpoint, dict):
        state_file = checkpoint.get("state_file")
        if isinstance(state_file, str) and is_relative_path(state_file):
            candidate = resolve_artifact_path(artifact_root, state_file)
            if candidate.exists():
                session_state_path = candidate
    if session_state_path and isinstance(checkpoint, dict):
        validate_session_state(session_state_path, data, payload, checkpoint, errors)
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--artifact-root")
    parser.add_argument("--session-state")
    args = parser.parse_args()
    try:
        input_path = Path(args.input)
        data = load(input_path)
        artifact_root = Path(args.artifact_root) if args.artifact_root else None
        session_state_path = Path(args.session_state) if args.session_state else None
        ok, errors = validate(data, artifact_root=artifact_root, session_state_path=session_state_path, input_path=input_path)
    except Exception as exc:
        ok, errors = False, [str(exc)]
    print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
