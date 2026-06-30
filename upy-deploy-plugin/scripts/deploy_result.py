#!/usr/bin/env python3
"""Combine upload, serial, and log reports into a deploy result."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

from common import configure_stdio, load_json, print_json, write_json


FAIL_PATTERNS = [
    ("Traceback (most recent call last)", "python_traceback"),
    ("rst cause:", "hardware_reset"),
    ("Guru Meditation Error", "esp32_panic"),
    ("MemoryError", "memory_error"),
    ("ENOMEM", "memory_error"),
    ("ValueError:", "python_value_error"),
    ("OSError:", "python_os_error"),
    ("ImportError:", "python_import_error"),
    ("AttributeError:", "python_attribute_error"),
]
FORBIDDEN_UPLOAD_TARGETS = {
    ":main.mpy",
    ":conf.mpy",
    ":boot.mpy",
}
FORBIDDEN_UPLOAD_SUFFIXES = (
    "/mock.py",
    "/mock.mpy",
    ".pyc",
)


def load_optional(path: str | None, label: str, errors: list[dict[str, Any]]) -> dict[str, Any]:
    if not path:
        return {}
    try:
        data = load_json(path)
    except FileNotFoundError:
        errors.append({"code": f"{label}_json_missing", "path": path, "message": f"{label} JSON file was not found"})
        return {}
    except json.JSONDecodeError as exc:
        errors.append({"code": f"{label}_json_invalid", "path": path, "message": str(exc)})
        return {}
    except OSError as exc:
        errors.append({"code": f"{label}_json_unreadable", "path": path, "message": str(exc)})
        return {}
    return data if isinstance(data, dict) else {}


def infer_status(report: dict[str, Any], default: str = "unknown") -> str:
    raw = report.get("status")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    if not report:
        return default
    errors = report.get("errors")
    if isinstance(errors, list) and errors:
        return "failed"
    failed = report.get("failed")
    try:
        if int(failed or 0) > 0:
            return "failed"
    except (TypeError, ValueError):
        pass
    return "success"


def text_contains_runtime_import_error(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    lowered = text.lower()
    return (
        "importerror" in lowered
        and ("no module named" in lowered or "cannot import name" in lowered)
        and ("unittest" in lowered or "micropython-lib" in lowered)
    )


def classify_device_tests(device_tests: dict[str, Any]) -> tuple[str, str]:
    if text_contains_runtime_import_error(device_tests):
        return "device_tests_runtime_unavailable", "device-side tests could not import a required runtime dependency"
    errors = device_tests.get("errors")
    if isinstance(errors, list):
        codes = {item.get("code") for item in errors if isinstance(item, dict)}
        if codes & {"device_tests_runtime_unavailable", "runtime_dependency_missing", "mpremote_unavailable"}:
            return "device_tests_runtime_unavailable", "device-side tests runtime is unavailable"
        if codes & {"device_tests_contract_failed", "device_test_assertion_failed"}:
            return "device_tests_contract_failed", "device-side contract tests failed"
    text = json.dumps(device_tests, ensure_ascii=False).lower()
    if "assertionerror" in text or "\nfail:" in text or " failed" in text:
        return "device_tests_contract_failed", "device-side contract tests failed"
    return "device_tests_failed", "device-side tests failed"


def _target_for_uploaded_item(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        target = item.get("target") or item.get("remote") or item.get("path")
        if isinstance(target, str):
            return target
    return None


def _source_for_uploaded_item(item: Any) -> str | None:
    if isinstance(item, dict):
        source = item.get("source") or item.get("src") or item.get("local")
        if isinstance(source, str):
            return source
    return None


def upload_targets(upload: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for item in upload.get("uploaded_files") or []:
        target = _target_for_uploaded_item(item)
        if target:
            targets.append(target)
    for step in upload.get("steps") or []:
        if not isinstance(step, dict):
            continue
        command = step.get("command")
        if not isinstance(command, list) or "cp" not in command:
            continue
        for arg in reversed(command):
            if isinstance(arg, str) and arg.startswith(":"):
                targets.append(arg)
                break
    return targets


def upload_source_target_pairs(upload: dict[str, Any]) -> list[tuple[str | None, str]]:
    pairs: list[tuple[str | None, str]] = []
    for item in upload.get("uploaded_files") or []:
        target = _target_for_uploaded_item(item)
        if target:
            pairs.append((_source_for_uploaded_item(item), target))
    for step in upload.get("steps") or []:
        if not isinstance(step, dict):
            continue
        command = step.get("command")
        if not isinstance(command, list) or "cp" not in command:
            continue
        target = None
        source = None
        for arg in reversed(command):
            if isinstance(arg, str) and arg.startswith(":"):
                target = arg
                break
        try:
            cp_index = command.index("cp")
        except ValueError:
            cp_index = -1
        if cp_index >= 0 and cp_index + 1 < len(command):
            candidate = command[cp_index + 1]
            if isinstance(candidate, str):
                source = candidate
        if target:
            pairs.append((source, target))
    return pairs


def forbidden_uploads(upload: dict[str, Any]) -> list[str]:
    bad: list[str] = []
    for source, target in upload_source_target_pairs(upload):
        normalized = target.replace("\\", "/")
        path = normalized[1:] if normalized.startswith(":") else normalized
        normalized_source = (source or "").replace("\\", "/")
        if normalized in FORBIDDEN_UPLOAD_TARGETS:
            bad.append(normalized)
            continue
        if path.startswith("firmware/") or normalized_source.startswith("build/mpy/firmware/") or "/build/mpy/firmware/" in normalized_source:
            bad.append(normalized)
            continue
        if "__pycache__/" in path or path.endswith(".pyc") or "__pycache__/" in normalized_source or normalized_source.endswith(".pyc"):
            bad.append(normalized)
            continue
        if path.startswith("drivers/") and path.endswith(FORBIDDEN_UPLOAD_SUFFIXES):
            bad.append(normalized)
    return sorted(set(bad))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload-json")
    parser.add_argument("--clean-json")
    parser.add_argument("--serial-json")
    parser.add_argument("--log-report-json")
    parser.add_argument("--device-tests-json")
    parser.add_argument("--mip-install-json")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--port", default="")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    upload = load_optional(args.upload_json, "upload", errors)
    clean = load_optional(args.clean_json, "clean", errors)
    serial = load_optional(args.serial_json, "serial", errors)
    log_report = load_optional(args.log_report_json, "log_report", errors)
    device_tests = load_optional(args.device_tests_json, "device_tests", errors)
    mip_install = load_optional(args.mip_install_json, "mip_install", errors)

    upload_status = infer_status(upload, default="skipped")
    clean_status = infer_status(clean, default="skipped")
    if upload and upload_status not in {"success", "ok", "skipped"}:
        errors.append({"code": "upload_failed", "message": "upload script did not report success", "detail": upload})
    forbidden = forbidden_uploads(upload)
    if forbidden:
        errors.append(
            {
                "code": "forbidden_runtime_upload",
                "message": "upload included source-only or test/mock artifacts that must not be deployed",
                "targets": forbidden,
            }
        )
    if clean and clean_status not in {"success", "ok", "skipped"}:
        errors.append({"code": "clean_failed", "message": "clean script did not report success", "detail": clean})
    if mip_install:
        mip_status = infer_status(mip_install)
        if mip_status in {"action_required", "unavailable"}:
            errors.append(
                {
                    "code": "runtime_dependency_install_unavailable",
                    "message": "runtime dependency installation could not run",
                    "detail": mip_install,
                }
            )
        elif mip_status not in {"success", "ok", "skipped"}:
            mip_errors = mip_install.get("errors") if isinstance(mip_install.get("errors"), list) else []
            mip_codes = {item.get("code") for item in mip_errors if isinstance(item, dict)}
            code = (
                "runtime_dependency_install_network_unavailable"
                if "runtime_dependency_install_network_unavailable" in mip_codes
                else "runtime_dependency_install_failed"
            )
            errors.append(
                {
                    "code": code,
                    "message": "mpremote mip dependency installation failed; network/proxy/VPN may be unavailable" if code.endswith("network_unavailable") else "mpremote mip dependency installation failed",
                    "detail": mip_errors or mip_install,
                }
            )

    output = str(serial.get("output") or serial.get("stdout") or "")
    if serial and serial.get("status") != "success":
        errors.append({"code": "serial_capture_failed", "message": "serial capture failed", "detail": serial.get("errors")})
    if serial and serial.get("returncode") not in (None, 0):
        warnings.append(f"serial capture process exited with returncode {serial.get('returncode')}")
    if serial.get("stalled"):
        warnings.append("serial capture stalled before a ready marker")
    if serial and not output:
        warnings.append("serial capture produced no output")
    for pattern, code in FAIL_PATTERNS:
        if pattern in output:
            errors.append({"code": code, "message": f"serial output contains {pattern}"})

    error_count = log_report.get("error_count")
    if isinstance(error_count, int) and error_count > 0:
        errors.append({"code": "device_log_errors", "message": f"device log report has {error_count} errors", "detail": log_report.get("errors")})

    if device_tests:
        test_status = infer_status(device_tests)
        try:
            failed_count = int(device_tests.get("failed") or 0)
        except (TypeError, ValueError):
            failed_count = 1
        if test_status == "failed" or failed_count > 0:
            code, message = classify_device_tests(device_tests)
            errors.append(
                {
                    "code": code,
                    "message": message,
                    "detail": device_tests.get("errors") or device_tests.get("tests"),
                }
            )
        elif test_status == "skipped":
            warnings.append("device-side tests were skipped")
        elif test_status not in {"success", "ok"}:
            errors.append({"code": "device_tests_unavailable", "message": "device-side tests did not complete", "detail": device_tests})

    status = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    result: dict[str, Any] = {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": args.strategy,
        "port": args.port or None,
        "upload_result": upload,
        "clean_result": clean,
        "serial_excerpt": output[:2000],
        "serial_output_bytes": len(output.encode("utf-8", errors="replace")),
        "log_report": log_report,
        "mip_install": mip_install,
        "device_tests": device_tests,
        "errors": errors,
        "warnings": warnings,
    }
    if args.output_json:
        write_json(args.output_json, result)
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
