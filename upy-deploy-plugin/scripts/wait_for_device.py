#!/usr/bin/env python3
"""Wait until a MicroPython device responds after reset/re-enumeration."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from typing import Any

from common import configure_stdio, print_json, write_json
from mpremote_runtime import MpremoteUnavailable, run_mpremote


def probe(port: str | None, timeout_ms: int):
    return run_mpremote(port, ["resume", "exec", "print('MPYHW_PROBE_OK')"], timeout_ms)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--timeout-sec", type=float, default=None, help="Compatibility alias for --timeout-ms")
    parser.add_argument("--interval-ms", type=int, default=2000)
    parser.add_argument("--probe-timeout-ms", type=int, default=3000)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    args = parser.parse_args()
    if args.timeout_sec is not None:
        args.timeout_ms = int(args.timeout_sec * 1000)
    return args


def main() -> int:
    configure_stdio()
    args = parse_args()
    start = time.monotonic()
    attempts: list[dict[str, Any]] = []
    status = "failed"
    if args.mock:
        attempts.append({"attempt": 1, "returncode": 0, "stdout": "MPYHW_PROBE_OK\n", "stderr": ""})
        status = "success"
    else:
        attempt = 0
        deadline = start + args.timeout_ms / 1000
        while time.monotonic() < deadline:
            attempt += 1
            try:
                proc = probe(args.port or None, args.probe_timeout_ms)
            except MpremoteUnavailable as exc:
                attempts.append({"attempt": attempt, "returncode": None, "stdout": "", "stderr": exc.to_error()["message"]})
                result = {
                    "status": "action_required",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "port": args.port or None,
                    "duration_ms": int((time.monotonic() - start) * 1000),
                    "attempts": attempts,
                    "errors": [exc.to_error()],
                }
                if args.output_json:
                    write_json(args.output_json, result)
                print_json(result)
                return 2
            attempts.append({
                "attempt": attempt,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-1000:],
                "stderr": proc.stderr[-1000:],
            })
            if proc.returncode == 0 and "MPYHW_PROBE_OK" in proc.stdout:
                status = "success"
                break
            time.sleep(max(args.interval_ms, 1) / 1000)
    result = {
        "status": status,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "port": args.port or None,
        "duration_ms": int((time.monotonic() - start) * 1000),
        "attempts": attempts,
        "errors": [] if status == "success" else [{"code": "device_wait_timeout", "message": "device did not respond before timeout"}],
    }
    if args.output_json:
        write_json(args.output_json, result)
    print_json(result)
    return 0 if status == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
