#!/usr/bin/env python3
"""Create a minimal local mock session for upy-gen-driver-plugin."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_state(session_dir: Path, session_id: str, checkpoint: str, step: str, status: str) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "update_session_state.py"),
        "--session-dir",
        str(session_dir),
        "--session-id",
        session_id,
        "--checkpoint",
        checkpoint,
        "--step",
        step,
        "--status",
        status,
        "--idempotency-key",
        f"upy-gen-driver-plugin:{session_id}:{step}:v1",
    ]
    subprocess.run(cmd, check=True, text=True, capture_output=True)


def phase_complete_no_device(session_id: str, session_dir: Path) -> dict:
    return {
        "protocol_version": "1.0",
        "msg_id": f"msg-{session_id}-partial",
        "session_id": session_id,
        "phase": "upy-gen-driver-plugin",
        "timestamp": utc_now(),
        "type": "phase_complete",
        "idempotency_key": f"upy-gen-driver-plugin:{session_id}:phase_complete:no_device:v1",
        "retry_of": None,
        "payload": {
            "phase": "gen-driver",
            "domain_phase": "gen-driver",
            "result": "partial",
            "summary": "Debug driver was generated but no MicroPython device was detected.",
            "next_phase": None,
            "runtime_context": {
                "artifact_root": ".",
                "artifact_root_mode": "cwd",
                "session_root": f"sessions/{session_id}",
                "project_root": f"sessions/{session_id}/project",
                "file_operation_root": f"sessions/{session_id}/project",
                "resource_root": "upy-gen-driver-plugin",
            },
            "checkpoint": {
                "checkpoint_id": f"upy-gen-driver-plugin:{session_id}:hardware_verify_ready",
                "resume_phase": "upy-gen-driver-plugin",
                "resume_step": "hardware_verify",
                "state_file": f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json",
            },
            "permissions": [],
            "file_manifest": {
                "root": ".",
                "files": [
                    {
                        "path": f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json",
                        "status": "created",
                        "role": "state",
                    },
                    {
                        "path": f"sessions/{session_id}/project/firmware/drivers/sht30_driver/sht30_debug.py",
                        "status": "created",
                        "role": "debug_driver",
                    },
                ],
            },
            "artifacts": [
                {
                    "type": "file_list",
                    "title": "Generated so far",
                    "files": [
                        {
                            "path": f"sessions/{session_id}/project/firmware/drivers/sht30_driver/sht30_debug.py",
                            "status": "created",
                        }
                    ],
                }
            ],
            "warnings": [],
            "structured_errors": [
                {
                    "code": "DEVICE_NOT_FOUND",
                    "severity": "warning",
                    "phase_step": "hardware_verify",
                    "retryable": True,
                    "message": "No MicroPython device was detected.",
                    "details": {"action": "device_scan"},
                    "next_action": "connect_device_and_resume",
                }
            ],
            "manifest_content": None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["standalone", "pipeline"], default="standalone")
    parser.add_argument("--scenario", choices=["no_device"], default="no_device")
    parser.add_argument("--session-id", default="mock-gen-driver")
    parser.add_argument("--output-root", default=".")
    args = parser.parse_args()

    session_dir = Path(args.output_root) / "sessions" / args.session_id
    driver_path = session_dir / "project" / "firmware" / "drivers" / "sht30_driver" / "sht30_debug.py"
    write(driver_path, "print('SELF_TEST_PENDING')\n")
    run_state(session_dir, args.session_id, "hardware_verify_ready", "hardware_verify", "partial")
    phase_complete = phase_complete_no_device(args.session_id, session_dir)
    pc_path = session_dir / "phase_complete.upy_gen_driver_plugin.json"
    write(pc_path, json.dumps(phase_complete, ensure_ascii=False, indent=2) + "\n")
    validate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_phase_complete.py"), "--input", str(pc_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    print(validate.stdout)
    return validate.returncode


if __name__ == "__main__":
    sys.exit(main())
