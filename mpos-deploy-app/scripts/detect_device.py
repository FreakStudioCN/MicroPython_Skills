#!/usr/bin/env python3
"""Probe a MicroPythonOS device and record basic board information."""

from __future__ import annotations

import argparse
import shlex

from _deploy_common import (
    controller_command,
    device_probe_code,
    make_check,
    query_device_info,
    resolve_output_dir,
    resolve_repo_arg,
    utc_now,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="MicroPythonOS repository root")
    parser.add_argument("--serial-port", required=True, help="Serial port for the device")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset the device on connect")
    parser.add_argument("--timeout", type=int, default=120, help="Probe timeout in seconds")
    parser.add_argument("--output-dir", help="Output directory for device_info.json")
    args = parser.parse_args()

    repo = resolve_repo_arg(args.repo)
    output_dir = resolve_output_dir(repo, "device-info", args.output_dir, output_name="device_info.json")
    output_path = output_dir / "device_info.json"

    probe = query_device_info(
        repo,
        args.serial_port,
        baudrate=args.baudrate,
        no_reset=args.no_reset,
        timeout=args.timeout,
    )
    device = probe.get("device", {}) if isinstance(probe.get("device"), dict) else {}
    machine = device.get("machine")
    has_mpos = bool(device.get("has_mpos"))
    warnings = []
    errors = []
    warnings.extend(probe.get("warnings", []))
    errors.extend(probe.get("errors", []))

    result = "failed" if errors else ("partial" if warnings else "success")
    device_info = {
        "schema_version": "mpos-device-info-v1",
        "created_at_utc": utc_now(),
        "result": result,
        "connection": {
            "transport": "serial",
            "serial_port": args.serial_port,
            "baudrate": args.baudrate,
            "no_reset": args.no_reset,
        },
        "command": {
            "primary": shlex.join(
                controller_command(
                    repo,
                    "exec",
                    [device_probe_code()],
                    serial_port=args.serial_port,
                    baudrate=args.baudrate,
                    no_reset=args.no_reset,
                )
            ),
            "secondary": [],
        },
        "device": {
            "machine": machine,
            "sys_platform": device.get("sys_platform"),
            "has_mpos": has_mpos,
            "app_count": device.get("app_count"),
            "board_guess": machine,
        },
        "checks": [
            make_check(
                "device_probe",
                True,
                probe.get("ok", False),
                "passed" if probe.get("ok") and not warnings else ("passed_with_warnings" if probe.get("ok") else "failed"),
                warnings=warnings,
                errors=errors,
            )
        ],
        "warnings": warnings,
        "errors": errors,
        "artifacts": [{"kind": "device_info", "path": str(output_path)}],
        "handoff": {
            "next_step": "Confirm the board before using device-copy or mpk-install.",
            "reason": "Device probe completed.",
        },
    }
    write_json(output_path, device_info)

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(output_path)
    return 0 if result in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
