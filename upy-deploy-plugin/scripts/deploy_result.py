#!/usr/bin/env python3
"""Combine upload, serial, and log reports into a deploy result."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

from common import configure_stdio, load_json, print_json, write_json


FAIL_PATTERNS = [
    ("Traceback (most recent call last)", "python_traceback"),
    ("rst cause:", "hardware_reset"),
    ("Guru Meditation Error", "esp32_panic"),
    ("MemoryError", "memory_error"),
    ("ENOMEM", "memory_error"),
]


def load_optional(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload-json")
    parser.add_argument("--clean-json")
    parser.add_argument("--serial-json")
    parser.add_argument("--log-report-json")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--port", default="")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    upload = load_optional(args.upload_json)
    clean = load_optional(args.clean_json)
    serial = load_optional(args.serial_json)
    log_report = load_optional(args.log_report_json)
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []

    if upload and upload.get("status") not in {"success", "ok", "skipped"}:
        errors.append({"code": "upload_failed", "message": "upload script did not report success", "detail": upload})
    if clean and clean.get("status") not in {"success", "ok"}:
        errors.append({"code": "clean_failed", "message": "clean script did not report success", "detail": clean})

    output = str(serial.get("output") or serial.get("stdout") or "")
    if serial and serial.get("status") != "success":
        errors.append({"code": "serial_capture_failed", "message": "serial capture failed", "detail": serial.get("errors")})
    if serial.get("stalled"):
        warnings.append("serial capture stalled before a ready marker")
    if serial and not output:
        errors.append({"code": "serial_no_output", "message": "serial capture produced no output"})
    for pattern, code in FAIL_PATTERNS:
        if pattern in output:
            errors.append({"code": code, "message": f"serial output contains {pattern}"})

    error_count = log_report.get("error_count")
    if isinstance(error_count, int) and error_count > 0:
        errors.append({"code": "device_log_errors", "message": f"device log report has {error_count} errors", "detail": log_report.get("errors")})

    status = "FAIL" if errors else "PASS"
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
        "errors": errors,
        "warnings": warnings,
    }
    if args.output_json:
        write_json(args.output_json, result)
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
