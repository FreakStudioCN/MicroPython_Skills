#!/usr/bin/env python3
"""Install MicroPython runtime dependencies declared by generate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import configure_stdio, load_json, print_json, write_json
from mpremote_runtime import MpremoteUnavailable, run_mpremote


SUCCESS_STATUS = {"success", "ok", "skipped"}
NETWORK_FAILURE_MARKERS = (
    "getaddrinfo",
    "temporary failure",
    "name or service not known",
    "network is unreachable",
    "connection refused",
    "connection reset",
    "connection timed out",
    "timed out",
    "ssl",
    "tls",
    "certificate",
    "proxy",
    "403",
    "407",
    "http error",
    "urlerror",
    "mip install failed",
)


def unwrap_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    payload = data.get("payload")
    if isinstance(payload, dict):
        manifest = payload.get("manifest_content")
        if isinstance(manifest, dict):
            return manifest
        manifest = payload.get("manifest")
        if isinstance(manifest, dict):
            return manifest
    manifest = data.get("manifest_content")
    if isinstance(manifest, dict):
        return manifest
    manifest = data.get("manifest")
    if isinstance(manifest, dict):
        return manifest
    return data


def load_manifest(project_root: Path, manifest_path: str | None) -> dict[str, Any]:
    path = Path(manifest_path) if manifest_path else project_root / "project-manifest.json"
    if not path.exists():
        return {}
    return unwrap_manifest(load_json(path))


def runtime_dependencies(manifest: dict[str, Any]) -> dict[str, Any]:
    direct = manifest.get("runtime_dependencies")
    if isinstance(direct, dict):
        return direct
    generate = manifest.get("generate")
    if isinstance(generate, dict) and isinstance(generate.get("runtime_dependencies"), dict):
        return generate["runtime_dependencies"]
    return {}


def normalize_mip_entry(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        package = item.strip()
        if not package:
            return None
        return {
            "package": package,
            "target": "/lib",
            "version": "latest",
            "install_phase": "deploy",
            "verify_import": package.replace("-", "_"),
        }
    if not isinstance(item, dict):
        return None
    package = str(item.get("package") or "").strip()
    if not package:
        return None
    target = str(item.get("target") or "/lib").strip() or "/lib"
    verify_import = str(item.get("verify_import") or package.replace("-", "_")).strip()
    return {
        **item,
        "package": package,
        "target": target,
        "version": str(item.get("version") or "latest"),
        "install_phase": str(item.get("install_phase") or "deploy"),
        "verify_import": verify_import,
    }


def mip_dependencies(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    deps = runtime_dependencies(manifest)
    raw = deps.get("mip") if isinstance(deps, dict) else []
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        entry = normalize_mip_entry(item)
        if not entry:
            continue
        key = (entry["package"], entry.get("verify_import") or "", entry["target"])
        if key in seen:
            continue
        seen.add(key)
        normalized.append(entry)
    return normalized


def import_probe_code(module: str) -> str:
    return f"import {module}; print('MPY_IMPORT_OK:{module}')"


def verify_import(port: str, module: str, timeout_ms: int) -> dict[str, Any]:
    completed = run_mpremote(port, ["resume", "exec", import_probe_code(module)], timeout_ms, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return {
        "returncode": completed.returncode,
        "stdout_excerpt": (completed.stdout or "")[-2000:],
        "stderr_excerpt": (completed.stderr or "")[-2000:],
        "ok": completed.returncode == 0 and f"MPY_IMPORT_OK:{module}" in output,
    }


def install_package(port: str, package: str, target: str, timeout_ms: int) -> dict[str, Any]:
    args = ["mip", "install"]
    if target:
        args.append(f"--target={target}")
    args.append(package)
    completed = run_mpremote(port, args, timeout_ms, check=False)
    return {
        "command_args": args,
        "returncode": completed.returncode,
        "stdout_excerpt": (completed.stdout or "")[-4000:],
        "stderr_excerpt": (completed.stderr or "")[-4000:],
        "ok": completed.returncode == 0,
    }


def classify_install_failure(report: dict[str, Any]) -> str:
    text = ((report.get("stdout_excerpt") or "") + "\n" + (report.get("stderr_excerpt") or "")).lower()
    if any(marker in text for marker in NETWORK_FAILURE_MARKERS):
        return "network_or_proxy_unavailable"
    if "no space" in text or "enospc" in text:
        return "device_storage_full"
    return "install_failed"


def normalize_device_path(path: str) -> str:
    value = path.strip().replace("\\", "/")
    if not value:
        return "/"
    if not value.startswith("/"):
        value = "/" + value
    while "//" in value:
        value = value.replace("//", "/")
    return value.rstrip("/") or "/"


def remote_arg(path: str) -> str:
    return ":" + normalize_device_path(path).lstrip("/")


def fs_ls(port: str, path: str, timeout_ms: int) -> dict[str, Any]:
    normalized = normalize_device_path(path)
    completed = run_mpremote(port, ["resume", "fs", "ls", remote_arg(normalized)], timeout_ms, check=False)
    return {
        "path": normalized,
        "command_args": ["resume", "fs", "ls", remote_arg(normalized)],
        "returncode": completed.returncode,
        "stdout_excerpt": (completed.stdout or "")[-4000:],
        "stderr_excerpt": (completed.stderr or "")[-4000:],
        "ok": completed.returncode == 0,
    }


def parse_ls_names(stdout: str) -> list[str]:
    names: list[str] = []
    for line in stdout.splitlines():
        item = line.strip()
        if not item:
            continue
        parts = item.split()
        name = parts[-1].rstrip("/") if parts else item.rstrip("/")
        if name and name not in {".", ".."}:
            names.append(name)
    return names


def fs_verify_dependency(port: str, dep: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    module = dep.get("verify_import") or dep["package"].replace("-", "_")
    target = normalize_device_path(dep.get("target") or "/lib")
    package_path = normalize_device_path(f"{target}/{module.replace('.', '/')}")
    root_listing = fs_ls(port, target, timeout_ms)
    package_listing = fs_ls(port, package_path, timeout_ms)
    root_names = parse_ls_names(root_listing.get("stdout_excerpt") or "")
    package_names = parse_ls_names(package_listing.get("stdout_excerpt") or "")
    expected_files = ["__init__.py", "__init__.mpy"]
    matched_files = [name for name in expected_files if name in package_names]
    module_leaf = module.split(".")[-1]
    module_files = [f"{module_leaf}.py", f"{module_leaf}.mpy"]
    matched_module_files = [name for name in module_files if name in root_names]
    ok = bool(
        root_listing["ok"]
        and (
            (package_listing["ok"] and matched_files)
            or matched_module_files
            or module_leaf in root_names
        )
    )
    return {
        "status": "success" if ok else "failed",
        "target": target,
        "package_path": package_path,
        "expected_files": expected_files,
        "matched_files": matched_files,
        "module_files": module_files,
        "matched_module_files": matched_module_files,
        "root_listing": root_listing,
        "package_listing": package_listing,
        "ok": ok,
    }


def mock_install(deps: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for dep in deps:
        records.append(
            {
                "package": dep["package"],
                "target": dep["target"],
                "verify_import": dep.get("verify_import"),
                "status": "installed",
                "mode": "mock",
                "pre_verify": {"ok": False},
                "install": {"ok": True, "command_args": ["mip", "install", f"--target={dep['target']}", dep["package"]]},
                "post_verify": {"ok": True},
                "fs_verify": {
                    "status": "success",
                    "target": dep["target"],
                    "package_path": f"{dep['target'].rstrip('/')}/{dep.get('verify_import') or dep['package']}",
                    "expected_files": ["__init__.py", "__init__.mpy"],
                    "matched_files": ["__init__.mpy"],
                    "module_files": ["unittest.py", "unittest.mpy"],
                    "matched_module_files": [],
                    "root_listing": {"ok": True, "stdout_excerpt": "unittest/"},
                    "package_listing": {"ok": True, "stdout_excerpt": "__init__.mpy"},
                    "ok": True,
                },
            }
        )
    return {
        "status": "success" if records else "skipped",
        "mode": "mock",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dependency_count": len(deps),
        "installed": len(records),
        "already_available": 0,
        "failed": 0,
        "dependencies": deps,
        "records": records,
        "errors": [],
        "warnings": [],
    }


def install_dependencies(project_root: Path, manifest_path: str | None, port: str, timeout_ms: int) -> dict[str, Any]:
    manifest = load_manifest(project_root, manifest_path)
    deps = mip_dependencies(manifest)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not deps:
        return {
            "status": "skipped",
            "mode": "live",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_root": str(project_root),
            "manifest_path": manifest_path or str(project_root / "project-manifest.json"),
            "port": port or None,
            "dependency_count": 0,
            "installed": 0,
            "already_available": 0,
            "failed": 0,
            "dependencies": [],
            "records": [],
            "errors": [],
            "warnings": [{"code": "mip_dependencies_not_declared", "message": "no runtime_dependencies.mip entries were found"}],
        }
    if not port:
        return {
            "status": "action_required",
            "mode": "live",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_root": str(project_root),
            "manifest_path": manifest_path or str(project_root / "project-manifest.json"),
            "port": None,
            "dependency_count": len(deps),
            "installed": 0,
            "already_available": 0,
            "failed": len(deps),
            "dependencies": deps,
            "records": [],
            "errors": [{"code": "port_required", "message": "--port is required unless --mock is used"}],
            "warnings": [],
        }
    for dep in deps:
        record: dict[str, Any] = {
            "package": dep["package"],
            "target": dep["target"],
            "verify_import": dep.get("verify_import"),
            "required_for": dep.get("required_for", []),
            "reason": dep.get("reason"),
        }
        if dep.get("install_phase") not in {"deploy", ""}:
            record["status"] = "skipped"
            record["skip_reason"] = f"install_phase={dep.get('install_phase')}"
            warnings.append(
                {
                    "code": "mip_dependency_non_deploy_phase",
                    "package": dep["package"],
                    "install_phase": dep.get("install_phase"),
                    "message": "runtime dependency is not marked for deploy installation",
                }
            )
            records.append(record)
            continue
        module = dep.get("verify_import") or dep["package"].replace("-", "_")
        pre_verify = verify_import(port, module, timeout_ms)
        record["pre_verify"] = pre_verify
        if pre_verify["ok"]:
            record["status"] = "already_available"
            records.append(record)
            continue
        install = install_package(port, dep["package"], dep["target"], timeout_ms)
        record["install"] = install
        if not install["ok"]:
            record["status"] = "failed"
            failure_class = classify_install_failure(install)
            code = "runtime_dependency_install_network_unavailable" if failure_class == "network_or_proxy_unavailable" else "runtime_dependency_install_failed"
            errors.append(
                {
                    "code": code,
                    "package": dep["package"],
                    "target": dep["target"],
                    "failure_class": failure_class,
                    "message": "mpremote mip install failed; network/proxy/VPN availability may be required" if failure_class == "network_or_proxy_unavailable" else "mpremote mip install failed",
                    "detail": install,
                }
            )
            records.append(record)
            continue
        post_verify = verify_import(port, module, timeout_ms)
        record["post_verify"] = post_verify
        if post_verify["ok"]:
            fs_verify = fs_verify_dependency(port, dep, timeout_ms)
            record["fs_verify"] = fs_verify
            if fs_verify["ok"]:
                record["status"] = "installed"
            else:
                record["status"] = "failed"
                errors.append(
                    {
                        "code": "runtime_dependency_fs_verify_failed",
                        "package": dep["package"],
                        "target": dep["target"],
                        "message": "dependency imports successfully but expected files were not confirmed with mpremote fs ls",
                        "detail": fs_verify,
                    }
                )
        else:
            record["status"] = "failed"
            errors.append(
                {
                    "code": "runtime_dependency_verify_failed",
                    "package": dep["package"],
                    "verify_import": module,
                    "message": "dependency installed but import verification failed",
                    "detail": post_verify,
                }
            )
        records.append(record)
    installed = sum(1 for item in records if item.get("status") == "installed")
    already_available = sum(1 for item in records if item.get("status") == "already_available")
    failed = sum(1 for item in records if item.get("status") == "failed")
    return {
        "status": "failed" if errors or failed else "success",
        "mode": "live",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "manifest_path": manifest_path or str(project_root / "project-manifest.json"),
        "port": port,
        "dependency_count": len(deps),
        "installed": installed,
        "already_available": already_available,
        "failed": failed,
        "dependencies": deps,
        "records": records,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--manifest", help="project-manifest.json or phase_complete path; defaults to project-root/project-manifest.json")
    parser.add_argument("--port", default="")
    parser.add_argument("--timeout-ms", type=int, default=120000)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    manifest = load_manifest(project_root, args.manifest)
    deps = mip_dependencies(manifest)
    try:
        result = mock_install(deps) if args.mock else install_dependencies(project_root, args.manifest, args.port, args.timeout_ms)
    except MpremoteUnavailable as exc:
        result = {
            "status": "action_required",
            "mode": "live",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_root": str(project_root),
            "port": args.port or None,
            "dependency_count": len(deps),
            "installed": 0,
            "already_available": 0,
            "failed": len(deps),
            "dependencies": deps,
            "records": [],
            "errors": [exc.to_error()],
            "warnings": [],
        }
    if args.output_json:
        write_json(args.output_json, result)
    print_json(result)
    return 0 if result.get("status") in SUCCESS_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
