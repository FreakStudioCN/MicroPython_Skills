#!/usr/bin/env python3
"""Run generated MicroPython device-side unittest files through mpremote."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import configure_stdio, print_json, write_json
from mpremote_runtime import MpremoteUnavailable, run_mpremote


TEST_PATTERNS = (
    "device/tests/test_*.py",
    "test/device/test_*.py",
)


def excerpt(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit]


def find_tests(project_root: Path) -> list[Path]:
    tests: list[Path] = []
    for pattern in TEST_PATTERNS:
        tests.extend(sorted(project_root.glob(pattern)))
    return sorted({path.resolve() for path in tests})


def rel_path(project_root: Path, path: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def mock_result(project_root: Path, output_json: str | None) -> dict[str, Any]:
    tests = find_tests(project_root)
    records = [
        {
            "path": rel_path(project_root, path),
            "status": "passed",
            "returncode": 0,
            "stdout_excerpt": "mock device test passed\n",
            "stderr_excerpt": "",
            "duration_ms": 1,
        }
        for path in tests
    ]
    return {
        "status": "success" if tests else "skipped",
        "mode": "mock",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "test_count": len(tests),
        "passed": len(tests),
        "failed": 0,
        "tests": records,
        "output_json": output_json,
    }


def render_log(result: dict[str, Any]) -> str:
    lines = [
        f"status={result.get('status')}",
        f"test_count={result.get('test_count', 0)}",
        f"passed={result.get('passed', 0)}",
        f"failed={result.get('failed', 0)}",
    ]
    for item in result.get("tests", []):
        if not isinstance(item, dict):
            continue
        lines.append(
            "{path} [{status}] rc={returncode} {duration_ms}ms".format(
                path=item.get("path", ""),
                status=item.get("status", "unknown"),
                returncode=item.get("returncode", ""),
                duration_ms=item.get("duration_ms", ""),
            )
        )
        stdout_excerpt = item.get("stdout_excerpt") or ""
        stderr_excerpt = item.get("stderr_excerpt") or ""
        if stdout_excerpt:
            lines.append("stdout:")
            lines.append(stdout_excerpt.rstrip())
        if stderr_excerpt:
            lines.append("stderr:")
            lines.append(stderr_excerpt.rstrip())
    errors = result.get("errors") or []
    if errors:
        lines.append("errors:")
        for item in errors:
            if isinstance(item, dict):
                lines.append(f"- {item.get('code', 'error')}: {item.get('message', '')}")
    return "\n".join(lines) + "\n"


def run_tests(project_root: Path, port: str, timeout_ms: int) -> dict[str, Any]:
    tests = find_tests(project_root)
    records: list[dict[str, Any]] = []
    started = datetime.now(timezone.utc).isoformat()
    if not tests:
        return {
            "status": "skipped",
            "mode": "live",
            "generated_at": started,
            "project_root": str(project_root),
            "port": port,
            "test_count": 0,
            "passed": 0,
            "failed": 0,
            "tests": [],
            "warnings": [{"code": "device_tests_not_found", "message": "no device-side unittest files were found"}],
        }
    for path in tests:
        begin = time.monotonic()
        completed = run_mpremote(port, ["run", str(path)], timeout_ms, check=False)
        duration_ms = int((time.monotonic() - begin) * 1000)
        passed = completed.returncode == 0
        records.append(
            {
                "path": rel_path(project_root, path),
                "status": "passed" if passed else "failed",
                "returncode": completed.returncode,
                "stdout_excerpt": excerpt(completed.stdout),
                "stderr_excerpt": excerpt(completed.stderr),
                "duration_ms": duration_ms,
            }
        )
    failed = [record for record in records if record["status"] != "passed"]
    return {
        "status": "failed" if failed else "success",
        "mode": "live",
        "generated_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "port": port,
        "test_count": len(records),
        "passed": len(records) - len(failed),
        "failed": len(failed),
        "tests": records,
        "errors": [
            {
                "code": classify_failure(record),
                "path": record["path"],
                "message": failure_message(record),
            }
            for record in failed
        ],
    }


def failure_text(record: dict[str, Any]) -> str:
    return f"{record.get('stdout_excerpt') or ''}\n{record.get('stderr_excerpt') or ''}"


def classify_failure(record: dict[str, Any]) -> str:
    text = failure_text(record).lower()
    if "importerror" in text and "no module named" in text:
        return "device_tests_runtime_unavailable"
    if "mpremote" in text and ("could not" in text or "failed" in text or "permission denied" in text):
        return "device_tests_runtime_unavailable"
    if "assertionerror" in text or "\nfail:" in text or "\nfailed" in text:
        return "device_tests_contract_failed"
    return "device_test_failed"


def failure_message(record: dict[str, Any]) -> str:
    code = classify_failure(record)
    if code == "device_tests_runtime_unavailable":
        return "device-side test runtime dependency or mpremote execution is unavailable"
    if code == "device_tests_contract_failed":
        return "device-side contract test failed"
    return "device-side unittest failed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--port", default="")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--log-file")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    try:
        if args.mock:
            result = mock_result(project_root, args.output_json)
        elif not args.port:
            result = {
                "status": "action_required",
                "errors": [{"code": "port_required", "message": "--port is required unless --mock is used"}],
            }
        else:
            result = run_tests(project_root, args.port, args.timeout_ms)
    except MpremoteUnavailable as exc:
        result = {"status": "action_required", "errors": [exc.to_error()]}
    except Exception as exc:
        result = {"status": "failed", "errors": [{"code": "device_tests_runner_failed", "message": str(exc)}]}
    if args.output_json:
        if args.log_file:
            result["log_file"] = str(Path(args.log_file).resolve()).replace("\\", "/")
        write_json(args.output_json, result)
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(render_log(result), encoding="utf-8")
        result["log_file"] = str(log_path.resolve()).replace("\\", "/")
    print_json(result)
    first_error = (result.get("errors") or [{}])[0]
    completed_failure_codes = {
        "device_test_failed",
        "device_tests_runtime_unavailable",
        "device_tests_contract_failed",
    }
    if result["status"] in {"success", "skipped"}:
        return 0
    if result["status"] == "failed" and result.get("test_count") is not None:
        codes = {item.get("code") for item in result.get("errors", []) if isinstance(item, dict)}
        if codes and codes <= completed_failure_codes:
            return 0
    if result["status"] == "failed" and first_error.get("code") == "port_required":
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
