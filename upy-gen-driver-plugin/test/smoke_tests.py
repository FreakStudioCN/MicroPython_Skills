#!/usr/bin/env python3
"""Smoke tests for upy-gen-driver-plugin resources."""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False, env=env)


def assert_ok(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_samples_validate() -> None:
    validator = ROOT / "scripts" / "validate_phase_complete.py"
    for name in (
        "phase_complete.upy_gen_driver_plugin.partial.no_device.json",
        "phase_complete.upy_gen_driver_plugin.partial.cancelled.json",
        "phase_complete.upy_gen_driver_plugin.partial.timeout.json",
        "phase_complete.upy_gen_driver_plugin.success.json",
        "phase_complete.upy_gen_driver_plugin.success.retry.json",
    ):
        result = run([sys.executable, str(validator), "--input", str(ROOT / "sample" / name)])
        assert_ok(result.returncode == 0, f"{name} failed validation: {result.stdout} {result.stderr}")


def test_validator_rejects_bad_business_states() -> None:
    validator = ROOT / "scripts" / "validate_phase_complete.py"
    sample = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.success.json").read_text(encoding="utf-8"))

    def expect_invalid(data: dict, expected: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "phase_complete.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = run([sys.executable, str(validator), "--input", str(path)])
            assert_ok(result.returncode != 0, f"validator unexpectedly accepted invalid payload: {result.stdout}")
            assert_ok(expected in result.stdout, f"expected {expected!r} in validator output: {result.stdout}")

    missing_hash = json.loads(json.dumps(sample))
    del missing_hash["payload"]["file_manifest"]["files"][0]["sha256"]
    expect_invalid(missing_hash, "sha256")

    unverified_hash = json.loads(json.dumps(sample))
    first_file = unverified_hash["payload"]["file_manifest"]["files"][0]
    del first_file["sha256"]
    first_file["hash"] = "unverified"
    expect_invalid(unverified_hash, "must use sha256")

    unverified_driver = json.loads(json.dumps(sample))
    unverified_driver["payload"]["hardware_verified"] = False
    expect_invalid(unverified_driver, "production_driver requires")

    partial_driver = json.loads(json.dumps(sample))
    partial_driver["payload"]["result"] = "partial"
    partial_driver["payload"]["structured_errors"] = [
        {
            "code": "DEVICE_NOT_FOUND",
            "severity": "warning",
            "phase_step": "hardware_verify",
            "retryable": True,
            "message": "No device.",
            "details": {},
            "next_action": "connect_device_and_resume",
        }
    ]
    expect_invalid(partial_driver, "production_driver role is only allowed")

    old_checkpoint = json.loads(json.dumps(sample))
    old_checkpoint["payload"]["checkpoint"]["checkpoint_id"] = "upy-gen-driver-plugin:phase_completed"
    expect_invalid(old_checkpoint, "checkpoint_id must use format")

    empty_file_list = json.loads(json.dumps(sample))
    empty_file_list["payload"]["artifacts"] = [{"type": "file_list", "files": []}]
    expect_invalid(empty_file_list, "file_list must include non-empty")

    partial_mock = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    partial_mock["payload"]["verification_mode"] = "mock"
    partial_mock["payload"]["warnings"] = [{"code": "MOCK_VERIFICATION_ONLY", "message": "Mock only."}]
    expect_invalid(partial_mock, "must use verification_mode=none")

    mock_ready = json.loads(json.dumps(sample))
    mock_ready["payload"]["hardware_verified"] = False
    mock_ready["payload"]["verification_mode"] = "mock"
    mock_ready["payload"]["warnings"] = [{"code": "MOCK_VERIFICATION_ONLY", "message": "Mock only."}]
    expect_invalid(mock_ready, "mock verification must not unlock generate")

    misleading_label = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    misleading_label["payload"]["artifacts"][0]["files"][0]["description"] = "Production driver (unverified)"
    expect_invalid(misleading_label, "must label unverified drivers as driver artifacts")

    artifact_with_production_key = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    artifact_with_production_key["payload"]["permissions"].append(
        {
            "permission_id": "write_driver_artifact",
            "operation": "file_write",
            "reason": "Write unverified driver artifact.",
            "paths": ["sessions/sample-standalone/project/firmware/drivers/sht30_driver/sht30.py"],
            "timeout_ms": 30000,
            "idempotency_key": "upy-gen-driver-plugin:sample-standalone:write_production_driver:sht30:v1",
            "result": "granted",
        }
    )
    expect_invalid(artifact_with_production_key, "write_driver_artifact for unverified driver artifacts")

    duplicate_key_different_action = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    duplicate_key_different_action["payload"]["permissions"].append(
        {
            "permission_id": "write_wiring",
            "operation": "file_write",
            "reason": "Write a different artifact.",
            "paths": ["sessions/sample-standalone/project/firmware/drivers/sht30_driver/wiring_sht30.md"],
            "timeout_ms": 30000,
            "idempotency_key": duplicate_key_different_action["payload"]["permissions"][0]["idempotency_key"],
            "result": "granted",
        }
    )
    expect_invalid(duplicate_key_different_action, "duplicates permissions[0] for a different action signature")

    missing_file_operation_root = json.loads(json.dumps(sample))
    del missing_file_operation_root["payload"]["runtime_context"]["file_operation_root"]
    expect_invalid(missing_file_operation_root, "payload.runtime_context.file_operation_root is required")

    missing_capability_as_no_device = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    missing_capability_as_no_device["payload"]["structured_errors"][0]["details"] = {
        "missing_capability": "device_command"
    }
    expect_invalid(missing_capability_as_no_device, "must use HOST_CAPABILITY_MISSING")

    missing_capability_without_detail = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    missing_capability_without_detail["payload"]["structured_errors"][0]["code"] = "HOST_CAPABILITY_MISSING"
    missing_capability_without_detail["payload"]["structured_errors"][0]["details"] = {}
    expect_invalid(missing_capability_without_detail, "details.missing_capability is required")

    no_device_without_device_action = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    no_device_without_device_action["payload"]["permissions"] = [
        item for item in no_device_without_device_action["payload"]["permissions"] if item.get("operation") != "device_scan"
    ]
    expect_invalid(no_device_without_device_action, "DEVICE_NOT_FOUND requires a device_scan or device_run permission entry")

    garbled_summary = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    garbled_summary["payload"]["summary"] = "Hardware verification pending бк no device available."
    expect_invalid(garbled_summary, "encoding artifact")

    mojibake_description = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    mojibake_description["payload"]["file_manifest"]["files"][0]["description"] = "Driver artifacts â€” pending verification."
    expect_invalid(mojibake_description, "encoding artifact")

    smart_punctuation = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.partial.no_device.json").read_text(encoding="utf-8"))
    smart_punctuation["payload"]["summary"] = "Hardware verification pending — no device available."
    expect_invalid(smart_punctuation, "encoding artifact")


def test_validator_rejects_foreign_phase_identity() -> None:
    validator = ROOT / "scripts" / "validate_phase_complete.py"
    sample = json.loads((ROOT / "sample" / "phase_complete.upy_gen_driver_plugin.success.json").read_text(encoding="utf-8"))
    session_id = "foreign-phase"
    sample["session_id"] = session_id
    sample["phase"] = "upy-driver-plugin"
    sample["idempotency_key"] = f"upy-driver-plugin:{session_id}:phase_complete:phase_completed:v1"
    sample["payload"]["phase"] = "driver"
    sample["payload"]["domain_phase"] = "driver"
    sample["payload"]["runtime_context"]["resource_root"] = "upy-driver-plugin"
    sample["payload"]["checkpoint"]["checkpoint_id"] = f"upy-driver-plugin:{session_id}:phase_completed"
    sample["payload"]["checkpoint"]["resume_phase"] = "upy-driver-plugin"
    sample["payload"]["checkpoint"]["state_file"] = f"sessions/{session_id}/session_state.upy_driver_plugin.json"
    sample["payload"]["permissions"][0]["idempotency_key"] = f"upy-driver-plugin:{session_id}:device_run:sht30:round1:v1"
    sample["payload"]["file_manifest"]["files"][0]["path"] = f"sessions/{session_id}/session_state.upy_driver_plugin.json"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "phase_complete.upy_driver_plugin.json"
        path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        result = run([sys.executable, str(validator), "--input", str(path)])
        assert_ok(result.returncode != 0, f"validator unexpectedly accepted foreign phase: {result.stdout}")
        for expected in (
            "input filename must be phase_complete.upy_gen_driver_plugin.json",
            "phase must be upy-gen-driver-plugin",
            "idempotency_key must start with upy-gen-driver-plugin:",
            "payload.phase must be gen-driver",
            "payload.domain_phase must be gen-driver",
            "payload.checkpoint.checkpoint_id must use format upy-gen-driver-plugin:<session_id>:<checkpoint_name>",
            "payload.checkpoint.resume_phase must be upy-gen-driver-plugin",
            "payload.checkpoint.state_file must be named session_state.upy_gen_driver_plugin.json",
        ):
            assert_ok(expected in result.stdout, f"expected {expected!r} in validator output: {result.stdout}")


def test_validator_rejects_checkpoint_mismatch() -> None:
    validator = ROOT / "scripts" / "validate_phase_complete.py"
    with tempfile.TemporaryDirectory() as tmp:
        session_id = "checkpoint-mismatch"
        session_dir = Path(tmp) / "sessions" / session_id
        state_path = session_dir / "session_state.upy_gen_driver_plugin.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "protocol_version": "1.0",
                    "session_id": session_id,
                    "phase": "upy-gen-driver-plugin",
                    "domain_phase": "gen-driver",
                    "status": "partial",
                    "checkpoint": "phase_completed",
                    "step": "finalize",
                    "idempotency_key": f"upy-gen-driver-plugin:{session_id}:state:v1",
                }
            ),
            encoding="utf-8",
        )
        debug_path = session_dir / "project" / "firmware" / "drivers" / "sht30_driver" / "sht30_debug.py"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text("print('SELF_TEST_PENDING')\n", encoding="utf-8")
        debug_sha = __import__("hashlib").sha256(debug_path.read_bytes()).hexdigest()
        state_sha = __import__("hashlib").sha256(state_path.read_bytes()).hexdigest()
        state_rel = f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json"
        debug_rel = f"sessions/{session_id}/project/firmware/drivers/sht30_driver/sht30_debug.py"
        data = {
            "protocol_version": "1.0",
            "msg_id": "msg-checkpoint-mismatch",
            "session_id": session_id,
            "phase": "upy-gen-driver-plugin",
            "timestamp": "2026-07-04T00:00:00Z",
            "type": "phase_complete",
            "idempotency_key": f"upy-gen-driver-plugin:{session_id}:phase_complete:hardware_verify_ready:v1",
            "retry_of": None,
            "payload": {
                "phase": "gen-driver",
                "domain_phase": "gen-driver",
                "result": "partial",
                "summary": "No device.",
                "next_phase": None,
                "runtime_context": {
                    "artifact_root": ".",
                    "session_root": f"sessions/{session_id}",
                    "project_root": f"sessions/{session_id}/project",
                    "file_operation_root": f"sessions/{session_id}/project",
                    "resource_root": "upy-gen-driver-plugin",
                },
                "checkpoint": {
                    "checkpoint_id": f"upy-gen-driver-plugin:{session_id}:hardware_verify_ready",
                    "resume_phase": "upy-gen-driver-plugin",
                    "resume_step": "hardware_verify",
                    "state_file": state_rel,
                },
                "permissions": [],
                "file_manifest": {
                    "root": ".",
                    "files": [
                        {
                            "path": state_rel,
                            "status": "created",
                            "role": "state",
                            "sha256": state_sha,
                            "bytes": state_path.stat().st_size,
                        },
                        {
                            "path": debug_rel,
                            "status": "created",
                            "role": "debug_driver",
                            "sha256": debug_sha,
                            "bytes": debug_path.stat().st_size,
                        },
                    ],
                },
                "artifacts": [
                    {
                        "type": "file_list",
                        "files": [
                            {"path": state_rel, "status": "created"},
                            {"path": debug_rel, "status": "created"},
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
                        "message": "No device.",
                        "details": {},
                        "next_action": "connect_device_and_resume",
                    }
                ],
                "manifest_content": None,
            },
        }
        pc_path = session_dir / "phase_complete.upy_gen_driver_plugin.json"
        pc_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = run([
            sys.executable,
            str(validator),
            "--input",
            str(pc_path),
            "--artifact-root",
            tmp,
            "--session-state",
            str(state_path),
        ])
        assert_ok(result.returncode != 0, f"checkpoint mismatch should fail: {result.stdout}")
        assert_ok("session_state.checkpoint must match" in result.stdout, result.stdout)


def test_validator_rejects_artifact_hygiene_regressions() -> None:
    validator = ROOT / "scripts" / "validate_phase_complete.py"
    with tempfile.TemporaryDirectory() as tmp:
        session_id = "artifact-hygiene"
        session_dir = Path(tmp) / "sessions" / session_id
        driver_dir = session_dir / "project" / "firmware" / "drivers" / "demo_driver"
        state_path = session_dir / "session_state.upy_gen_driver_plugin.json"
        driver_path = driver_dir / "demo.py"
        cache_path = driver_dir / "__pycache__" / "demo.cpython-39.pyc"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        driver_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "protocol_version": "1.0",
                    "session_id": session_id,
                    "phase": "upy-gen-driver-plugin",
                    "domain_phase": "gen-driver",
                    "status": "partial",
                    "checkpoint": "hardware_verify_ready",
                }
            ),
            encoding="utf-8",
        )
        driver_path.write_text(
            "from micropython import const\n"
            "# Generated driver — pending hardware verification\n"
            "_I2C_ADDR = const(0x1E)\n"
            "class Demo:\n"
            "    def __init__(self, i2c):\n"
            "        self._i2c = i2c\n",
            encoding="utf-8",
        )
        cache_path.write_bytes(b"cache")
        state_rel = f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json"
        driver_rel = f"sessions/{session_id}/project/firmware/drivers/demo_driver/demo.py"
        data = {
            "protocol_version": "1.0",
            "msg_id": "msg-artifact-hygiene",
            "session_id": session_id,
            "phase": "upy-gen-driver-plugin",
            "timestamp": "2026-07-04T00:00:00Z",
            "type": "phase_complete",
            "idempotency_key": f"upy-gen-driver-plugin:{session_id}:phase_complete:hardware_verify_ready:v1",
            "retry_of": None,
            "payload": {
                "phase": "gen-driver",
                "domain_phase": "gen-driver",
                "result": "partial",
                "summary": "Production driver generated but unverified.",
                "next_phase": None,
                "runtime_context": {
                    "artifact_root": ".",
                    "session_root": f"sessions/{session_id}",
                    "project_root": f"sessions/{session_id}/project",
                    "file_operation_root": f"sessions/{session_id}/project",
                    "resource_root": "upy-gen-driver-plugin",
                },
                "checkpoint": {
                    "checkpoint_id": f"upy-gen-driver-plugin:{session_id}:hardware_verify_ready",
                    "resume_phase": "upy-gen-driver-plugin",
                    "resume_step": "hardware_verify",
                    "state_file": state_rel,
                },
                "permissions": [
                    {
                        "permission_id": "write_driver",
                        "operation": "file_write",
                        "reason": "Write production driver artifact.",
                        "target": driver_rel,
                        "timeout_ms": 30000,
                        "idempotency_key": f"upy-gen-driver-plugin:{session_id}:write_driver_artifact:demo:v1",
                        "result": "granted",
                    }
                ],
                "file_manifest": {
                    "root": ".",
                    "files": [
                        {
                            "path": state_rel,
                            "status": "created",
                            "role": "state",
                            "sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
                            "bytes": state_path.stat().st_size,
                        },
                        {
                            "path": driver_rel,
                            "status": "created",
                            "role": "artifact",
                            "sha256": hashlib.sha256(driver_path.read_bytes()).hexdigest(),
                            "bytes": driver_path.stat().st_size,
                            "description": "Production driver (unverified).",
                        },
                    ],
                },
                "artifacts": [
                    {
                        "type": "file_list",
                        "files": [
                            {
                                "path": driver_rel,
                                "role": "Unverified driver artifact",
                                "description": "Production driver (unverified).",
                            }
                        ],
                    }
                ],
                "warnings": [],
                "structured_errors": [
                    {
                        "code": "HOST_CAPABILITY_MISSING",
                        "severity": "error",
                        "phase_step": "hardware_verify",
                        "retryable": True,
                        "message": "Missing device command.",
                        "details": {"missing_capability": "device_command"},
                        "next_action": "connect_device_and_resume",
                    }
                ],
                "hardware_verified": False,
                "verification_mode": "none",
                "manifest_content": None,
            },
        }
        pc_path = session_dir / "phase_complete.upy_gen_driver_plugin.json"
        pc_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = run([
            sys.executable,
            str(validator),
            "--input",
            str(pc_path),
            "--artifact-root",
            tmp,
            "--session-state",
            str(state_path),
        ])
        assert_ok(result.returncode != 0, f"artifact hygiene regressions should fail: {result.stdout}")
        assert_ok("session_state.step is required" in result.stdout, result.stdout)
        assert_ok("session_state.idempotency_key is required" in result.stdout, result.stdout)
        assert_ok("must use paths[], not target" in result.stdout, result.stdout)
        assert_ok("paths is required for file_write" in result.stdout, result.stdout)
        assert_ok("production driver wording" in result.stdout, result.stdout)
        assert_ok("CPython cache artifact" in result.stdout, result.stdout)
        assert_ok("partial session_state must record artifacts or last_ok_artifact" in result.stdout, result.stdout)
        assert_ok("text artifact appears to contain an encoding artifact" in result.stdout, result.stdout)


