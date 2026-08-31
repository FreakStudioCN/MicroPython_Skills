#!/usr/bin/env python3
"""Combine upload, serial, and log reports into a deploy result."""

from __future__ import annotations

import argparse
import json
import re
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
SENSOR_TIMEOUT_MARKERS = (
    "ETIMEDOUT",
    "[Errno 110]",
)
SENSOR_READING_PATTERNS = (
    re.compile(r"\b(?:temp|temperature|humidity|rh)\b\s*(?:=|:)\s*-?\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"\b(?:read|sample|measurement)\b.*\b(?:ok|success|succeeded)\b", re.IGNORECASE),
)
SUCCESS_STATUSES = {"success", "ok"}
FIRMWARE_TRACEBACK_FILES = {"main.py", "boot.py", "conf.py"}
TRACEBACK_FRAME_RE = re.compile(r'File "([^"]+)"')
SOFT_REBOOT_MARKER = "MPY: soft reboot"
BOOT_MARKERS = ("MPYHW_READY", "starting scheduler")
TRACEBACK_MARKER = "Traceback (most recent call last)"


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


def report_output(report: dict[str, Any]) -> str:
    return str(report.get("output") or report.get("stdout") or "")


def compact_capture(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {}
    result = dict(report)
    output = report_output(report)
    if output:
        result["output_excerpt"] = output[:2000]
        result["output_bytes"] = len(output.encode("utf-8", errors="replace"))
        result.pop("output", None)
        result.pop("stdout", None)
    return result


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


def sensor_timeout_count(output: str) -> int:
    count = 0
    for line in output.splitlines():
        if any(marker in line for marker in SENSOR_TIMEOUT_MARKERS):
            count += 1
    return count


def has_successful_sensor_reading(output: str) -> bool:
    for line in output.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in ("failed", "error", "timeout", "boot", "driver ready", "scheduler")):
            continue
        if any(pattern.search(line) for pattern in SENSOR_READING_PATTERNS):
            return True
        if re.search(r"\b(?:t|temp)\s*=\s*-?\d", line, re.IGNORECASE) and re.search(
            r"\b(?:h|rh|humidity)\s*=\s*-?\d", line, re.IGNORECASE
        ):
            return True
    return False


def has_firmware_traceback(output: str) -> bool:
    if TRACEBACK_MARKER not in output:
        return False
    for match in TRACEBACK_FRAME_RE.finditer(output):
        frame = match.group(1).replace("\\", "/").rsplit("/", 1)[-1]
        if frame in FIRMWARE_TRACEBACK_FILES:
            return True
    return False


def _traceback_recovered(segment: str) -> bool:
    reboot = segment.find(SOFT_REBOOT_MARKER)
    if reboot < 0:
        return False
    tail = segment[reboot:]
    return any(marker in tail for marker in BOOT_MARKERS)


def all_tracebacks_recovered_after_interrupt(output: str) -> bool:
    """True when every traceback is followed by a reboot and firmware startup marker.

    The final reset intentionally interrupts a running app before sending Ctrl-D. That interrupt
    can produce a traceback whose frames name main.py, so frame matching alone cannot distinguish it
    from a startup crash. Recovery is proven per traceback by ordering: traceback, soft reboot, then
    boot marker, before any later traceback appears.
    """
    starts = [match.start() for match in re.finditer(re.escape(TRACEBACK_MARKER), output)]
    if not starts:
        return False
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(output)
        if not _traceback_recovered(output[start:end]):
            return False
    return True


def validate_capture_health(
    output: str,
    errors: list[dict[str, Any]],
    warnings: list[str],
    *,
    prefix: str,
    empty_code: str,
) -> None:
    if not output:
        errors.append({"code": empty_code, "message": f"{prefix} capture produced no output"})
        return
    timeout_count = sensor_timeout_count(output)
    if timeout_count >= 2:
        if has_successful_sensor_reading(output):
            warnings.append(
                f"{prefix} output reported {timeout_count} sensor I/O timeout(s) but also captured a successful reading"
            )
        else:
            errors.append(
                {
                    "code": "device_io_timeout",
                    "message": f"{prefix} output reports repeated sensor I/O timeouts and no successful reading",
                    "timeout_count": timeout_count,
                }
            )
    elif timeout_count == 1:
        warnings.append(f"{prefix} output reported one sensor I/O timeout")
    recovered_after_interrupt = all_tracebacks_recovered_after_interrupt(output)
    for pattern, code in FAIL_PATTERNS:
        if pattern not in output:
            continue
        if code == "python_traceback" and recovered_after_interrupt:
            warnings.append(
                f"{prefix} output contains an interrupt traceback followed by soft reboot and boot marker"
            )
            continue
        errors.append({"code": code, "message": f"{prefix} output contains {pattern}"})


def artifact_time(artifact: dict[str, Any] | None, *keys: str) -> datetime | None:
    """The newest timezone-aware timestamp an artifact reports, or None.

    Parsed, not string-compared. A stamp that is missing, unparseable, or naive is treated
    as "no evidence of when", never as "earlier".
    """
    if not isinstance(artifact, dict):
        return None
    seen: list[datetime] = []
    for key in keys:
        raw = artifact.get(key)
        if not isinstance(raw, str):
            continue
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            seen.append(parsed)
    return max(seen) if seen else None


def validate_final_reset_is_last(
    final_reset: dict[str, Any],
    others: dict[str, dict[str, Any] | None],
    errors: list[dict[str, Any]],
) -> None:
    """The final reset must be the LAST thing that touched the board.

    This can only see artifacts it is handed. The SKILL rule that final reset is the last
    device operation closes non-artifact gaps; this catches ordered artifacts that prove a
    later device operation occurred.
    """
    reset_at = artifact_time(final_reset, "finished_at", "generated_at", "started_at")
    if not reset_at:
        return
    for name, artifact in others.items():
        other_at = artifact_time(artifact, "generated_at", "finished_at")
        if not other_at or other_at <= reset_at:
            continue
        errors.append(
            {
                "code": "final_reset_not_last",
                "message": (
                    f"{name} is stamped {other_at.isoformat()}, AFTER the final reset at "
                    f"{reset_at.isoformat()}, so the reset was not the last step. Anything that "
                    "reaches the board after it -- device tests, a log pull, a re-probe, any "
                    "mpremote fs call -- re-enters the raw REPL and stops main.py, leaving the "
                    "board idle. Run capture_repl.py --reset-first LAST, after the tests and after "
                    "any log download, then pass that capture as --final-reset-json."
                ),
            }
        )


def validate_final_reset(
    final_reset: dict[str, Any],
    errors: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    output = report_output(final_reset)
    final_status = infer_status(final_reset)
    if final_status not in SUCCESS_STATUSES:
        errors.append(
            {
                "code": "final_reset_failed",
                "message": "final reset capture did not report success",
                "detail": final_reset.get("errors"),
            }
        )
    if final_reset.get("reset_first") is not True:
        errors.append(
            {
                "code": "final_reset_not_reset_first",
                "message": "final reset capture must run capture_repl.py --reset-first after upload and device tests",
            }
        )
    elif not (final_reset.get("observed_soft_reboot") is True or final_reset.get("observed_fresh_boot") is True):
        errors.append(
            {
                "code": "final_reset_soft_reboot_not_observed",
                "message": (
                    "final reset requested Ctrl-D but the capture observed neither 'MPY: soft reboot' nor the "
                    "firmware's own startup marker, so nothing shows the board restarted. On a board behind a "
                    "USB-serial bridge the port open already reset it and Ctrl-D reaches a running main.py "
                    "instead of an idle REPL, so the soft-reboot line never appears and the startup marker is "
                    "the evidence to look for. A capture holding only task output attached to an app that was "
                    "already running: re-run capture_repl.py --reset-first as the final device operation."
                ),
            }
        )
    final_reset_firmware_traceback = has_firmware_traceback(output)
    if final_reset.get("stalled") and not final_reset_firmware_traceback:
        errors.append(
            {
                "code": "final_reset_capture_stalled",
                "matched_stop": final_reset.get("matched_stop"),
                "output_bytes": len(report_output(final_reset).encode("utf-8", errors="replace")),
                "message": (
                    "final reset capture stalled: output arrived but no stop pattern matched "
                    "(capture_repl.py defaults: 'MPYHW_READY', 'starting scheduler') and the board then "
                    "went quiet past the idle threshold. Either make firmware/main.py print one of those "
                    "markers at startup, or re-run capture_repl.py --reset-first "
                    "--stop-pattern '<a line main.py actually prints>' - and run it LAST, after tests and "
                    "log pulls, since any later mpremote fs call re-enters the REPL and stops main.py."
                ),
            }
        )
    if final_reset.get("returncode") not in (None, 0):
        warnings.append(f"final reset capture process exited with returncode {final_reset.get('returncode')}")
    validate_capture_health(output, errors, warnings, prefix="final reset", empty_code="final_reset_capture_empty")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload-json")
    parser.add_argument("--clean-json")
    parser.add_argument("--serial-json")
    parser.add_argument("--final-reset-json")
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
    final_reset = load_optional(args.final_reset_json, "final_reset", errors)
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

    output = report_output(serial)
    if serial and serial.get("status") != "success":
        errors.append({"code": "serial_capture_failed", "message": "serial capture failed", "detail": serial.get("errors")})
    if serial and serial.get("returncode") not in (None, 0):
        warnings.append(f"serial capture process exited with returncode {serial.get('returncode')}")
    serial_firmware_traceback = has_firmware_traceback(output)
    if serial.get("stalled") and not serial_firmware_traceback:
        errors.append(
            {
                "code": "serial_capture_stalled",
                "matched_stop": serial.get("matched_stop"),
                "message": (
                    "serial capture stalled: the 'stalled' flag in the --serial-json artifact means output "
                    "arrived but none of capture_repl.py's stop patterns ('MPYHW_READY', 'starting scheduler' "
                    "by default) ever matched and the board then went quiet past the idle threshold. Either "
                    "make firmware/main.py print one of those markers, or re-run capture_repl.py with "
                    "--stop-pattern '<a line main.py actually prints>'."
                ),
            }
        )
    if serial:
        validate_capture_health(output, errors, warnings, prefix="serial", empty_code="serial_capture_empty")

    error_count = log_report.get("error_count")
    if isinstance(error_count, int) and error_count > 0:
        errors.append({"code": "device_log_errors", "message": f"device log report has {error_count} errors", "detail": log_report.get("errors")})

    # A device-test artifact requires the reset whatever its status, not only on success.
    final_reset_required = upload_status in SUCCESS_STATUSES or bool(device_tests)
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
        if test_status in SUCCESS_STATUSES:
            final_reset_required = True

    final_reset_output = ""
    if final_reset:
        final_reset_output = validate_final_reset(final_reset, errors, warnings)
        # Order, not just presence: see validate_final_reset_is_last.
        validate_final_reset_is_last(
            final_reset,
            {"device tests": device_tests, "device log report": log_report},
            errors,
        )
    elif final_reset_required and not args.final_reset_json:
        errors.append(
            {
                "code": "final_reset_missing",
                "message": (
                    "upload and device tests can leave the board in raw REPL; run capture_repl.py "
                    "--reset-first as the final device operation and pass --final-reset-json before "
                    "reporting deploy success"
                ),
            }
        )

    steps = [step for step in upload.get("steps", []) if isinstance(step, dict)]
    if final_reset:
        steps.append(
            {
                "type": "final_reset",
                "status": infer_status(final_reset),
                "reset_first": final_reset.get("reset_first"),
                "matched_stop": final_reset.get("matched_stop"),
            }
        )

    status = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    result: dict[str, Any] = {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": args.strategy,
        "port": args.port or None,
        "upload_result": upload,
        "clean_result": clean,
        "steps": steps,
        "serial_excerpt": output[:2000],
        "serial_output_bytes": len(output.encode("utf-8", errors="replace")),
        "final_reset": compact_capture(final_reset),
        "final_reset_excerpt": final_reset_output[:2000],
        "final_reset_output_bytes": len(final_reset_output.encode("utf-8", errors="replace")),
        "log_report": log_report,
        "mip_install": mip_install,
        "device_tests": device_tests,
        "errors": errors,
        "warnings": warnings,
    }
    if args.output_json:
        write_json(args.output_json, result)
    print_json(result)
    return 2 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
