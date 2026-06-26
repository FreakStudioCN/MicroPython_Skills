#!/usr/bin/env python3
"""Validate deploy-time MicroPython runtime dependency declarations."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


DEVICE_TEST_DIRS = (("device", "tests"), ("test", "device"))
RUNTIME_IMPORTS = {
    "unittest": {
        "package": "unittest",
        "verify_import": "unittest",
        "required_for": "device_tests",
        "reason": "device-side tests import unittest",
    },
    "urequests": {
        "package": "urequests",
        "verify_import": "urequests",
        "required_for": "firmware",
        "reason": "firmware imports urequests",
    },
    "requests": {
        "package": "requests",
        "verify_import": "requests",
        "required_for": "firmware",
        "reason": "firmware imports requests",
    },
    "umqtt": {
        "package": "umqtt.simple",
        "verify_import": "umqtt.simple",
        "required_for": "firmware",
        "reason": "firmware imports umqtt",
    },
}
BUILTIN_IMPORTS = {
    "array",
    "binascii",
    "bluetooth",
    "cmath",
    "collections",
    "errno",
    "esp",
    "esp32",
    "framebuf",
    "gc",
    "hashlib",
    "heapq",
    "io",
    "json",
    "machine",
    "math",
    "micropython",
    "network",
    "os",
    "random",
    "re",
    "select",
    "socket",
    "ssl",
    "struct",
    "sys",
    "time",
    "uasyncio",
    "uctypes",
    "uselect",
    "usocket",
}


def load_manifest(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "project-manifest.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def runtime_dependencies(manifest: dict[str, Any]) -> dict[str, Any]:
    direct = manifest.get("runtime_dependencies")
    if isinstance(direct, dict):
        return direct
    generate = manifest.get("generate")
    if isinstance(generate, dict) and isinstance(generate.get("runtime_dependencies"), dict):
        return generate["runtime_dependencies"]
    return {}


def declared_mip(runtime_deps: dict[str, Any]) -> list[dict[str, Any]]:
    mip = runtime_deps.get("mip") if isinstance(runtime_deps, dict) else []
    if not isinstance(mip, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in mip:
        if isinstance(item, str):
            entries.append({"package": item, "verify_import": item.replace("-", "_"), "target": "/lib", "install_phase": "deploy"})
        elif isinstance(item, dict):
            entries.append(item)
    return entries


def project_py_files(project_dir: Path) -> list[Path]:
    roots = [
        project_dir / "firmware",
        project_dir / "device" / "tests",
        project_dir / "test" / "device",
    ]
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
        elif root.is_dir():
            files.extend(root.rglob("*.py"))
    return sorted(set(files))


def is_device_test(project_dir: Path, path: Path) -> bool:
    try:
        rel_parts = path.relative_to(project_dir).parts
    except ValueError:
        return False
    return any(tuple(rel_parts[: len(parts)]) == parts for parts in DEVICE_TEST_DIRS)


def import_roots(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError:
        return set()
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def needed_runtime_deps(project_dir: Path) -> dict[str, dict[str, Any]]:
    needed: dict[str, dict[str, Any]] = {}
    for path in project_py_files(project_dir):
        roots = import_roots(path)
        rel = path.relative_to(project_dir).as_posix()
        for root in roots:
            if root == "unittest" and not is_device_test(project_dir, path):
                continue
            info = RUNTIME_IMPORTS.get(root)
            if not info:
                continue
            record = needed.setdefault(
                root,
                {
                    **info,
                    "import_root": root,
                    "evidence": [],
                },
            )
            record["evidence"].append(rel)
    return needed


def entry_matches(entry: dict[str, Any], required: dict[str, Any]) -> bool:
    package = str(entry.get("package") or "")
    verify_import = str(entry.get("verify_import") or "")
    return package == required["package"] or verify_import == required["verify_import"]


def validate_entry(entry: dict[str, Any], required: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    package = str(entry.get("package") or "")
    required_for = entry.get("required_for")
    if entry.get("install_phase") != "deploy":
        errors.append(
            {
                "code": "MPY_RUNTIME_DEPENDENCY_INSTALL_PHASE_INVALID",
                "package": package,
                "message": "runtime_dependencies.mip entries must use install_phase=deploy",
            }
        )
    if not entry.get("target"):
        errors.append(
            {
                "code": "MPY_RUNTIME_DEPENDENCY_TARGET_MISSING",
                "package": package,
                "message": "runtime_dependencies.mip entry must declare target, usually /lib",
            }
        )
    if entry.get("verify_import") != required["verify_import"]:
        errors.append(
            {
                "code": "MPY_RUNTIME_DEPENDENCY_VERIFY_IMPORT_MISSING",
                "package": package,
                "expected": required["verify_import"],
                "message": "runtime dependency must declare verify_import so deploy can probe installation",
            }
        )
    if isinstance(required_for, list):
        has_required_for = required["required_for"] in required_for
    else:
        has_required_for = required_for == required["required_for"]
    if not has_required_for:
        errors.append(
            {
                "code": "MPY_RUNTIME_DEPENDENCY_REQUIRED_FOR_MISSING",
                "package": package,
                "expected": required["required_for"],
                "message": "runtime dependency must declare the feature that needs it",
            }
        )
    return errors


def check(project_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    runtime_deps = runtime_dependencies(manifest)
    mip_entries = declared_mip(runtime_deps)
    needed = needed_runtime_deps(project_dir)
    errors: list[dict[str, Any]] = []
    for root, required in needed.items():
        matches = [entry for entry in mip_entries if entry_matches(entry, required)]
        if not matches:
            errors.append(
                {
                    "code": "MPY_RUNTIME_DEPENDENCY_UNDECLARED",
                    "import_root": root,
                    "package": required["package"],
                    "verify_import": required["verify_import"],
                    "evidence": required["evidence"],
                    "message": "generate must declare MicroPython runtime dependencies for deploy-time mpremote mip install",
                }
            )
            continue
        errors.extend(validate_entry(matches[0], required))
    return {
        "check": "runtime_dependencies",
        "project_dir": str(project_dir),
        "needed": list(needed.values()),
        "declared_mip": mip_entries,
        "builtin_required": runtime_deps.get("builtin_required", []) if isinstance(runtime_deps, dict) else [],
        "known_builtin_imports": sorted(BUILTIN_IMPORTS),
        "errors": errors,
        "warnings": [],
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    result = check(Path(args.project_dir))
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
