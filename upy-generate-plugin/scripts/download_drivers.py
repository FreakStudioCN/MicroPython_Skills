#!/usr/bin/env python3
"""Resolve and download MicroPython driver files as stdout JSON.

This plugin-mode script does not write project files and does not mutate the
manifest. It returns file records that the host/LLM must turn into
file_operation(write) under firmware/lib.
"""

from __future__ import annotations

import argparse
import py_compile
import tempfile
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump, load_manifest_arg, safe_name
from driver_ready_gate import driver_ready_gate_errors


UPYPI_BASE = "https://upypi.net"


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "upy-generate-plugin/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - user-requested public API
        return response.read().decode("utf-8-sig", errors="replace")


def fetch_json(url: str, timeout: int = 20) -> Any:
    return json.loads(fetch_text(url, timeout=timeout))


def normalize_python_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    cleaned: list[str] = []
    skip_blank_after_backslash = False
    for line in lines:
        if skip_blank_after_backslash and not line.strip():
            continue
        cleaned.append(line)
        skip_blank_after_backslash = line.rstrip().endswith("\\")
    return "\n".join(cleaned) + ("\n" if text.endswith("\n") or cleaned else "")


def firmware_lib_path(filename: str) -> str:
    filename = filename.replace("\\", "/").split("/")[-1]
    if not filename:
        filename = "driver.py"
    return f"firmware/lib/{filename}"


def compile_record(path: str, content: str) -> dict[str, Any] | None:
    if not path.endswith(".py"):
        return None
    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / Path(path).name
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        try:
            py_compile.compile(str(target), doraise=True)
            return {"ok": True, "error": None}
        except py_compile.PyCompileError as exc:
            return {"ok": False, "error": str(exc)}


def file_record(path: str, content: str, role: str, source_path: str) -> dict[str, Any]:
    record = {
        "path": path,
        "content": content,
        "encoding": "utf-8",
        "role": role,
        "source_path": source_path,
    }
    compile_info = compile_record(path, content)
    if compile_info is not None:
        record["compile"] = compile_info
    return record


