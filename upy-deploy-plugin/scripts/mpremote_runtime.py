#!/usr/bin/env python3
"""Central mpremote process adapter for upy-deploy-plugin scripts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ENV_COMMAND = "UPY_MPREMOTE"
INSTALL_HINT = "python -m pip install mpremote"


class MpremoteUnavailable(RuntimeError):
    def __init__(self, detail: dict[str, Any]):
        self.detail = detail
        super().__init__(detail.get("message", "mpremote is not available"))

    def to_error(self) -> dict[str, Any]:
        return {
            "code": "mpremote_unavailable",
            "message": self.detail.get("message", "mpremote is not available"),
            "install_hint": INSTALL_HINT,
            "detail": self.detail,
        }


def split_command(value: str) -> list[str]:
    return shlex.split(value, posix=os.name != "nt")


def resolve_mpremote_command() -> dict[str, Any]:
    env_value = os.environ.get(ENV_COMMAND)
    if env_value:
        command = split_command(env_value)
        if command:
            return {
                "status": "available",
                "source": "env",
                "command": command,
                "env": ENV_COMMAND,
            }
    executable = shutil.which("mpremote")
    if executable:
        return {
            "status": "available",
            "source": "path",
            "command": [executable],
        }
    if importlib.util.find_spec("mpremote") is not None:
        return {
            "status": "available",
            "source": "python_module",
            "command": [sys.executable, "-m", "mpremote"],
        }
    return {
        "status": "missing",
        "source": "not_found",
        "command": [],
        "message": "mpremote was not found on PATH and is not importable from this Python environment",
        "install_hint": INSTALL_HINT,
        "python": sys.executable,
    }


def command_or_raise() -> list[str]:
    resolved = resolve_mpremote_command()
    if resolved.get("status") != "available":
        raise MpremoteUnavailable(resolved)
    return list(resolved["command"])


def build_mpremote_command(base_command: list[str], port: str | None, args: list[str]) -> list[str]:
    command = list(base_command)
    if port:
        command.extend(["connect", port])
    command.extend(args)
    return command


def build_command(port: str | None, args: list[str]) -> list[str]:
    return build_mpremote_command(command_or_raise(), port, args)


def run_mpremote(
    port: str | None,
    args: list[str],
    timeout_ms: int,
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = build_command(port, args)
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(timeout_ms, 1) / 1000,
        check=check,
    )


def popen_mpremote(
    port: str,
    args: list[str],
    **kwargs: Any,
) -> subprocess.Popen[bytes]:
    command = build_command(port, args)
    return subprocess.Popen(command, **kwargs)


def command_display(command: list[str]) -> str:
    return subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)


def availability_summary(mock_command: list[str] | None = None) -> dict[str, Any]:
    if mock_command is not None:
        resolved = {"status": "available", "source": "mock", "command": mock_command}
    else:
        resolved = resolve_mpremote_command()
    summary = {
        "tool": "mpremote",
        "status": resolved["status"],
        "source": resolved.get("source"),
        "command": resolved.get("command", []),
        "install_hint": INSTALL_HINT,
        "env_override": ENV_COMMAND,
    }
    if resolved.get("message"):
        summary["message"] = resolved["message"]
    return summary


def write_json(data: dict[str, Any], output_json: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output_json:
        target = Path(output_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    print(text)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Print mpremote availability as JSON")
    parser.add_argument("--mock", action="store_true", help="Use a mock command for contract tests")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = availability_summary(["mpremote"] if args.mock else None)
    write_json(result, args.output_json)
    return 0 if result["status"] == "available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
