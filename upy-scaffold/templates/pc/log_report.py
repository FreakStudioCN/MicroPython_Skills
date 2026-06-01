#!/usr/bin/env python3
"""Parse rotating log output into a JSON test report.

Usage:
    python log_report.py --log-file output.log           # from file
    python log_report.py --input <(read_device_log.py)   # piped from device (bash)
"""

import json
import re
import sys
import argparse
from datetime import datetime, timezone


_ERROR_PATTERNS = [
    (re.compile(r"__MPY_ERR__:(.*)"), "P0_INJECTED"),
    (re.compile(r"Traceback \(most recent call last\):([\s\S]*?)(?=\n\S|\Z)"), "P0_TRACEBACK"),
    (re.compile(r"rst cause:(\d+)"), "P1_WDT_RESET"),
    (re.compile(r"Guru Meditation Error:.*"), "P1_GURU_MEDITATION"),
    (re.compile(r"\[FAIL\]\s*(.*)"), "P2_FAIL"),
    (re.compile(r"\[ERROR\]\s*(.*)"), "P2_ERROR"),
    (re.compile(r"MemoryError"), "P1_MEMORY"),
    (re.compile(r"ENOMEM"), "P1_MEMORY"),
]


def parse_log(text):
    errors = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        for pattern, level in _ERROR_PATTERNS:
            m = pattern.search(line)
            if m:
                errors.append({
                    "line": i + 1,
                    "level": level,
                    "message": m.group(0).strip()[:200],
                    "context": lines[max(0, i-2):i+3],
                })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_lines": len(lines),
        "error_count": len(errors),
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Parse MPY device logs into JSON report")
    parser.add_argument("--log-file", help="Path to log file")
    parser.add_argument("--input", action="store_true", help="Read from stdin")
    args = parser.parse_args()

    if args.log_file:
        with open(args.log_file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.input or not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("[error] Provide --log-file or pipe input via stdin", file=sys.stderr)
        sys.exit(1)

    report = parse_log(text)
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
