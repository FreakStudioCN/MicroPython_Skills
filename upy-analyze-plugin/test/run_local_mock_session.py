#!/usr/bin/env python3
"""
本地双向桥接器：

- 启动 analyze_runner.py
- 启动 mock_plugin.py
- 将 runner stdout 转发给 mock stdin
- 将 mock stdout 转发回 runner stdin
- 将双方 stderr 透传到当前终端，便于观察

用途：
- 解决 `python analyze_runner.py | python mock_plugin.py` 只能单向传输的问题
- 用于本机真正演练 analyze <-> plugin 的最小协议闭环
"""

import subprocess
import sys
import threading
import os
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def forward_lines(src, dst, close_dst=False):
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


def tee_stderr(src, prefix):
    for line in iter(src.readline, ""):
        if not line:
            break
        sys.stderr.write(f"{prefix}{line}")
        sys.stderr.flush()


def main() -> int:
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"

    runner = subprocess.Popen(
        [sys.executable, str(TEST_DIR / "analyze_runner.py")],
        cwd=str(SKILL_DIR),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=child_env,
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
        env=child_env,
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
