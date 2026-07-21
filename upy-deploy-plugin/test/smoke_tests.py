#!/usr/bin/env python3
"""Smoke tests for upy-deploy-plugin resources."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SAMPLE = ROOT / "sample"
SCRIPTS = ROOT / "scripts"
PHASE = "upy-deploy-plugin"


def run(args: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )


def run_json_allow_failure(args: list[str], *, cwd: Path = ROOT) -> tuple[int, dict[str, Any]]:
    proc = run(args, cwd=cwd)
    if not proc.stdout.strip():
        raise AssertionError(f"command produced no JSON: {' '.join(args)}\nstderr:\n{proc.stderr}")
    return proc.returncode, json.loads(proc.stdout)


def run_json(args: list[str], *, cwd: Path = ROOT) -> dict[str, Any]:
    proc = run(args, cwd=cwd)
    if proc.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return json.loads(proc.stdout)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_script_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_sample_json_parse_and_phase_names() -> None:
    for path in sorted(SAMPLE.glob("*.json")):
        payload = load_json(path)
        if payload.get("phase") and payload["phase"] != PHASE:
            raise AssertionError(f"{path.name} top-level phase mismatch")
        inner = payload.get("payload")
        if isinstance(inner, dict) and inner.get("phase") and inner["phase"] != PHASE:
            raise AssertionError(f"{path.name} payload.phase mismatch")
    success = load_json(SAMPLE / "phase_complete.upy_deploy_plugin.success.json")
    manifest = success["payload"]["manifest_content"]
    if manifest["phase"] != PHASE:
        raise AssertionError("success manifest_content.phase must be upy-deploy-plugin")
    if success["payload"]["next_phase"] != "project-library-upload":
        raise AssertionError("success sample must route to project library upload")
    failed = load_json(SAMPLE / "phase_complete.upy_deploy_plugin.failed.json")
    if failed["payload"]["next_phase"] != "upy-generate-plugin":
        raise AssertionError("failed sample must show generate fix fallback")


def assert_skill_text_contract() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = [
        'phase="upy-deploy-plugin"',
        "clean_then_upload",
        "erase_then_upload",
        "deploy_result_feedback",
        "deploy_fail_next_action",
        "project/tools/flash_device.py --compile --upload --no-reset --port <port> --json-summary",
        "shared-plugin-scripts/mpremote/list_serial_ports.py",
        "scripts/mpremote_runtime.py",
        "scripts/check_environment.py",
        "UPY_MPREMOTE",
        "python -m pip install mpremote",
        "requirements-runtime.txt",
        "scripts/capture_repl.py",
        "scripts/run_device_tests.py",
        "mpremote connect <port> resume fs",
        "mpremote_runtime.py --run --port <port> --",
        "PASS_WITH_WARNINGS",
        "error_context",
        "持久会话",
        "upy-generate-plugin(mode=fix",
        "upy-autofix-plugin",
        "项目库",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise AssertionError(f"SKILL.md missing required contract text: {missing}")


def assert_plugin_json_shape() -> None:
    plugin = load_json(ROOT / ".codex-plugin" / "plugin.json")
    if plugin.get("name") != PHASE:
        raise AssertionError("plugin.json name mismatch")
    if plugin.get("skills"):
        raise AssertionError("plugin.json should not point to missing ./skills")
    interface = plugin.get("interface", {})
    if "Deploys generated MicroPython projects" not in interface.get("shortDescription", ""):
        raise AssertionError("plugin interface metadata not customized")


def assert_approval_request_samples() -> None:
    expected = {
        "approval_request.confirm_clean_device_project.json": "confirm_clean_device_project",
        "approval_request.confirm_erase_device_fs.json": "confirm_erase_device_fs",
        "approval_request.deploy_result_feedback.json": "deploy_result_feedback",
        "approval_request.deploy_fail_next_action.json": "deploy_fail_next_action",
        "approval_request.run_device_tests.json": "run_device_tests",
    }
    for filename, approval_id in expected.items():
        sample = load_json(SAMPLE / filename)
        payload = sample.get("payload", {})
        if sample.get("phase") != PHASE or payload.get("phase") != PHASE:
            raise AssertionError(f"{filename} must use unified phase")
        if payload.get("approval_id") != approval_id:
            raise AssertionError(f"{filename} approval_id mismatch")
        if not payload.get("actions"):
            raise AssertionError(f"{filename} must expose user actions")
    clean = load_json(SAMPLE / "approval_request.confirm_clean_device_project.json")
    clean_text = json.dumps(clean, ensure_ascii=False)
    if "--mode project_files --dry-run" not in clean_text:
        raise AssertionError("clean confirmation must be based on project_files dry-run")
    erase = load_json(SAMPLE / "approval_request.confirm_erase_device_fs.json")
    if "confirm_erase" not in json.dumps(erase, ensure_ascii=False):
        raise AssertionError("erase confirmation must require explicit erase action")
    fail = load_json(SAMPLE / "approval_request.deploy_fail_next_action.json")
    fail_text = json.dumps(fail, ensure_ascii=False)
    if "upy-autofix-plugin" not in fail_text or "upy-generate-plugin" not in fail_text:
        raise AssertionError("deploy fail next action must include autofix and generate fallback")
    if "error_context" not in fail_text or "device_tests_result_path" not in fail_text:
        raise AssertionError("deploy fail next action must include generate fix error_context")
    feedback = load_json(SAMPLE / "approval_request.deploy_result_feedback.json")
    feedback_text = json.dumps(feedback, ensure_ascii=False)
    if "feedback_schema" not in feedback_text or "user_feedback_after_deploy" not in feedback_text:
        raise AssertionError("deploy result feedback must collect user feedback for generate fix")


def assert_manifest_validator() -> None:
    start = SAMPLE / "start_phase.upy_deploy_plugin.full.json"
    result = run_json([sys.executable, str(SCRIPTS / "deploy_manifest.py"), "--validate-start-phase", "--input", str(start)])
    if result["status"] != "ok":
        raise AssertionError(f"start validation failed: {result}")
    source = load_json(start)["payload"]["source_phase_complete"]
    with tempfile.TemporaryDirectory(prefix="deploy-upstream-") as temp_dir:
        upstream_path = Path(temp_dir) / "upstream.json"
        upstream_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        result = run_json([sys.executable, str(SCRIPTS / "deploy_manifest.py"), "--validate-upstream", "--input", str(upstream_path)])
    if result["status"] != "ok":
        raise AssertionError(f"upstream validation failed: {result}")
    for name in ("phase_complete.upy_deploy_plugin.success.json", "phase_complete.upy_deploy_plugin.failed.json"):
        result = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(SAMPLE / name),
        ])
        if result["status"] != "ok":
            raise AssertionError(f"{name} validation failed: {result}")
    with tempfile.TemporaryDirectory(prefix="deploy-bad-phase-") as temp_dir:
        bad_path = Path(temp_dir) / "bad_phase.json"
        bad = load_json(SAMPLE / "phase_complete.upy_deploy_plugin.success.json")
        bad["payload"]["deploy_result"] = {"result": "PASS"}
        bad["payload"]["artifacts"] = [
            {
                "type": "file_list",
                "files": [{"path": "sessions/demo-session/phase_complete.upy_deploy_plugin.json", "status": "new"}],
            }
        ]
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "deploy_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(bad_path),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"bad deploy phase_complete must fail validation: {payload}")
        text = json.dumps(payload, ensure_ascii=False)
        for expected in ("deploy_result.status is required", "deploy_result.strategy is required", "deploy_result.json"):
            if expected not in text:
                raise AssertionError(f"bad deploy validation missing {expected}: {payload}")


def assert_clean_device_mock_modes() -> None:
    clean = run_json([
        sys.executable,
        str(SCRIPTS / "clean_device_project.py"),
        "--mode",
        "project_files",
        "--dry-run",
        "--mock",
    ])
    if clean["status"] != "success" or clean["operation"] != "dry_run":
        raise AssertionError(f"clean dry-run failed: {clean}")
    if any(path.startswith("data/") or path.startswith("secrets/") for path in clean["delete_targets"]):
        raise AssertionError("project_files clean must not include mock user data")
    for stale in ("conf.mpy", "drivers/sht30_driver/mock.mpy"):
        if stale not in clean["delete_targets"]:
            raise AssertionError(f"project_files clean must remove stale deploy artifact {stale}: {clean}")
    erase = run_json([
        sys.executable,
        str(SCRIPTS / "clean_device_project.py"),
        "--mode",
        "erase_all",
        "--dry-run",
        "--mock",
    ])
    if "data/calibration.json" not in erase["delete_targets"] or "secrets/wifi.json" not in erase["delete_targets"]:
        raise AssertionError("erase_all dry-run must list user data paths")
    if not erase.get("warnings"):
        raise AssertionError("erase_all dry-run must warn")


def assert_mpremote_runtime_contract() -> None:
    runtime = load_script_module("deploy_mpremote_runtime", SCRIPTS / "mpremote_runtime.py")
    old_env = os.environ.get("UPY_MPREMOTE")
    os.environ["UPY_MPREMOTE"] = "python -m mpremote"
    try:
        resolved = runtime.resolve_mpremote_command()
    finally:
        if old_env is None:
            os.environ.pop("UPY_MPREMOTE", None)
        else:
            os.environ["UPY_MPREMOTE"] = old_env
    if resolved["status"] != "available" or resolved["source"] != "env":
        raise AssertionError(f"UPY_MPREMOTE must override mpremote resolution: {resolved}")
    command = runtime.build_mpremote_command(["python", "-m", "mpremote"], "COM9", ["resume", "exec", "print(1)"])
    if command != ["python", "-m", "mpremote", "connect", "COM9", "resume", "exec", "print(1)"]:
        raise AssertionError(f"mpremote command builder mismatch: {command}")
    summary = run_json([sys.executable, str(SCRIPTS / "mpremote_runtime.py"), "--check", "--mock"])
    if summary["status"] != "available" or summary["command"] != ["mpremote"]:
        raise AssertionError(f"mpremote runtime mock check mismatch: {summary}")
    passthrough = run_json([
        sys.executable,
        str(SCRIPTS / "mpremote_runtime.py"),
        "--run",
        "--mock",
        "--port",
        "COM9",
        "--",
        "resume",
        "exec",
        "print(1)",
    ])
    if passthrough["status"] != "success":
        raise AssertionError(f"mpremote runtime mock passthrough failed: {passthrough}")
    if passthrough["command"] != ["mpremote", "connect", "COM9", "resume", "exec", "print(1)"]:
        raise AssertionError(f"mpremote runtime passthrough command mismatch: {passthrough}")


def assert_environment_check_mock() -> None:
    result = run_json([sys.executable, str(SCRIPTS / "check_environment.py"), "--mock"])
    if result["status"] != "success":
        raise AssertionError(f"mock environment check must succeed: {result}")
    if result["tools"]["mpremote"]["source"] != "mock":
        raise AssertionError(f"environment check must use mock mpremote: {result}")
    if "requirements-runtime.txt" not in result["install_hint"]:
        raise AssertionError(f"environment check must include requirements install hint: {result}")


def assert_mpremote_calls_are_centralized() -> None:
    allowed = {"mpremote_runtime.py", "list_serial_ports.py"}
    offenders: list[str] = []
    for path in sorted(SCRIPTS.glob("*.py")):
        if path.name in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if ("subprocess.run(" in text or "subprocess.Popen(" in text) and "mpremote" in text:
            offenders.append(path.name)
    if offenders:
        raise AssertionError(f"mpremote process calls must go through mpremote_runtime.py: {offenders}")


def assert_capture_and_result_mock() -> None:
    with tempfile.TemporaryDirectory(prefix="deploy-result-") as temp_dir:
        temp = Path(temp_dir)
        serial_json = temp / "serial.json"
        upload_json = temp / "upload.json"
        log_json = temp / "log.json"
        run_json([
            sys.executable,
            str(SCRIPTS / "wait_for_device.py"),
            "--mock",
            "--timeout-sec",
            "1",
        ])
        run_json([
            sys.executable,
            str(SCRIPTS / "capture_repl.py"),
            "--mock",
            "--timeout-ms",
            "10",
            "--output-json",
            str(serial_json),
        ])
        upload_json.write_text(json.dumps({"status": "success", "steps": []}, ensure_ascii=False), encoding="utf-8")
        log_json.write_text(json.dumps({"error_count": 0, "errors": []}, ensure_ascii=False), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(upload_json),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM3",
        ])
        if result["status"] != "PASS":
            raise AssertionError(f"mock deploy result should pass: {result}")


def assert_reset_capture_traceback_fails_deploy_result() -> None:
    with tempfile.TemporaryDirectory(prefix="deploy-traceback-") as temp_dir:
        temp = Path(temp_dir)
        serial_json = temp / "serial.json"
        upload_json = temp / "upload.json"
        log_json = temp / "log.json"
        run_json([
            sys.executable,
            str(SCRIPTS / "capture_repl.py"),
            "--mock",
            "--reset-first",
            "--mock-traceback",
            "--timeout-ms",
            "10",
            "--output-json",
            str(serial_json),
        ])
        serial = json.loads(serial_json.read_text(encoding="utf-8"))
        if not serial.get("reset_first") or "ValueError: invalid Timer number" not in serial.get("output", ""):
            raise AssertionError(f"reset-first mock capture did not include startup traceback: {serial}")
        upload_json.write_text(json.dumps({"status": "success"}, ensure_ascii=False), encoding="utf-8")
        log_json.write_text(json.dumps({"error_count": 0, "errors": []}, ensure_ascii=False), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(upload_json),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM88",
        ])
        codes = {error.get("code") for error in result.get("errors", [])}
        if result.get("status") != "FAIL" or not {"python_traceback", "python_value_error"} <= codes:
            raise AssertionError(f"startup traceback must fail deploy result: {result}")


def assert_forbidden_upload_artifacts_fail_deploy_result() -> None:
    with tempfile.TemporaryDirectory(prefix="deploy-forbidden-upload-") as temp_dir:
        temp = Path(temp_dir)
        upload_json = temp / "upload.json"
        log_json = temp / "log.json"
        serial_json = temp / "serial.json"
        upload_json.write_text(
            json.dumps(
                {
                    "status": "success",
                    "uploaded_files": [
                        {"source": "build/mpy/main.mpy", "target": ":main.mpy"},
                        {"source": "build/mpy/conf.mpy", "target": ":conf.mpy"},
                        {
                            "source": "build/mpy/firmware/tasks/business_task.mpy",
                            "target": ":firmware/tasks/business_task.mpy",
                        },
                        {
                            "source": "build/mpy/tasks/__pycache__/business_task.cpython-39.pyc",
                            "target": ":tasks/__pycache__/business_task.cpython-39.pyc",
                        },
                        {
                            "source": "build/mpy/drivers/status_driver/mock.mpy",
                            "target": ":drivers/status_driver/mock.mpy",
                        },
                    ],
                    "steps": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        log_json.write_text(json.dumps({"error_count": 0, "errors": []}, ensure_ascii=False), encoding="utf-8")
        serial_json.write_text(json.dumps({"status": "success", "output": ""}, ensure_ascii=False), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(upload_json),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM3",
        ])
        if result["status"] != "FAIL":
            raise AssertionError(f"forbidden upload artifacts must fail deploy result: {result}")
        matches = [error for error in result.get("errors", []) if error.get("code") == "forbidden_runtime_upload"]
        targets = matches[0].get("targets", []) if matches else []
        for expected in (":main.mpy", ":conf.mpy", ":firmware/tasks/business_task.mpy", ":tasks/__pycache__/business_task.cpython-39.pyc"):
            if expected not in targets:
                raise AssertionError(f"forbidden upload target {expected} not reported correctly: {result}")
        if not matches:
            raise AssertionError(f"forbidden upload error not reported correctly: {result}")

    with tempfile.TemporaryDirectory(prefix="deploy-forbidden-upload-old-") as temp_dir:
        temp = Path(temp_dir)
        upload_json = temp / "upload.json"
        log_json = temp / "log.json"
        serial_json = temp / "serial.json"
        upload_json.write_text(
            json.dumps(
                {
                    "status": "success",
                    "steps": [
                        {
                            "type": "mpremote",
                            "command": ["mpremote", "resume", "fs", "cp", "x", ":drivers/status_driver/mock.py"],
                            "returncode": 0,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        log_json.write_text(json.dumps({"error_count": 0, "errors": []}, ensure_ascii=False), encoding="utf-8")
        serial_json.write_text(json.dumps({"status": "success", "output": ""}, ensure_ascii=False), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(upload_json),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM3",
        ])
        if result["status"] != "FAIL" or "forbidden_runtime_upload" not in json.dumps(result):
            raise AssertionError(f"legacy upload summary must still expose forbidden artifacts: {result}")


def assert_deploy_result_warnings_and_device_tests() -> None:
    with tempfile.TemporaryDirectory(prefix="deploy-result-edge-") as temp_dir:
        temp = Path(temp_dir)
        serial_json = temp / "serial.json"
        upload_json = temp / "upload.json"
        log_json = temp / "log.json"
        tests_json = temp / "device_tests.json"
        upload_json.write_text(json.dumps({"status": "success"}, ensure_ascii=False), encoding="utf-8")
        serial_json.write_text(json.dumps({"status": "success", "output": ""}, ensure_ascii=False), encoding="utf-8")
        log_json.write_text(json.dumps({"error_count": 0, "errors": []}, ensure_ascii=False), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(upload_json),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM3",
        ])
        if result["status"] != "PASS_WITH_WARNINGS":
            raise AssertionError(f"empty serial output should be warning-only: {result}")
        if "serial capture produced no output" not in result.get("warnings", []):
            raise AssertionError(f"warning must mention empty serial output: {result}")

        tests_json.write_text(
            json.dumps({"status": "failed", "failed": 1, "errors": [{"code": "device_test_failed"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        failed = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(upload_json),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--device-tests-json",
            str(tests_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM3",
        ])
        if failed["status"] != "FAIL":
            raise AssertionError(f"failed device tests must fail deploy result: {failed}")
        if not any(error.get("code") == "device_tests_failed" for error in failed.get("errors", [])):
            raise AssertionError(f"device test failure code missing: {failed}")

        tests_json.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "failed": 1,
                    "tests": [{"stderr_excerpt": "ImportError: no module named 'unittest'"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        runtime_failed = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(upload_json),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--device-tests-json",
            str(tests_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM3",
        ])
        if not any(error.get("code") == "device_tests_runtime_unavailable" for error in runtime_failed.get("errors", [])):
            raise AssertionError(f"runtime unavailable device-test code missing: {runtime_failed}")

        missing = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(temp / "missing-upload.json"),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM3",
        ])
        if not any(error.get("code") == "upload_json_missing" for error in missing.get("errors", [])):
            raise AssertionError(f"missing upload json must be structured, not traceback: {missing}")


def assert_install_mip_dependencies_mock() -> None:
    with tempfile.TemporaryDirectory(prefix="mip-deps-") as temp_dir:
        project = Path(temp_dir)
        manifest = {
            "phase": "generate",
            "runtime_dependencies": {
                "mip": [
                    {
                        "package": "unittest",
                        "reason": "device/tests import unittest",
                        "required_for": ["device_tests"],
                        "target": "/lib",
                        "version": "latest",
                        "install_phase": "deploy",
                        "verify_import": "unittest",
                    }
                ]
            },
        }
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "install_mip_dependencies.py"),
            "--project-root",
            str(project),
            "--mock",
        ])
        if result["status"] != "success" or result["installed"] != 1:
            raise AssertionError(f"mock mip install should install one dependency: {result}")
        record = result["records"][0]
        if record["package"] != "unittest" or record["install"]["command_args"] != ["mip", "install", "--target=/lib", "unittest"]:
            raise AssertionError(f"mock mip install command invalid: {result}")
        fs_verify = record.get("fs_verify") or {}
        if not fs_verify.get("ok") or fs_verify.get("package_path") != "/lib/unittest":
            raise AssertionError(f"mock mip install must include filesystem verification: {result}")
        if "__init__.mpy" not in fs_verify.get("expected_files", []) or "__init__.mpy" not in fs_verify.get("matched_files", []):
            raise AssertionError(f"mip fs verification must accept precompiled .mpy package files: {result}")

        manifest["runtime_dependencies"]["mip"].append(
            {
                "package": "https://upypi.net/pkgs/bma423_driver/1.0.0",
                "package_name": "bma423_driver",
                "reason": "BMA423 IMU requires uPyPi package bma423_driver",
                "required_for": ["BMA423 IMU"],
                "target": "/lib",
                "version": "1.0.0",
                "install_phase": "deploy",
                "verify_import": "bma423",
                "source": "upypi",
                "asset_files": ["bma423conf.bin"],
            }
        )
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "install_mip_dependencies.py"),
            "--project-root",
            str(project),
            "--mock",
        ])
        bma_record = next(
            (
                item for item in result.get("records", [])
                if item.get("package") == "https://upypi.net/pkgs/bma423_driver/1.0.0"
            ),
            None,
        )
        if not bma_record:
            raise AssertionError(f"mock mip install must include BMA423 uPyPi dependency: {result}")
        bma_fs_verify = bma_record.get("fs_verify") or {}
        if bma_fs_verify.get("missing_asset_files") or "bma423conf.bin" not in bma_fs_verify.get("matched_asset_files", []):
            raise AssertionError(f"mip fs verification must check uPyPi asset files: {result}")

        mip_failed_json = project / "mip_failed.json"
        mip_failed_json.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "errors": [
                        {
                            "code": "runtime_dependency_install_network_unavailable",
                            "package": "unittest",
                            "message": "mpremote mip install failed; network/proxy/VPN availability may be required",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        upload_json = project / "upload.json"
        serial_json = project / "serial.json"
        log_json = project / "log.json"
        upload_json.write_text(json.dumps({"status": "success"}), encoding="utf-8")
        serial_json.write_text(json.dumps({"status": "success", "output": "boot ok"}), encoding="utf-8")
        log_json.write_text(json.dumps({"error_count": 0, "errors": []}), encoding="utf-8")
        deploy_result = run_json([
            sys.executable,
            str(SCRIPTS / "deploy_result.py"),
            "--upload-json",
            str(upload_json),
            "--serial-json",
            str(serial_json),
            "--log-report-json",
            str(log_json),
            "--mip-install-json",
            str(mip_failed_json),
            "--strategy",
            "clean_then_upload",
            "--port",
            "COM3",
        ])
        if not any(error.get("code") == "runtime_dependency_install_network_unavailable" for error in deploy_result.get("errors", [])):
            raise AssertionError(f"deploy result must classify mip network/proxy failure: {deploy_result}")


def assert_run_device_tests_mock() -> None:
    with tempfile.TemporaryDirectory(prefix="device-tests-") as temp_dir:
        project = Path(temp_dir)
        test_path = project / "device" / "tests" / "test_contract.py"
        test_path.parent.mkdir(parents=True)
        test_path.write_text("import unittest\n\nunittest.main()\n", encoding="utf-8")
        mock_path = project / "firmware" / "drivers" / "status_driver" / "mock.py"
        mock_path.parent.mkdir(parents=True)
        mock_path.write_text("class MockStatus: pass\n", encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "run_device_tests.py"),
            "--project-root",
            str(project),
            "--mock",
        ])
        if result["status"] != "success":
            raise AssertionError(f"mock device test run must succeed: {result}")
        if result["test_count"] != 1 or result["passed"] != 1 or result["failed"] != 0:
            raise AssertionError(f"mock device test counts invalid: {result}")
        if result["tests"][0]["status"] != "passed":
            raise AssertionError(f"mock device test record invalid: {result}")
        temp_artifacts = result.get("temp_artifacts") or {}
        if temp_artifacts.get("uploaded") != 1 or temp_artifacts.get("cleaned") != 1:
            raise AssertionError(f"device test runner must record temporary mock upload and cleanup: {result}")
        uploaded = temp_artifacts["uploads"][0]
        if uploaded.get("target") != ":drivers/status_driver/mock.py":
            raise AssertionError(f"temporary mock target must be runtime-relative and explicit: {result}")
        dash = project / "-"
        proc = run([
            sys.executable,
            str(SCRIPTS / "run_device_tests.py"),
            "--project-root",
            str(project),
            "--mock",
            "--output-json",
            "-",
        ], cwd=project)
        if proc.returncode != 0:
            raise AssertionError(f"mock device tests with stdout output failed: {proc.stdout}\n{proc.stderr}")
        if dash.exists():
            raise AssertionError("run_device_tests.py must not create a project-root '-' file when --output-json - is used")
        if json.loads(proc.stdout).get("status") != "success":
            raise AssertionError(f"stdout JSON result invalid: {proc.stdout}")


def assert_shared_serial_mock() -> None:
    script = REPO / "shared-plugin-scripts" / "mpremote" / "list_serial_ports.py"
    result = run_json([sys.executable, str(script), "--mode", "mock", "--mock-port", "COM9"], cwd=REPO)
    if result["ports"][0]["name"] != "COM9":
        raise AssertionError("shared serial mock did not return requested port")
    port = result["ports"][0]
    if not port.get("platform") or port.get("source") != "mock":
        raise AssertionError(f"shared serial port record must include platform/source: {port}")
    proc = run([sys.executable, str(script), "--mock-port", "COM9"], cwd=REPO)
    if proc.returncode == 0:
        raise AssertionError("live mode must reject --mock-port")
    deploy_wrapper = SCRIPTS / "list_serial_ports.py"
    wrapper_result = run_json([sys.executable, str(deploy_wrapper), "--mode", "mock", "--mock-port", "COM10"], cwd=ROOT)
    if wrapper_result["ports"][0]["name"] != "COM10":
        raise AssertionError("deploy serial wrapper did not delegate to shared scanner")


def main() -> int:
    tests = [
        assert_sample_json_parse_and_phase_names,
        assert_skill_text_contract,
        assert_plugin_json_shape,
        assert_approval_request_samples,
        assert_manifest_validator,
        assert_clean_device_mock_modes,
        assert_mpremote_runtime_contract,
        assert_environment_check_mock,
        assert_mpremote_calls_are_centralized,
        assert_capture_and_result_mock,
        assert_reset_capture_traceback_fails_deploy_result,
        assert_forbidden_upload_artifacts_fail_deploy_result,
        assert_deploy_result_warnings_and_device_tests,
        assert_install_mip_dependencies_mock,
        assert_run_device_tests_mock,
        assert_shared_serial_mock,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
