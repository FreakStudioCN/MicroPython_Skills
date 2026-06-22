#!/usr/bin/env python3
"""List serial ports for plugin/live ESP32 flashing."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--mode", choices=("live", "mock"), default="live")
    parser.add_argument("--mock-port", help="Only for sample/mock tests")
    return parser.parse_args(argv)


def live_ports() -> list[dict[str, str]]:
    try:
        from serial.tools import list_ports  # type: ignore

        return [
            {"name": port.device, "description": port.description, "hwid": port.hwid}
            for port in list_ports.comports()
        ]
    except Exception as pyserial_exc:  # pragma: no cover - host-dependent fallback
        if os.name != "nt":
            raise pyserial_exc
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object",
            ],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or str(pyserial_exc))
        return [
            {"name": line.strip(), "description": "Windows serial port", "hwid": ""}
            for line in proc.stdout.splitlines()
            if line.strip()
        ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    ports = []
    if args.mode == "mock":
        mock_port = args.mock_port or "COM3"
        ports.append({"name": mock_port, "description": "Mock serial port for format tests", "hwid": "MOCK"})
    elif args.mock_port:
        result = {
            "status": "failed",
            "mode": args.mode,
            "ports": [],
            "error": {
                "code": "mock_port_not_allowed",
                "message": "--mock-port is only allowed with --mode mock",
            },
        }
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output_json:
            Path(args.output_json).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 2
    else:
        try:
            ports = live_ports()
        except Exception as exc:  # pragma: no cover - depends on host pyserial
            result = {
                "status": "failed",
                "mode": args.mode,
                "ports": [],
                "error": {"code": "serial_scan_failed", "message": str(exc)},
            }
            text = json.dumps(result, ensure_ascii=False, indent=2)
            if args.output_json:
                Path(args.output_json).write_text(text + "\n", encoding="utf-8")
            print(text)
            return 2

    result = {"status": "success", "mode": args.mode, "ports": ports}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
