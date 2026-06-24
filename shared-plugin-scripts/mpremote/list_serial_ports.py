#!/usr/bin/env python3
"""List serial ports for plugin/live MicroPython workflows."""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--mode", choices=("live", "mock"), default="live")
    parser.add_argument("--mock-port", help="Only for sample/mock tests")
    return parser.parse_args(argv)


def host_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform or "unknown"


def serial_record(name: str, description: str, hwid: str = "", *, source: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "hwid": hwid,
        "platform": host_platform(),
        "source": source,
    }


def pyserial_ports() -> list[dict[str, Any]]:
    from serial.tools import list_ports  # type: ignore

    ports: list[dict[str, Any]] = []
    for port in list_ports.comports():
        record = serial_record(
            str(port.device),
            str(port.description or ""),
            str(port.hwid or ""),
            source="pyserial",
        )
        for attr in ("manufacturer", "product", "serial_number", "location"):
            value = getattr(port, attr, None)
            if value:
                record[attr] = str(value)
        for attr in ("vid", "pid"):
            value = getattr(port, attr, None)
            if value is not None:
                record[attr] = value
        ports.append(record)
    return ports


def windows_fallback_ports(pyserial_exc: Exception) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object",
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or str(pyserial_exc))
    return [
        serial_record(line.strip(), "Windows serial port", source="windows-powershell")
        for line in proc.stdout.splitlines()
        if line.strip()
    ]


def posix_port_patterns(platform_name: str | None = None) -> list[str]:
    system = platform_name or sys.platform
    if system == "darwin":
        return [
            "/dev/cu.usbserial*",
            "/dev/cu.usbmodem*",
            "/dev/tty.usbserial*",
            "/dev/tty.usbmodem*",
        ]
    if system.startswith("linux"):
        return [
            "/dev/serial/by-id/*",
            "/dev/ttyACM*",
            "/dev/ttyUSB*",
        ]
    return []


def posix_fallback_ports(patterns: list[str] | None = None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    ports: list[dict[str, Any]] = []
    for pattern in patterns or posix_port_patterns():
        for candidate in sorted(glob.glob(pattern)):
            if candidate in seen:
                continue
            seen.add(candidate)
            ports.append(serial_record(candidate, "POSIX serial port", source="posix-glob"))
    return ports


def live_ports() -> list[dict[str, Any]]:
    try:
        return pyserial_ports()
    except Exception as pyserial_exc:  # pragma: no cover - host-dependent fallback
        if os.name == "nt":
            return windows_fallback_ports(pyserial_exc)
        if sys.platform == "darwin" or sys.platform.startswith("linux"):
            return posix_fallback_ports()
        raise pyserial_exc


def emit(result: dict[str, Any], output_json: str | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.mode == "mock":
        emit(
            {
                "status": "success",
                "mode": args.mode,
                "ports": [
                    serial_record(
                        args.mock_port or "COM3",
                        "Mock serial port for format tests",
                        "MOCK",
                        source="mock",
                    )
                ],
            },
            args.output_json,
        )
        return 0
    if args.mock_port:
        emit(
            {
                "status": "failed",
                "mode": args.mode,
                "ports": [],
                "error": {
                    "code": "mock_port_not_allowed",
                    "message": "--mock-port is only allowed with --mode mock",
                },
            },
            args.output_json,
        )
        return 2
    try:
        ports = live_ports()
    except Exception as exc:  # pragma: no cover - depends on host
        emit(
            {
                "status": "failed",
                "mode": args.mode,
                "ports": [],
                "error": {"code": "serial_scan_failed", "message": str(exc)},
            },
            args.output_json,
        )
        return 2
    emit({"status": "success", "mode": args.mode, "ports": ports}, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