def test_validator_rejects_i2c_driver_antipatterns() -> None:
    validator = ROOT / "scripts" / "validate_phase_complete.py"
    with tempfile.TemporaryDirectory() as tmp:
        session_id = "i2c-antipattern"
        session_dir = Path(tmp) / "sessions" / session_id
        state_path = session_dir / "session_state.upy_gen_driver_plugin.json"
        driver_path = session_dir / "project" / "firmware" / "drivers" / "demo_driver" / "demo.py"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        driver_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "protocol_version": "1.0",
                    "session_id": session_id,
                    "phase": "upy-gen-driver-plugin",
                    "domain_phase": "gen-driver",
                    "status": "success",
                    "checkpoint": "phase_completed",
                    "step": "phase_complete",
                    "idempotency_key": f"upy-gen-driver-plugin:{session_id}:state:v1",
                }
            ),
            encoding="utf-8",
        )
        driver_path.write_text(
            "from micropython import const\n"
            "_I2C_ADDR_WRITE = const(0x3C)\n"
            "class Demo:\n"
            "    def __init__(self, i2c):\n"
            "        if not isinstance(i2c, I2C):\n"
            "            raise TypeError('i2c')\n",
            encoding="utf-8",
        )
        state_rel = f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json"
        driver_rel = f"sessions/{session_id}/project/firmware/drivers/demo_driver/demo.py"
        data = {
            "protocol_version": "1.0",
            "msg_id": "msg-i2c-antipattern",
            "session_id": session_id,
            "phase": "upy-gen-driver-plugin",
            "timestamp": "2026-07-04T00:00:00Z",
            "type": "phase_complete",
            "idempotency_key": f"upy-gen-driver-plugin:{session_id}:phase_complete:phase_completed:v1",
            "retry_of": None,
            "payload": {
                "phase": "gen-driver",
                "domain_phase": "gen-driver",
                "result": "success",
                "summary": "Generated driver.",
                "next_phase": "upy-generate-plugin",
                "runtime_context": {
                    "artifact_root": ".",
                    "session_root": f"sessions/{session_id}",
                    "project_root": f"sessions/{session_id}/project",
                    "file_operation_root": f"sessions/{session_id}/project",
                    "resource_root": "upy-gen-driver-plugin",
                },
                "checkpoint": {
                    "checkpoint_id": f"upy-gen-driver-plugin:{session_id}:phase_completed",
                    "resume_phase": "upy-gen-driver-plugin",
                    "resume_step": "phase_completed",
                    "state_file": state_rel,
                },
                "permissions": [],
                "file_manifest": {
                    "root": ".",
                    "files": [
                        {
                            "path": state_rel,
                            "status": "created",
                            "role": "state",
                            "sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
                            "bytes": state_path.stat().st_size,
                        },
                        {
                            "path": driver_rel,
                            "status": "created",
                            "role": "production_driver",
                            "sha256": hashlib.sha256(driver_path.read_bytes()).hexdigest(),
                            "bytes": driver_path.stat().st_size,
                        },
                    ],
                },
                "artifacts": [
                    {
                        "type": "file_list",
                        "files": [
                            {"path": state_rel, "status": "created"},
                            {"path": driver_rel, "status": "created"},
                        ],
                    }
                ],
                "warnings": [],
                "structured_errors": [],
                "hardware_verified": True,
                "manifest_content": None,
            },
        }
        pc_path = session_dir / "phase_complete.upy_gen_driver_plugin.json"
        pc_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = run([
            sys.executable,
            str(validator),
            "--input",
            str(pc_path),
            "--artifact-root",
            tmp,
            "--session-state",
            str(state_path),
        ])
        assert_ok(result.returncode != 0, f"I2C antipatterns should fail: {result.stdout}")
        assert_ok("read/write I2C address constants" in result.stdout, result.stdout)
        assert_ok("strict isinstance" in result.stdout, result.stdout)


