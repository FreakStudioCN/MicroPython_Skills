#!/usr/bin/env python3
"""Run make lint, installing uv into the current Python environment if needed."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "timed_out": True,
            "stdout_tail": (exc.stdout or "")[-4000:],
            "stderr_tail": (exc.stderr or "")[-4000:],
        }
    return {
        "command": command,
        "returncode": proc.returncode,
        "timed_out": False,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def uv_missing(check: dict[str, Any]) -> bool:
    text = f"{check.get('stdout_tail', '')}\n{check.get('stderr_tail', '')}".lower()
    return (
        check.get("returncode") == 127
        or "uv: not found" in text
        or "uv: no such file or directory" in text
        or "no such file or directory: 'uv'" in text
        or "error 127" in text
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="MicroPythonOS repository root")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds allowed for each command")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter used to install uv")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    python = Path(args.python).expanduser()
    python_bin = python.parent.resolve()
    env = os.environ.copy()
    env["PATH"] = str(python_bin) + os.pathsep + env.get("PATH", "")

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    lint_check = run(["make", "lint"], repo, env, args.timeout)
    lint_check["name"] = "make_lint_initial"
    checks.append(lint_check)

    if lint_check.get("returncode") != 0 and uv_missing(lint_check):
        install_check = run([str(python), "-m", "pip", "install", "uv"], repo, env, args.timeout)
        install_check["name"] = "install_uv"
        checks.append(install_check)
        if install_check.get("returncode") == 0:
            lint_check = run(["make", "lint"], repo, env, args.timeout)
            lint_check["name"] = "make_lint_after_uv_install"
            checks.append(lint_check)
        else:
            errors.append("uv is missing and automatic installation failed")
    elif lint_check.get("returncode") != 0:
        errors.append("make lint failed")

    if checks[-1].get("name", "").startswith("make_lint") and checks[-1].get("returncode") == 0:
        result = "success"
    else:
        if not errors:
            errors.append("make lint did not complete successfully")
        result = "blocked"

    output = {
        "schema_version": "mpos-gen-app-lint-tooling-v1",
        "phase": "prepare-lint-tooling",
        "result": result,
        "created_at_utc": utc_now(),
        "repo": str(repo),
        "python": str(python),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if result == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
