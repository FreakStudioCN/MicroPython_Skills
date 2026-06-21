#!/usr/bin/env python3
"""Bridge select_hw_runner.py and mock_plugin.py bidirectionally."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def forward_lines(src, dst, close_dst=False) -> None:
    try:
        for line in iter(src.readline, ""):
            if not line:
                break
            dst.write(line)
            dst.flush()
    finally:
        if close_dst:
            try:
                dst.close()
            except Exception:
                pass


def tee_stderr(src, prefix: str) -> None:
    for line in iter(src.readline, ""):
        if not line:
            break
        sys.stderr.write(f"{prefix}{line}")
        sys.stderr.flush()


def main() -> int:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    runner = subprocess.Popen(
        [sys.executable, str(TEST_DIR / "select_hw_runner.py")],
        cwd=str(SKILL_DIR),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    plugin = subprocess.Popen(
        [sys.executable, str(TEST_DIR / "mock_plugin.py")],
        cwd=str(SKILL_DIR),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )

    threads = [
        threading.Thread(target=forward_lines, args=(runner.stdout, plugin.stdin, True), daemon=True),
        threading.Thread(target=forward_lines, args=(plugin.stdout, runner.stdin, True), daemon=True),
        threading.Thread(target=tee_stderr, args=(runner.stderr, "[runner] "), daemon=True),
        threading.Thread(target=tee_stderr, args=(plugin.stderr, "[mock] "), daemon=True),
    ]
    for thread in threads:
        thread.start()

    runner_rc = runner.wait()
    plugin_rc = plugin.wait()
    for thread in threads:
        thread.join(timeout=1)

    if runner_rc != 0:
        sys.stderr.write(f"[bridge] runner exited with {runner_rc}\n")
    if plugin_rc != 0:
        sys.stderr.write(f"[bridge] mock exited with {plugin_rc}\n")
    return 0 if runner_rc == 0 and plugin_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