def test_validator_rejects_python_static_quality_issues() -> None:
    validator = ROOT / "scripts" / "validate_phase_complete.py"
    with tempfile.TemporaryDirectory() as tmp:
        session_id = "python-static-quality"
        session_dir = Path(tmp) / "sessions" / session_id
        state_path = session_dir / "session_state.upy_gen_driver_plugin.json"
        driver_path = session_dir / "project" / "firmware" / "drivers" / "demo_driver" / "demo.py"
        test_path = session_dir / "project" / "firmware" / "drivers" / "demo_driver" / "test_demo.py"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        driver_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "protocol_version": "1.0",
                    "session_id": session_id,
                    "phase": "upy-gen-driver-plugin",
                    "domain_phase": "gen-driver",
                    "status": "success",
                    "checkpoint": "phase_completed",
                    "step": "phase_complete",
                    "idempotency_key": f"upy-gen-driver-plugin:{session_id}:state:v1",
                }
            ),
            encoding="utf-8",
        )
        driver_path.write_text(
            "from micropython import const\n"
            "_I2C_ADDR = const(0x1E)\n"
            "SCALE = const(1.5)\n"
            "MODE_IDLE = const(3)\n"
            "class Demo:\n"
            "    def __init__(self, i2c):\n"
            "        if not hasattr(i2c, 'readfrom_mem'):\n"
            "            raise TypeError('i2c')\n"
            "        self._i2c = i2c\n"
            "        self._addr = _I2C_ADDR\n"
            "    def configure(self):\n"
            "        self._write_reg(0x60, _ODR_10HZ)\n"
            "    def read_data(self):\n"
            "        buf = bytearray(6)\n"
            "        self._read_reg(0x68, buf)\n"
            "    def deinit(self):\n"
            "        self._write_reg(0x60, _MD_IDLE)\n"
            "    def _read_reg(self, reg):\n"
            "        return self._i2c.readfrom_mem_into(self._addr, reg, bytearray(1))\n"
            "    def _write_reg(self, reg, value):\n"
            "        return self._i2c.writeto_mem(self._addr, reg, bytes([value]))\n",
            encoding="utf-8",
        )
        test_path.write_text(
            "from machine import I2C\n"
            "I2C_FREQ = const(400000)\n"
            "print(I2C_FREQ)\n",
            encoding="utf-8",
        )
        state_rel = f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json"
        driver_rel = f"sessions/{session_id}/project/firmware/drivers/demo_driver/demo.py"
        test_rel = f"sessions/{session_id}/project/firmware/drivers/demo_driver/test_demo.py"
        data = {
            "protocol_version": "1.0",
            "msg_id": "msg-python-static-quality",
            "session_id": session_id,
            "phase": "upy-gen-driver-plugin",
            "timestamp": "2026-07-04T00:00:00Z",
            "type": "phase_complete",
            "idempotency_key": f"upy-gen-driver-plugin:{session_id}:phase_complete:phase_completed:v1",
            "retry_of": None,
            "payload": {
                "phase": "gen-driver",
                "domain_phase": "gen-driver",
                "result": "success",
                "summary": "Generated driver.",
                "next_phase": "upy-generate-plugin",
                "runtime_context": {
                    "artifact_root": ".",
                    "session_root": f"sessions/{session_id}",
                    "project_root": f"sessions/{session_id}/project",
                    "file_operation_root": f"sessions/{session_id}/project",
                    "resource_root": "upy-gen-driver-plugin",
                },
                "checkpoint": {
                    "checkpoint_id": f"upy-gen-driver-plugin:{session_id}:phase_completed",
                    "resume_phase": "upy-gen-driver-plugin",
                    "resume_step": "phase_completed",
                    "state_file": state_rel,
                },
                "permissions": [],
                "file_manifest": {
                    "root": ".",
                    "files": [
                        {
                            "path": state_rel,
                            "status": "created",
                            "role": "state",
                            "sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
                            "bytes": state_path.stat().st_size,
                        },
                        {
                            "path": driver_rel,
                            "status": "created",
                            "role": "production_driver",
                            "sha256": hashlib.sha256(driver_path.read_bytes()).hexdigest(),
                            "bytes": driver_path.stat().st_size,
                        },
                        {
                            "path": test_rel,
                            "status": "created",
                            "role": "test",
                            "sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
                            "bytes": test_path.stat().st_size,
                        },
                    ],
                },
                "artifacts": [
                    {
                        "type": "file_list",
                        "files": [
                            {"path": state_rel, "status": "created"},
                            {"path": driver_rel, "status": "created"},
                            {"path": test_rel, "status": "created"},
                        ],
                    }
                ],
                "warnings": [],
                "structured_errors": [],
                "hardware_verified": True,
                "manifest_content": None,
            },
        }
        pc_path = session_dir / "phase_complete.upy_gen_driver_plugin.json"
        pc_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = run([
            sys.executable,
            str(validator),
            "--input",
            str(pc_path),
            "--artifact-root",
            tmp,
            "--session-state",
            str(state_path),
        ])
        assert_ok(result.returncode != 0, f"static quality issues should fail: {result.stdout}")
        assert_ok("undefined name" in result.stdout, result.stdout)
        assert_ok("method call arity mismatch" in result.stdout, result.stdout)
        assert_ok("I2C capability check missing methods" in result.stdout, result.stdout)
        assert_ok("uses const(...)" in result.stdout, result.stdout)
        assert_ok("non-integer literal" in result.stdout, result.stdout)


