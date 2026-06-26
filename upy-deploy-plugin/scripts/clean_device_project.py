#!/usr/bin/env python3
"""Dry-run or clean files on a MicroPython device before project upload."""

from __future__ import annotations

import argparse
import json
import textwrap
from datetime import datetime, timezone
from typing import Any

from common import configure_stdio, print_json, write_json
from mpremote_runtime import MpremoteUnavailable, run_mpremote


PROJECT_TARGETS = [
    "main.py",
    "main.mpy",
    "boot.py",
    "boot.mpy",
    "conf.py",
    "conf.mpy",
    "board.py",
    "board.mpy",
    "lib",
    "drivers",
    "tasks",
]


def normalize_path(path: str) -> str:
    value = path.strip().replace("\\", "/").lstrip("/")
    parts = [part for part in value.split("/") if part and part not in {".", ".."}]
    return "/".join(parts)


def mock_inventory(mode: str) -> list[str]:
    if mode == "project_files":
        return [
            "main.py",
            "conf.py",
            "conf.mpy",
            "board.py",
            "drivers/sht30_driver/mock.mpy",
            "lib/logger/logging.py",
            "drivers/sht30_driver/__init__.py",
            "tasks/main_task.py",
        ]
    return [
        "boot.py",
        "main.py",
        "conf.py",
        "board.py",
        "lib/logger/logging.py",
        "drivers/sht30_driver/__init__.py",
        "tasks/main_task.py",
        "data/calibration.json",
        "secrets/wifi.json",
        "log/run_0.log",
    ]


def list_device_files(port: str | None, timeout_ms: int) -> list[str]:
    code = r"""
import os

def walk(path):
    try:
        names = os.listdir(path or "/")
    except Exception:
        return
    for name in names:
        full = (path.rstrip("/") + "/" + name).strip("/")
        try:
            mode = os.stat("/" + full)[0]
            is_dir = bool(mode & 0x4000)
        except Exception:
            is_dir = False
        print(full + ("/" if is_dir else ""))
        if is_dir:
            walk("/" + full)

walk("/")
"""
    proc = run_mpremote(port, ["resume", "exec", code], timeout_ms)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "mpremote inventory failed")
    files: list[str] = []
    for line in proc.stdout.splitlines():
        item = normalize_path(line.rstrip("/"))
        if item:
            files.append(item)
    return sorted(set(files))


def select_targets(inventory: list[str], mode: str, include_logs: bool) -> list[str]:
    normalized = sorted({normalize_path(item) for item in inventory if normalize_path(item)})
    if mode == "erase_all":
        return normalized
    roots = set(PROJECT_TARGETS)
    if include_logs:
        roots.add("log")
    targets: list[str] = []
    for item in normalized:
        first = item.split("/", 1)[0]
        if item in roots or first in roots:
            targets.append(item)
    return sorted(set(targets), key=lambda value: (value.count("/"), value), reverse=True)


def deletion_code(targets: list[str]) -> str:
    payload = json.dumps(targets)
    return textwrap.dedent(
        f"""
        import os
        targets = {payload}

        def remove_path(path):
            p = "/" + path.strip("/")
            try:
                os.remove(p)
                print("removed_file", path)
                return
            except OSError:
                pass
            try:
                for name in os.listdir(p):
                    remove_path(path.strip("/") + "/" + name)
                os.rmdir(p)
                print("removed_dir", path)
            except Exception as exc:
                print("remove_failed", path, repr(exc))

        for target in targets:
            remove_path(target)
        try:
            os.sync()
        except Exception:
            pass
        """
    )


def execute_delete(port: str | None, targets: list[str], timeout_ms: int, mode: str) -> dict[str, Any]:
    if not targets:
        return {"returncode": 0, "stdout": "", "stderr": "", "removed": []}
    proc = run_mpremote(port, ["resume", "exec", deletion_code(targets)], timeout_ms)
    removed = [
        line.split(" ", 1)[1]
        for line in proc.stdout.splitlines()
        if line.startswith("removed_file ") or line.startswith("removed_dir ")
    ]
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "removed": removed,
        "mode": mode,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("project_files", "erase_all"), required=True)
    parser.add_argument("--port", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--include-logs", action="store_true")
    parser.add_argument("--mock", action="store_true", help="Use mock inventory, never touch a device")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    if args.dry_run == args.execute:
        result = {"status": "failed", "errors": ["choose exactly one of --dry-run or --execute"]}
        print_json(result)
        return 2
    try:
        inventory = mock_inventory(args.mode) if args.mock else list_device_files(args.port or None, args.timeout_ms)
        targets = select_targets(inventory, args.mode, args.include_logs)
        execution = None
        status = "success"
        if args.execute:
            execution = execute_delete(args.port or None, targets, args.timeout_ms, args.mode) if not args.mock else {
                "returncode": 0,
                "stdout": "\n".join(f"removed_file {item}" for item in targets),
                "stderr": "",
                "removed": targets,
                "mode": args.mode,
            }
            if execution["returncode"] != 0:
                status = "failed"
        result: dict[str, Any] = {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": args.mode,
            "operation": "execute" if args.execute else "dry_run",
            "port": args.port or None,
            "inventory_count": len(inventory),
            "delete_count": len(targets),
            "delete_targets": targets,
            "warnings": [],
            "execution": execution,
        }
        if args.mode == "erase_all" and args.dry_run:
            result["warnings"].append("erase_all may delete user data; require explicit user approval before --execute")
    except MpremoteUnavailable as exc:
        result = {
            "status": "action_required",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": args.mode,
            "operation": "execute" if args.execute else "dry_run",
            "port": args.port or None,
            "errors": [exc.to_error()],
            "delete_targets": [],
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": args.mode,
            "operation": "execute" if args.execute else "dry_run",
            "port": args.port or None,
            "errors": [{"code": "clean_device_failed", "message": str(exc)}],
            "delete_targets": [],
        }
    if args.output_json:
        write_json(args.output_json, result)
    print_json(result)
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
