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
        "mpremote connect <port> resume fs",
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
            str(SCRIPTS / "capture_repl.py"),
            "--mock",
            "--duration-ms",
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
        assert_shared_serial_mock,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