def test_session_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "sessions" / "smoke"
        script = ROOT / "scripts" / "update_session_state.py"
        result = run([
            sys.executable,
            str(script),
            "--session-dir",
            str(session_dir),
            "--session-id",
            "smoke",
            "--checkpoint",
            "started",
            "--step",
            "start",
            "--status",
            "running",
            "--idempotency-key",
            "upy-gen-driver-plugin:smoke:start:v1",
        ])
        assert_ok(result.returncode == 0, result.stdout + result.stderr)
        result = run([sys.executable, str(script), "--session-dir", str(session_dir), "--check"])
        assert_ok(result.returncode == 0, result.stdout + result.stderr)


def test_finalize_phase_complete_refreshes_state_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        session_id = "finalize-refresh"
        session_dir = root / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        state_path = session_dir / "session_state.upy_gen_driver_plugin.json"
        debug_path = session_dir / "project" / "firmware" / "drivers" / "demo_driver" / "demo_debug.py"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text("print('SELF_TEST_PENDING')\n", encoding="utf-8")

        state_v1 = {
            "protocol_version": "1.0",
            "session_id": session_id,
            "phase": "upy-gen-driver-plugin",
            "domain_phase": "gen-driver",
            "status": "partial",
            "checkpoint": "hardware_verify_ready",
            "step": "hardware_verify",
            "idempotency_key": f"upy-gen-driver-plugin:{session_id}:hardware_verify:v1",
            "artifacts": [
                f"sessions/{session_id}/project/firmware/drivers/demo_driver/demo_debug.py"
            ],
            "last_ok_artifact": f"sessions/{session_id}/project/firmware/drivers/demo_driver/demo_debug.py",
        }
        state_path.write_text(json.dumps(state_v1, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        state_rel = f"sessions/{session_id}/session_state.upy_gen_driver_plugin.json"
        debug_rel = f"sessions/{session_id}/project/firmware/drivers/demo_driver/demo_debug.py"
        stale_state_sha = hashlib.sha256(state_path.read_bytes()).hexdigest()
        stale_state_bytes = state_path.stat().st_size

        state_v2 = dict(state_v1)
        state_v2["step"] = "phase_complete_written"
        state_v2["idempotency_key"] = f"upy-gen-driver-plugin:{session_id}:phase_complete:v1"
        state_path.write_text(json.dumps(state_v2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        draft = {
            "protocol_version": "1.0",
            "msg_id": "msg-finalize-refresh",
            "session_id": session_id,
            "phase": "upy-gen-driver-plugin",
            "timestamp": "2026-07-04T00:00:00Z",
            "type": "phase_complete",
            "idempotency_key": f"upy-gen-driver-plugin:{session_id}:phase_complete:hardware_verify_ready:v1",
            "retry_of": None,
            "payload": {
                "phase": "gen-driver",
                "domain_phase": "gen-driver",
                "result": "partial",
                "summary": "No device.",
                "next_phase": None,
                "runtime_context": {
                    "artifact_root": ".",
                    "session_root": f"sessions/{session_id}",
                    "project_root": f"sessions/{session_id}/project",
                    "file_operation_root": f"sessions/{session_id}/project",
                    "resource_root": "upy-gen-driver-plugin",
                },
                "checkpoint": {
                    "checkpoint_id": f"upy-gen-driver-plugin:{session_id}:hardware_verify_ready",
                    "resume_phase": "upy-gen-driver-plugin",
                    "resume_step": "hardware_verify",
                    "state_file": state_rel,
                },
                "permissions": [],
                "file_manifest": {
                    "root": ".",
                    "files": [
                        {
                            "path": state_rel,
                            "status": "created",
                            "role": "state",
                            "sha256": stale_state_sha,
                            "bytes": stale_state_bytes,
                        },
                        {
                            "path": debug_rel,
                            "status": "created",
                            "role": "debug_driver",
                        },
                    ],
                },
                "artifacts": [
                    {
                        "type": "file_list",
                        "files": [
                            {"path": state_rel, "status": "created"},
                            {"path": debug_rel, "status": "created"},
                        ],
                    }
                ],
                "warnings": [],
                "structured_errors": [
                    {
                        "code": "HOST_CAPABILITY_MISSING",
                        "severity": "warning",
                        "phase_step": "hardware_verify",
                        "retryable": True,
                        "message": "No device command capability.",
                        "details": {"missing_capability": "device_command"},
                        "next_action": "connect_device_and_resume",
                    }
                ],
                "hardware_verified": False,
                "verification_mode": "none",
                "manifest_content": None,
            },
        }
        draft_path = session_dir / "phase_complete.upy_gen_driver_plugin.draft.json"
        output_path = session_dir / "phase_complete.upy_gen_driver_plugin.json"
        draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = run([
            sys.executable,
            str(ROOT / "scripts" / "finalize_phase_complete.py"),
            "--input",
            str(draft_path),
            "--output",
            str(output_path),
            "--artifact-root",
            str(root),
            "--session-state",
            str(state_path),
        ])
        assert_ok(result.returncode == 0, result.stdout + result.stderr)
        finalized = json.loads(output_path.read_text(encoding="utf-8"))
        state_entry = finalized["payload"]["file_manifest"]["files"][0]
        assert_ok(state_entry["sha256"] == hashlib.sha256(state_path.read_bytes()).hexdigest(), result.stdout)
        assert_ok(state_entry["bytes"] == state_path.stat().st_size, result.stdout)


def test_convert_arduino() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "demo.ino"
        out = Path(tmp) / "mapping.json"
        src.write_text(
            "#include <Wire.h>\n"
            "const int ADDR = 0x44;\n"
            "void setup() { Wire.begin(); }\n"
            "void loop() { Wire.beginTransmission(ADDR); Wire.endTransmission(); delay(10); }\n",
            encoding="utf-8",
        )
        result = run([
            sys.executable,
            str(ROOT / "scripts" / "convert_arduino.py"),
            "--input",
            str(src),
            "--output",
            str(out),
            "--json-summary",
        ])
        assert_ok(result.returncode == 0, result.stdout + result.stderr)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert_ok(data["api_matches"], "expected API matches")


def test_mock_session() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for scenario, expected_result, expected_code in (
            ("no_device", "partial", "DEVICE_NOT_FOUND"),
            ("cancelled", "partial", "CANCELLED_BY_USER"),
            ("timeout", "partial", "DEVICE_RUN_TIMEOUT"),
            ("retry_success", "success", None),
        ):
            session_id = f"mock-smoke-{scenario}"
            result = run([
                sys.executable,
                str(ROOT / "test" / "run_local_mock_session.py"),
                "--output-root",
                tmp,
                "--session-id",
                session_id,
                "--scenario",
                scenario,
            ])
            assert_ok(result.returncode == 0, result.stdout + result.stderr)
            pc_path = Path(tmp) / "sessions" / session_id / "phase_complete.upy_gen_driver_plugin.json"
            data = json.loads(pc_path.read_text(encoding="utf-8"))
            assert_ok(data["payload"]["result"] == expected_result, f"{scenario} result mismatch")
            if expected_code:
                codes = [item["code"] for item in data["payload"]["structured_errors"]]
                assert_ok(expected_code in codes, f"{scenario} missing {expected_code}")
            permissions = data["payload"]["permissions"]
            assert_ok(permissions, f"{scenario} should record permission prompts")
            assert_ok(all("timeout_ms" in item for item in permissions), f"{scenario} permissions need timeouts")
            state_path = Path(tmp) / "sessions" / session_id / "session_state.upy_gen_driver_plugin.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            assert_ok(state["session_id"] == session_id, f"{scenario} state session mismatch")
            if expected_result == "partial":
                assert_ok(state.get("artifacts") or state.get("last_ok_artifact"), f"{scenario} state should keep resume artifacts")
            if scenario == "retry_success":
                assert_ok(data["retry_of"], "retry_success should carry retry_of")
                payload = data["payload"]
                assert_ok(payload.get("next_phase") is None, "mock success must not unlock generate")
                assert_ok(payload.get("driver_status") == "unverified", "mock success should report unverified driver_status")
                assert_ok(payload.get("verification_mode") == "mock", "mock success should use verification_mode=mock")
                assert_ok(payload.get("hardware_verified") is False, "mock success must not mark hardware_verified=true")
                warnings = payload.get("warnings", [])
                assert_ok(any(item.get("code") == "MOCK_VERIFICATION_ONLY" for item in warnings), "mock success needs warning")
                driver = payload["manifest_content"]["devices"][0]["driver"]
                assert_ok(driver.get("source") == "cold-driver", "mock manifest should preserve cold-driver source")
                assert_ok(driver.get("status") == "unverified", "mock manifest driver status should be unverified")
                roles = {item.get("role") for item in payload["file_manifest"]["files"]}
                assert_ok("artifact" in roles and "production_driver" not in roles, "mock driver should be an artifact")
                events = state.get("events", [])
                assert_ok(any(item.get("status") == "retrying" for item in events), "retry_success should record retrying event")
            log_path = Path(tmp) / "sessions" / session_id / "gen_driver" / "message_log.jsonl"
            assert_ok(log_path.exists(), f"{scenario} should write protocol message log")


def main() -> int:
    tests = [
        test_samples_validate,
        test_validator_rejects_bad_business_states,
        test_validator_rejects_foreign_phase_identity,
        test_validator_rejects_checkpoint_mismatch,
        test_validator_rejects_artifact_hygiene_regressions,
        test_validator_rejects_i2c_driver_antipatterns,
        test_validator_rejects_python_static_quality_issues,
        test_session_state,
        test_finalize_phase_complete_refreshes_state_manifest,
        test_convert_arduino,
        test_mock_session,
    ]
    failures: list[str] = []
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
