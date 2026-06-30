#!/usr/bin/env python3
"""Run generated MicroPython device-side unittest files through mpremote."""

from __future__ import annotations

import argparse
import fnmatch
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
DEFAULT_TEMP_UPLOAD_PATTERNS = (
    "firmware/drivers/*/mock.py",
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


def posix_rel(project_root: Path, path: Path) -> str:
    return rel_path(project_root, path).replace("\\", "/")


def find_temp_uploads(project_root: Path, patterns: list[str]) -> list[tuple[Path, str]]:
    uploads: list[tuple[Path, str]] = []
    for path in sorted(project_root.rglob("mock.py")):
        rel = posix_rel(project_root, path)
        if not any(fnmatch.fnmatch(rel, pattern) for pattern in patterns):
            continue
        if rel.startswith("firmware/"):
            remote = ":" + rel[len("firmware/"):]
        else:
            remote = ":" + rel
        uploads.append((path.resolve(), remote.replace("\\", "/")))
    return uploads


def remote_parent_dirs(remote: str) -> list[str]:
    rel = remote[1:] if remote.startswith(":") else remote
    parent = str(Path(rel).parent).replace("\\", "/")
    if not parent or parent == ".":
        return []
    parts = [part for part in parent.split("/") if part]
    return [":" + "/".join(parts[:index]) for index in range(1, len(parts) + 1)]


def mock_temp_artifacts(project_root: Path, patterns: list[str]) -> dict[str, Any]:
    uploads = [
        {
            "source": posix_rel(project_root, source),
            "target": target,
            "upload": {"ok": True, "returncode": 0},
            "cleanup": {"ok": True, "returncode": 0},
            "cleanup_verify": {"ok": True, "returncode": 1, "status": "absent"},
        }
        for source, target in find_temp_uploads(project_root, patterns)
    ]
    return {
        "status": "success",
        "enabled": bool(patterns),
        "patterns": patterns,
        "uploads": uploads,
        "uploaded": len(uploads),
        "cleaned": len(uploads),
        "errors": [],
    }


def mock_result(project_root: Path, output_json: str | None, temp_upload_patterns: list[str]) -> dict[str, Any]:
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
        "temp_artifacts": mock_temp_artifacts(project_root, temp_upload_patterns),
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


def temp_upload_setup(project_root: Path, port: str, timeout_ms: int, patterns: list[str]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for source, target in find_temp_uploads(project_root, patterns):
        record: dict[str, Any] = {
            "source": posix_rel(project_root, source),
            "target": target,
        }
        for remote_dir in remote_parent_dirs(target):
            mkdir = run_mpremote(port, ["resume", "fs", "mkdir", remote_dir], timeout_ms, check=False)
            record.setdefault("mkdir", []).append(
                {
                    "target": remote_dir,
                    "returncode": mkdir.returncode,
                    "stdout_excerpt": excerpt(mkdir.stdout, 1000),
                    "stderr_excerpt": excerpt(mkdir.stderr, 1000),
                }
            )
        uploaded = run_mpremote(port, ["resume", "fs", "cp", str(source), target], timeout_ms, check=False)
        upload_ok = uploaded.returncode == 0
        record["upload"] = {
            "ok": upload_ok,
            "returncode": uploaded.returncode,
            "stdout_excerpt": excerpt(uploaded.stdout),
            "stderr_excerpt": excerpt(uploaded.stderr),
        }
        if not upload_ok:
            errors.append(
                {
                    "code": "device_test_temp_upload_failed",
                    "source": record["source"],
                    "target": target,
                    "message": "failed to upload temporary device-test mock artifact",
                }
            )
        records.append(record)
    return {
        "status": "failed" if errors else "success",
        "enabled": bool(patterns),
        "patterns": patterns,
        "uploads": records,
        "uploaded": sum(1 for item in records if (item.get("upload") or {}).get("ok")),
        "errors": errors,
    }


def temp_upload_cleanup(port: str, timeout_ms: int, setup: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item in setup.get("uploads") or []:
        if not isinstance(item, dict) or not (item.get("upload") or {}).get("ok"):
            continue
        target = item.get("target")
        if not isinstance(target, str):
            continue
        cleanup = run_mpremote(port, ["resume", "fs", "rm", target], timeout_ms, check=False)
        verify = run_mpremote(port, ["resume", "fs", "ls", target], timeout_ms, check=False)
        cleanup_ok = cleanup.returncode == 0
        absent = verify.returncode != 0
        record = {
            "target": target,
            "cleanup": {
                "ok": cleanup_ok,
                "returncode": cleanup.returncode,
                "stdout_excerpt": excerpt(cleanup.stdout),
                "stderr_excerpt": excerpt(cleanup.stderr),
            },
            "cleanup_verify": {
                "ok": absent,
                "returncode": verify.returncode,
                "stdout_excerpt": excerpt(verify.stdout),
                "stderr_excerpt": excerpt(verify.stderr),
                "status": "absent" if absent else "still_present",
            },
        }
        if not cleanup_ok or not absent:
            errors.append(
                {
                    "code": "device_test_temp_cleanup_failed",
                    "target": target,
                    "message": "temporary device-test mock artifact was not removed cleanly",
                }
            )
        records.append(record)
    return {
        "status": "failed" if errors else "success",
        "cleanups": records,
        "cleaned": sum(1 for item in records if (item.get("cleanup") or {}).get("ok")),
        "errors": errors,
    }


def run_tests(project_root: Path, port: str, timeout_ms: int, temp_upload_patterns: list[str]) -> dict[str, Any]:
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
    temp_setup = temp_upload_setup(project_root, port, timeout_ms, temp_upload_patterns)
    test_runner_errors: list[dict[str, Any]] = []
    try:
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
    except Exception as exc:
        test_runner_errors.append(
            {
                "code": "device_tests_runner_failed",
                "message": str(exc),
            }
        )
    finally:
        temp_cleanup = temp_upload_cleanup(port, timeout_ms, temp_setup)
    failed = [record for record in records if record["status"] != "passed"]
    temp_errors = list(temp_setup.get("errors") or []) + list(temp_cleanup.get("errors") or [])
    return {
        "status": "failed" if failed or temp_errors or test_runner_errors else "success",
        "mode": "live",
        "generated_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "port": port,
        "test_count": len(records),
        "passed": len(records) - len(failed),
        "failed": len(failed),
        "tests": records,
        "temp_artifacts": {
            "status": "failed" if temp_errors else "success",
            "enabled": bool(temp_upload_patterns),
            "patterns": temp_upload_patterns,
            "setup": temp_setup,
            "cleanup": temp_cleanup,
            "errors": temp_errors,
        },
        "errors": [
            {
                "code": classify_failure(record),
                "path": record["path"],
                "message": failure_message(record),
            }
            for record in failed
        ] + test_runner_errors + temp_errors,
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
    parser.add_argument(
        "--temp-upload-pattern",
        action="append",
        default=None,
        help="Project-local glob for temporary device-test artifacts. Use 'none' to disable defaults.",
    )
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--log-file")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    temp_upload_patterns = list(DEFAULT_TEMP_UPLOAD_PATTERNS)
    if args.temp_upload_pattern:
        temp_upload_patterns = []
        for pattern in args.temp_upload_pattern:
            if pattern.lower() == "none":
                continue
            temp_upload_patterns.append(pattern.replace("\\", "/"))
    try:
        if args.mock:
            result = mock_result(project_root, args.output_json, temp_upload_patterns)
        elif not args.port:
            result = {
                "status": "action_required",
                "errors": [{"code": "port_required", "message": "--port is required unless --mock is used"}],
            }
        else:
            result = run_tests(project_root, args.port, args.timeout_ms, temp_upload_patterns)
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
