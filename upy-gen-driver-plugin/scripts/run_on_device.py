#!/usr/bin/env python3
"""Run a MicroPython file on a connected device through mpremote and capture logs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a MicroPython file via mpremote")
    parser.add_argument("--com", required=True, help="Serial port, for example COM3")
    parser.add_argument("--file", required=True, help="Python file to run")
    parser.add_argument("--capture", action="store_true", help="Write stdout/stderr to a log file")
    parser.add_argument("--log", help="Output log path")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--json-summary", action="store_true")
    parser.add_argument("--mpremote", default="mpremote")
    args = parser.parse_args()

    timeout = max(1, args.timeout_ms / 1000.0)
    start = time.monotonic()
    command = [args.mpremote, "connect", args.com, "resume", "run", args.file]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        completed = None
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
    else:
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    duration_ms = int((time.monotonic() - start) * 1000)
    log_path = args.log
    if args.capture and not log_path:
        stem = Path(args.file).stem
        log_path = str(Path("logs") / f"{stem}_run.log")
    if args.capture and log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "COMMAND: " + " ".join(command) + "\n"
            + f"TIMEOUT_MS: {args.timeout_ms}\n"
            + f"DURATION_MS: {duration_ms}\n"
            + "STDOUT:\n" + stdout + "\n"
            + "STDERR:\n" + stderr + "\n",
            encoding="utf-8",
        )
    exit_code = 124 if timed_out else int(completed.returncode if completed is not None else 1)
    status = "timeout" if timed_out else ("ok" if exit_code == 0 else "error")
    summary = {
        "status": status,
        "command": command,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "output_file": log_path,
        "stdout_excerpt": stdout[-2000:],
        "stderr_excerpt": stderr[-2000:],
        "self_test_pass": "SELF_TEST_PASS" in stdout,
    }
    if args.json_summary:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