def download_upypi(device_name: str, package_name: str, version: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    base = f"{UPYPI_BASE}/pkgs/{package_name}/{version}"
    try:
        package = fetch_json(f"{base}/package.json")
    except Exception as exc:
        return files, [{"code": "UPYPI_PACKAGE_JSON_FAILED", "package": package_name, "message": str(exc)}]

    for entry in package.get("urls", []):
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        target_name, source_path = str(entry[0]), str(entry[1])
        if not target_name.endswith(".py"):
            continue
        try:
            text = normalize_python_text(fetch_text(f"{base}/{source_path}"))
        except Exception as exc:
            warnings.append({"code": "UPYPI_FILE_FETCH_FAILED", "file": target_name, "message": str(exc)})
            continue
        files.append(file_record(firmware_lib_path(target_name), text, "driver", source_path))

    safe = safe_name(device_name)
    for ref_name, url, role in (
        (f"{safe}_README.md", f"{base}/README.md", "readme"),
        (f"{safe}_example.py", f"{base}/code/main.py", "example"),
    ):
        try:
            text = fetch_text(url)
        except Exception:
            continue
        if text.strip():
            if role == "example":
                text = normalize_python_text(text)
            files.append(file_record(firmware_lib_path(ref_name), text, role, url))
    return files, warnings


def parse_github_repo(url: str) -> tuple[str, str] | None:
    match = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", url)
    if not match:
        return None
    return match.group(1), match.group(2).rstrip("/")


def download_github(device_name: str, repo_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    parsed = parse_github_repo(repo_url)
    if not parsed:
        return files, [{"code": "GITHUB_URL_INVALID", "url": repo_url}]
    owner, repo = parsed
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    try:
        contents = fetch_json(api_url)
    except Exception as exc:
        contents = []
        warnings.append({"code": "GITHUB_CONTENTS_FAILED", "url": api_url, "message": str(exc)})
    if isinstance(contents, list):
        for item in contents:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            if not name.endswith(".py") or "setup" in name.lower():
                continue
            dl_url = item.get("download_url")
            if not dl_url:
                continue
            try:
                text = normalize_python_text(fetch_text(str(dl_url)))
            except Exception as exc:
                warnings.append({"code": "GITHUB_FILE_FETCH_FAILED", "file": name, "message": str(exc)})
                continue
            files.append(file_record(firmware_lib_path(name), text, "driver", str(dl_url)))
    safe = safe_name(device_name)
    readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md"
    try:
        readme = fetch_text(readme_url)
    except Exception:
        readme = ""
    if readme.strip():
        files.append(file_record(firmware_lib_path(f"{safe}_README.md"), readme, "readme", readme_url))
    return files, warnings


def placeholder_for_none(device: dict[str, Any]) -> dict[str, Any]:
    name = safe_name(str(device.get("name", "device")))
    content = (
        '"""GPIO/manual device placeholder generated by upy-generate-plugin.\n\n'
        "The LLM must replace this with a factory or keep it as documentation\n"
        "for devices that do not require an external library.\n"
        '"""\n'
    )
    return file_record(f"firmware/lib/{name}_placeholder.py", content, "placeholder", "generated")


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Download MicroPython drivers as JSON file records")
    parser.add_argument("--manifest", default="-", help="Manifest JSON or phase_complete path. Use '-' for stdin.")
    parser.add_argument("--offline", action="store_true", help="Do not access network; emit planned dependencies only")
    args = parser.parse_args()

    manifest = load_manifest_arg(args.manifest)
    drivers: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    gate_errors = driver_ready_gate_errors(manifest)
    if gate_errors:
        json_dump(
            {
                "drivers": [],
                "errors": gate_errors,
                "warnings": [],
                "summary": "Blocked generate before driver resolution: {} device driver(s) are not ready".format(
                    len(gate_errors)
                ),
            }
        )
        return 2

    all_warnings: list[dict[str, Any]] = []
    for device in manifest.get("devices", []):
        if not isinstance(device, dict):
            continue
        driver = device.get("driver", {})
        if not isinstance(driver, dict):
            driver = {}
        source = str(driver.get("source", "")).lower()
        device_name = str(device.get("name", "device"))
        package_name = str(driver.get("package_name", ""))
        status = str(driver.get("status") or driver.get("driver_status") or device.get("driver_status") or "").strip()
        version = str(driver.get("version", "1.0.0"))
        files: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if status == "ready" and driver.get("path"):
            warnings.append(
                {
                    "code": "DRIVER_ALREADY_READY",
                    "device": device_name,
                    "path": driver.get("path"),
                    "message": "driver is already hardware-ready; no firmware/lib download is required",
                }
            )
        elif args.offline:
            warnings.append({"code": "OFFLINE_MODE", "message": "network download skipped"})
        elif source == "upypi" and package_name:
            files, warnings = download_upypi(device_name, package_name, version)
        elif source in {"awesome-micropython", "github"} and driver.get("driver_url"):
            files, warnings = download_github(device_name, str(driver["driver_url"]))
        elif source in {"none", "manual", ""}:
            files = [placeholder_for_none(device)]
        else:
            warnings.append({"code": "DRIVER_SOURCE_UNSUPPORTED", "device": device_name, "source": source})
        if source != "none" and not files and not args.offline and status not in {"cold_driver_required", "ready"}:
            warnings.append({"code": "NO_DRIVER_FILES", "device": device_name})
        drivers.append(
            {
                "device_name": device_name,
                "source": source or "none",
                "package_name": package_name or None,
                "version": version if package_name else None,
                "files": files,
                "warnings": warnings,
            }
        )
        all_warnings.extend(warnings)
    json_dump(
        {
            "drivers": drivers,
            "errors": errors,
            "warnings": all_warnings,
            "summary": "Resolved {} device driver entries, {} files total".format(
                len(drivers),
                sum(len(item["files"]) for item in drivers),
            ),
        }
    )
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
