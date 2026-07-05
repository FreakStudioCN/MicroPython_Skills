#!/usr/bin/env python3
"""Smoke tests for upy-gen-driver-plugin resources."""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


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
            if scenario == "retry_success":
                assert_ok(data["retry_of"], "retry_success should carry retry_of")
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
        test_validator_rejects_i2c_driver_antipatterns,
        test_validator_rejects_python_static_quality_issues,
        test_session_state,
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
