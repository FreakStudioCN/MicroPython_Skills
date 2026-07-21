#!/usr/bin/env python3
"""Validate deploy-time MicroPython runtime dependency declarations."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


UPYPI_BASE = "https://upypi.net"
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
API_REFERENCE_FIELDS = ("api_ref", "api_reference", "api_summary")
API_EVIDENCE_FIELDS = (
    "docs_url",
    "doc_url",
    "documentation_url",
    "readme_url",
    "readme",
    "examples_url",
    "example_url",
    "examples",
    "source_url",
)
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


def upypi_package_url(driver: dict[str, Any], package_name: str, version: str) -> str:
    url = str(driver.get("url") or "").strip()
    if url:
        url = url.rstrip("/")
        if url.endswith("/package.json"):
            url = url[: -len("/package.json")]
        return url
    return f"{UPYPI_BASE}/pkgs/{package_name}/{version}"


def manifest_micropython_lib_deps(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    needed: dict[str, dict[str, Any]] = {}
    devices = manifest.get("devices")
    if not isinstance(devices, list):
        return needed
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            continue
        driver = device.get("driver")
        if not isinstance(driver, dict):
            continue
        if str(driver.get("source") or "").strip().lower() != "micropython_lib":
            continue
        device_name = str(device.get("name") or f"devices[{index}]")
        evidence = [f"project-manifest.json:devices[{index}].driver"]
        package = str(driver.get("package_name") or "").strip()
        if not package:
            needed[f"micropython_lib_missing_package:{index}"] = {
                "package": "",
                "verify_import": "",
                "required_for": device_name,
                "reason": f"{device_name} declares driver.source=micropython_lib but driver.package_name is missing",
                "import_root": "micropython_lib",
                "evidence": evidence,
                "missing_package": True,
            }
            continue
        verify_import = str(driver.get("verify_import") or driver.get("module") or package.replace("-", "_")).strip()
        needed[f"micropython_lib:{index}:{package}:{verify_import}"] = {
            "package": package,
            "verify_import": verify_import,
            "required_for": device_name,
            "reason": f"{device_name} requires MicroPython-lib package {package}",
            "import_root": verify_import,
            "evidence": evidence,
            "api_reference_missing": not has_api_reference(driver),
            "api_reference_weak": has_weak_api_reference(driver),
        }
    return needed


def manifest_upypi_deps(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    needed: dict[str, dict[str, Any]] = {}
    devices = manifest.get("devices")
    if not isinstance(devices, list):
        return needed
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            continue
        driver = device.get("driver")
        if not isinstance(driver, dict):
            continue
        if str(driver.get("source") or "").strip().lower() != "upypi":
            continue
        device_name = str(device.get("name") or f"devices[{index}]")
        evidence = [f"project-manifest.json:devices[{index}].driver"]
        package_name = str(driver.get("package_name") or "").strip()
        if not package_name:
            needed[f"upypi_missing_package:{index}"] = {
                "package": "",
                "verify_import": "",
                "required_for": device_name,
                "reason": f"{device_name} declares driver.source=upypi but driver.package_name is missing",
                "import_root": "upypi",
                "evidence": evidence,
                "missing_package": True,
                "missing_package_source": "upypi",
            }
            continue
        version = str(driver.get("version") or "1.0.0").strip() or "1.0.0"
        package_url = upypi_package_url(driver, package_name, version)
        verify_import = str(driver.get("verify_import") or driver.get("module") or package_name.replace("-", "_")).strip()
        needed[f"upypi:{index}:{package_name}:{verify_import}"] = {
            "package": package_url,
            "package_name": package_name,
            "version": version,
            "verify_import": verify_import,
            "required_for": device_name,
            "reason": f"{device_name} requires uPyPi package {package_name}",
            "import_root": verify_import,
            "evidence": evidence,
            "source": "upypi",
        }
    return needed


def has_nonempty_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(str(key).strip() and has_nonempty_value(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_nonempty_value(item) for item in value)
    return value is not None


def has_structured_api_reference(driver: dict[str, Any]) -> bool:
    for field in API_REFERENCE_FIELDS:
        value = driver.get(field)
        if isinstance(value, (dict, list)) and has_nonempty_value(value):
            return True
    for container_name in ("metadata", "package_metadata", "package_info"):
        container = driver.get(container_name)
        if isinstance(container, dict) and has_structured_api_reference(container):
            return True
    return False


def has_api_reference(driver: dict[str, Any]) -> bool:
    if has_structured_api_reference(driver):
        return True
    for field in API_EVIDENCE_FIELDS:
        if has_nonempty_value(driver.get(field)):
            return True
    for container_name in ("metadata", "package_metadata", "package_info"):
        container = driver.get(container_name)
        if isinstance(container, dict) and has_api_reference(container):
            return True
    return False


def has_weak_api_reference(driver: dict[str, Any]) -> bool:
    return any(isinstance(driver.get(field), str) and driver[field].strip() for field in API_REFERENCE_FIELDS)


def entry_matches(entry: dict[str, Any], required: dict[str, Any]) -> bool:
    package = str(entry.get("package") or "")
    verify_import = str(entry.get("verify_import") or "")
    return package == required["package"] or verify_import == required["verify_import"]


def validate_entry(entry: dict[str, Any], required: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    package = str(entry.get("package") or "")
    required_for = entry.get("required_for")
    if required.get("source") == "upypi" and package != required["package"]:
        errors.append(
            {
                "code": "MPY_RUNTIME_DEPENDENCY_UPYPI_PACKAGE_URL_INVALID",
                "package": package,
                "expected": required["package"],
                "message": "uPyPi runtime_dependencies.mip package must be the package URL for mpremote mip install",
            }
        )
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
    needed.update(manifest_micropython_lib_deps(manifest))
    needed.update(manifest_upypi_deps(manifest))
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for root, required in needed.items():
        if required.get("missing_package"):
            errors.append(
                {
                    "code": "MPY_RUNTIME_DEPENDENCY_PACKAGE_NAME_MISSING",
                    "import_root": required["import_root"],
                    "package": required["package"],
                    "verify_import": required["verify_import"],
                    "evidence": required["evidence"],
                    "message": f"driver.package_name is required when driver.source={required.get('missing_package_source') or 'micropython_lib'}",
                }
            )
            continue
        if required.get("api_reference_missing"):
            errors.append(
                {
                    "code": "MPY_RUNTIME_DEPENDENCY_API_REFERENCE_MISSING",
                    "import_root": required["import_root"],
                    "package": required["package"],
                    "verify_import": required["verify_import"],
                    "evidence": required["evidence"],
                    "message": "driver.source=micropython_lib needs structured api_ref or docs/readme/examples evidence before generate writes package API calls",
                }
            )
        if required.get("api_reference_weak"):
            warnings.append(
                {
                    "code": "MPY_RUNTIME_DEPENDENCY_API_REFERENCE_WEAK",
                    "package": required["package"],
                    "message": "driver.api_ref is a plain string; prefer a structured object with callable names, init shape, and example usage",
                }
            )
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
        "warnings": warnings,
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
