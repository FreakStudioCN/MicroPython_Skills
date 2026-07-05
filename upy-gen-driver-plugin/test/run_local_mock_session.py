#!/usr/bin/env python3
"""Create a minimal local mock session for upy-gen-driver-plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE = "upy-gen-driver-plugin"
DOMAIN_PHASE = "gen-driver"
CHIP = "sht30"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_message(session_dir: Path, message: dict[str, Any]) -> None:
    log_path = session_dir / "gen_driver" / "message_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(message, ensure_ascii=False) + "\n")


def run_state(
    session_dir: Path,
    session_id: str,
    checkpoint: str,
    step: str,
    status: str,
    retry_of: str | None = None,
    error: dict[str, Any] | None = None,
) -> None:
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
        f"{PHASE}:{session_id}:{step}:v1",
    ]
    if retry_of:
        cmd.extend(["--retry-of", retry_of])
    if error:
        cmd.extend(["--error", json.dumps(error, ensure_ascii=False)])
    subprocess.run(cmd, check=True, text=True, capture_output=True)


def permission_entry(
    session_id: str,
    operation: str,
    suffix: str,
    reason: str,
    timeout_ms: int,
    paths: list[str] | None = None,
    command_preview: str | None = None,
    retry_of: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "permission_id": f"{operation}_{CHIP}_{suffix}",
        "operation": operation,
        "reason": reason,
        "timeout_ms": timeout_ms,
        "idempotency_key": f"{PHASE}:{session_id}:{operation}:{CHIP}:{suffix}:v1",
        "result": "granted",
        "details": {"mock": True},
    }
    if paths:
        entry["paths"] = paths
    if command_preview:
        entry["command_preview"] = command_preview
    if retry_of:
        entry["retry_of"] = retry_of
    return entry


def structured_error(code: str, severity: str, phase_step: str, message: str, next_action: str) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "phase_step": phase_step,
        "retryable": True,
        "message": message,
        "details": {"mock": True},
        "next_action": next_action,
    }


def runtime_context(session_id: str) -> dict[str, str]:
    return {
        "artifact_root": ".",
        "artifact_root_mode": "cwd",
        "session_root": f"sessions/{session_id}",
        "project_root": f"sessions/{session_id}/project",
        "file_operation_root": f"sessions/{session_id}/project",
        "resource_root": "upy-gen-driver-plugin",
    }


def common_phase_complete(
    session_id: str,
    result: str,
    summary: str,
    checkpoint_name: str,
    resume_step: str,
    permissions: list[dict[str, Any]],
    files: list[dict[str, Any]],
    structured_errors: list[dict[str, Any]],
    next_phase: str | None,
    retry_of: str | None = None,
    manifest_content: dict[str, Any] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    hardware_verified: bool = False,
    verification_mode: str | None = "none",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phase": DOMAIN_PHASE,
        "domain_phase": DOMAIN_PHASE,
        "result": result,
        "summary": summary,
        "next_phase": next_phase,
        "runtime_context": runtime_context(session_id),
        "checkpoint": {
            "checkpoint_id": f"{PHASE}:{session_id}:{checkpoint_name}",
            "resume_phase": PHASE,
            "resume_step": resume_step,
            "state_file": f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json",
        },
        "permissions": permissions,
        "file_manifest": {
            "root": ".",
            "files": files,
        },
        "artifacts": [
            {
                "type": "file_list",
                "title": "Generated files",
                "files": [{"path": item["path"], "status": item["status"]} for item in files],
            }
        ],
        "warnings": warnings or [],
        "structured_errors": structured_errors,
        "manifest_content": manifest_content,
        "hardware_verified": hardware_verified,
    }
    if verification_mode:
        payload["verification_mode"] = verification_mode
    return {
        "protocol_version": "1.0",
        "msg_id": f"msg-{session_id}-{result}-{checkpoint_name}",
        "session_id": session_id,
        "phase": PHASE,
        "timestamp": utc_now(),
        "type": "phase_complete",
        "idempotency_key": f"{PHASE}:{session_id}:phase_complete:{checkpoint_name}:v1",
        "retry_of": retry_of,
        "payload": payload,
    }


def file_entry(output_root: Path, path: str, role: str, status: str = "created") -> dict[str, Any]:
    entry: dict[str, Any] = {"path": path, "status": status, "role": role}
    if status in {"created", "updated", "unchanged"}:
        resolved = output_root / Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"manifest entry target missing: {resolved}")
        entry["sha256"] = sha256_file(resolved)
        entry["bytes"] = resolved.stat().st_size
    return entry


def debug_driver_rel(session_id: str) -> str:
    return f"sessions/{session_id}/project/firmware/drivers/{CHIP}_driver/{CHIP}_debug.py"


def phase_complete_no_device(session_id: str, session_dir: Path) -> dict[str, Any]:
    debug_rel = debug_driver_rel(session_id)
    output_root = session_dir.parents[1]
    return common_phase_complete(
        session_id,
        "partial",
        "Debug driver was generated but no MicroPython device was detected.",
        "hardware_verify_ready",
        "hardware_verify",
        [
            permission_entry(session_id, "file_write", "debug", "Write debug driver artifact.", 30000, [debug_rel]),
            permission_entry(session_id, "device_scan", "scan", "Scan for a MicroPython device.", 5000),
        ],
        [
            file_entry(output_root, f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json", "state"),
            file_entry(output_root, debug_rel, "debug_driver"),
        ],
        [structured_error("DEVICE_NOT_FOUND", "warning", "hardware_verify", "No MicroPython device was detected.", "connect_device_and_resume")],
        None,
    )


def phase_complete_cancelled(session_id: str, session_dir: Path) -> dict[str, Any]:
    debug_rel = debug_driver_rel(session_id)
    output_root = session_dir.parents[1]
    return common_phase_complete(
        session_id,
        "partial",
        "User cancelled during hardware verification. Progress is saved for resume.",
        "cancelled",
        "hardware_verify",
        [permission_entry(session_id, "file_write", "debug", "Write debug driver artifact before cancellation.", 30000, [debug_rel])],
        [
            file_entry(output_root, f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json", "state"),
            file_entry(output_root, debug_rel, "debug_driver"),
        ],
        [structured_error("CANCELLED_BY_USER", "warning", "hardware_verify", "User cancelled hardware verification.", "resume_upy_gen_driver_plugin")],
        None,
    )


def phase_complete_timeout(session_id: str, session_dir: Path) -> dict[str, Any]:
    debug_rel = debug_driver_rel(session_id)
    log_rel = f"sessions/{session_id}/gen_driver/logs/driver_verify_round1.log"
    output_root = session_dir.parents[1]
    write(session_dir / "gen_driver" / "logs" / "driver_verify_round1.log", "DEVICE_RUN_TIMEOUT\n")
    return common_phase_complete(
        session_id,
        "partial",
        "Device verification timed out. Retry can continue from the saved debug driver.",
        "hardware_verify_ready",
        "hardware_verify",
        [
            permission_entry(
                session_id,
                "device_run",
                "round1",
                "Run debug driver on the selected MicroPython device.",
                60000,
                [debug_rel],
                "mpremote connect <port> resume run <debug-driver>",
            )
        ],
        [
            file_entry(output_root, f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json", "state"),
            file_entry(output_root, debug_rel, "debug_driver"),
            file_entry(output_root, log_rel, "verify_log"),
        ],
        [structured_error("DEVICE_RUN_TIMEOUT", "error", "hardware_verify", "Device run timed out.", "retry_device_run")],
        None,
    )


def phase_complete_retry_success(session_id: str, session_dir: Path) -> dict[str, Any]:
    debug_rel = debug_driver_rel(session_id)
    output_root = session_dir.parents[1]
    retry_of = f"msg-{session_id}-device-run-timeout"
    write(session_dir / "gen_driver" / "logs" / "driver_verify_round1.log", "DEVICE_RUN_TIMEOUT\n")
    write(session_dir / "gen_driver" / "logs" / "driver_verify_round2.log", "SELF_TEST_PASS\n")
    driver_rel = f"sessions/{session_id}/project/firmware/drivers/{CHIP}_driver/{CHIP}.py"
    test_rel = f"sessions/{session_id}/project/firmware/drivers/{CHIP}_driver/test_{CHIP}.py"
    wiring_rel = f"sessions/{session_id}/project/firmware/drivers/{CHIP}_driver/wiring_{CHIP}.md"
    write(session_dir / "project" / "firmware" / "drivers" / f"{CHIP}_driver" / f"{CHIP}.py", "class SHT30:\n    pass\n")
    write(session_dir / "project" / "firmware" / "drivers" / f"{CHIP}_driver" / f"test_{CHIP}.py", "print('SELF_TEST_PASS')\n")
    write(session_dir / "project" / "firmware" / "drivers" / f"{CHIP}_driver" / f"wiring_{CHIP}.md", "# SHT30 wiring\n")
    return common_phase_complete(
        session_id,
        "success",
        "Retry completed and mock SELF_TEST_PASS was observed.",
        "phase_completed",
        "phase_completed",
        [
            permission_entry(session_id, "device_run", "round1", "First mock device run timed out.", 60000, [debug_rel]),
            permission_entry(session_id, "device_run", "round1", "Retry mock device run after timeout.", 60000, [debug_rel], retry_of=retry_of),
        ],
        [
            file_entry(output_root, f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json", "state"),
            file_entry(output_root, debug_rel, "debug_driver"),
            file_entry(output_root, f"sessions/{session_id}/gen_driver/logs/driver_verify_round1.log", "verify_log"),
            file_entry(output_root, f"sessions/{session_id}/gen_driver/logs/driver_verify_round2.log", "verify_log"),
            file_entry(output_root, driver_rel, "production_driver"),
            file_entry(output_root, test_rel, "test"),
            file_entry(output_root, wiring_rel, "wiring"),
        ],
        [],
        "upy-generate-plugin",
        retry_of=retry_of,
        manifest_content={
            "phase": DOMAIN_PHASE,
            "devices": [{"name": "SHT30", "driver": {"status": "local_generated", "path": f"firmware/drivers/{CHIP}_driver/{CHIP}.py"}}],
        },
        warnings=[
            {
                "code": "MOCK_VERIFICATION_ONLY",
                "message": "Local mock SELF_TEST_PASS is not real hardware proof.",
            }
        ],
        verification_mode="mock",
    )


SCENARIOS = {
    "no_device": phase_complete_no_device,
    "cancelled": phase_complete_cancelled,
    "timeout": phase_complete_timeout,
    "retry_success": phase_complete_retry_success,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["standalone", "pipeline"], default="standalone")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="no_device")
    parser.add_argument("--session-id", default="mock-gen-driver")
    parser.add_argument("--output-root", default=".")
    args = parser.parse_args()

    session_dir = Path(args.output_root) / "sessions" / args.session_id
    start_message = {
        "protocol_version": "1.0",
        "msg_id": f"msg-{args.session_id}-start",
        "session_id": args.session_id,
        "phase": PHASE,
        "timestamp": utc_now(),
        "type": "start_phase",
        "idempotency_key": f"{PHASE}:{args.session_id}:start:v1",
        "retry_of": None,
        "payload": {
            "mode": args.mode,
            "phase": DOMAIN_PHASE,
            "domain_phase": DOMAIN_PHASE,
        },
    }
    append_message(session_dir, start_message)

    driver_path = session_dir / "project" / "firmware" / "drivers" / f"{CHIP}_driver" / f"{CHIP}_debug.py"
    write(driver_path, "print('SELF_TEST_PENDING')\n")
    if args.scenario == "no_device":
        run_state(session_dir, args.session_id, "hardware_verify_ready", "hardware_verify", "partial")
    elif args.scenario == "cancelled":
        error = structured_error("CANCELLED_BY_USER", "warning", "hardware_verify", "User cancelled hardware verification.", "resume_upy_gen_driver_plugin")
        run_state(session_dir, args.session_id, "cancelled", "hardware_verify", "cancelled", error=error)
    elif args.scenario == "timeout":
        error = structured_error("DEVICE_RUN_TIMEOUT", "error", "hardware_verify", "Device run timed out.", "retry_device_run")
        run_state(session_dir, args.session_id, "hardware_verify_ready", "hardware_verify", "partial", error=error)
    elif args.scenario == "retry_success":
        retry_of = f"msg-{args.session_id}-device-run-timeout"
        error = structured_error("DEVICE_RUN_TIMEOUT", "error", "hardware_verify", "Device run timed out.", "retry_device_run")
        run_state(session_dir, args.session_id, "hardware_verify_ready", "hardware_verify", "retrying", retry_of=retry_of, error=error)
        run_state(session_dir, args.session_id, "phase_completed", "phase_complete", "success", retry_of=retry_of)

    phase_complete = SCENARIOS[args.scenario](args.session_id, session_dir)
    append_message(session_dir, phase_complete)
    pc_path = session_dir / "phase_complete.upy_gen_driver_plugin.json"
    write(pc_path, json.dumps(phase_complete, ensure_ascii=False, indent=2) + "\n")
    validate = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_phase_complete.py"),
            "--input",
            str(pc_path),
            "--artifact-root",
            str(Path(args.output_root)),
            "--session-state",
            str(session_dir / "session_state.upy_gen_driver_plugin.json"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    print(validate.stdout)
    return validate.returncode


if __name__ == "__main__":
    sys.exit(main())
