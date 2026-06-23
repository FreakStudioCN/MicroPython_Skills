#!/usr/bin/env python3
"""Run a Python file on a MicroPython device through mpremote.

This helper is bundled with upy-scaffold-plugin so generated projects can copy
it into .upy/scripts without depending on the original upy-deploy skill tree.
It sends one local .py file to the device REPL with `mpremote run`, captures
output, and optionally writes a log plus JSON summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_log_name(source: Path) -> str:
    stem = source.stem or "device_run"
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem)
    return f"{cleaned}_{utc_stamp()}.log"


def build_command(port: Optional[str], file_path: Path) -> list[str]:
    command = ["mpremote"]
    if port:
        command.extend(["connect", port])
    command.extend(["run", str(file_path)])
    return command


def write_log(
    log_dir: Path,
    source: Path,
    command: list[str],
    result: subprocess.CompletedProcess[str],
    duration_ms: int,
) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    output_path = log_dir / safe_log_name(source)
    content = [
        "# run_on_device log",
        f"timestamp: {datetime.now(timezone.utc).isoformat()}",
        f"command: {' '.join(command)}",
        f"exit_code: {result.returncode}",
        f"duration_ms: {duration_ms}",
        "",
        "## stdout",
        result.stdout or "",
        "",
        "## stderr",
        result.stderr or "",
        "",
    ]
    output_path.write_text("\n".join(content), encoding="utf-8")
    return output_path


def summary(
    status: str,
    result: subprocess.CompletedProcess[str],
    duration_ms: int,
    output_file: Optional[Path],
    errors: list[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "exit_code": result.returncode,
        "duration_ms": duration_ms,
        "stdout_bytes": len((result.stdout or "").encode("utf-8", errors="ignore")),
        "stderr_bytes": len((result.stderr or "").encode("utf-8", errors="ignore")),
        "errors": errors,
    }
    if output_file is not None:
        payload["output_file"] = str(output_file).replace("\\", "/")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a MicroPython .py file on a device through mpremote")
    parser.add_argument("--com", "--port", dest="port", default=None, help="serial port, for example COM3 or /dev/ttyACM0")
    parser.add_argument("--file", required=True, help="local .py file to execute")
    parser.add_argument("--capture", action="store_true", help="write stdout/stderr to a log file")
    parser.add_argument("--log-dir", default="logs", help="directory for captured logs")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="execution timeout in milliseconds")
    parser.add_argument("--json-summary", action="store_true", help="print JSON summary to stdout")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = parse_args()
    file_path = Path(args.file)
    if not file_path.exists():
        errors = [f"file not found: {file_path}"]
        dummy = subprocess.CompletedProcess(args=["mpremote"], returncode=2, stdout="", stderr=errors[0])
        if args.json_summary:
            print(json.dumps(summary("error", dummy, 0, None, errors), ensure_ascii=False))
        else:
            print(errors[0], file=sys.stderr)
        return 2
    if file_path.suffix.lower() != ".py":
        errors = [f"--file must point to a .py file: {file_path}"]
        dummy = subprocess.CompletedProcess(args=["mpremote"], returncode=2, stdout="", stderr=errors[0])
        if args.json_summary:
            print(json.dumps(summary("error", dummy, 0, None, errors), ensure_ascii=False))
        else:
            print(errors[0], file=sys.stderr)
        return 2

    command = build_command(args.port, file_path)
    start = time.monotonic()
    errors: list[str] = []
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(args.timeout_ms, 1) / 1000,
            check=False,
        )
    except FileNotFoundError:
        message = "mpremote executable not found"
        result = subprocess.CompletedProcess(command, returncode=127, stdout="", stderr=message)
        errors.append(message)
    except subprocess.TimeoutExpired as exc:
        message = f"device execution timed out after {args.timeout_ms} ms"
        result = subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=((exc.stderr or "") + "\n" + message).strip(),
        )
        errors.append(message)

    duration_ms = int((time.monotonic() - start) * 1000)
    if result.returncode != 0 and not errors:
        errors.append("mpremote run returned non-zero exit code")

    output_file = None
    if args.capture:
        output_file = write_log(Path(args.log_dir), file_path, command, result, duration_ms)

    status = "ok" if result.returncode == 0 else "error"
    if args.json_summary:
        print(json.dumps(summary(status, result, duration_ms, output_file, errors), ensure_ascii=False))
    else:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if output_file is not None:
            print(f"\n[run_on_device] log: {output_file}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
