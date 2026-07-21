#!/usr/bin/env python3
"""Smoke tests for upy-generate-plugin resources."""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def set_mcu_model(project: Path, model: str) -> None:
    manifest_path = project / "project-manifest.json"
    manifest = load_json(manifest_path)
    manifest["mcu"] = {"model": model}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def run_cmd(cmd: list[str], input_obj: dict | None = None, cwd: Path | None = None) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        input=json.dumps(input_obj, ensure_ascii=False) if input_obj is not None else None,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def ready_driver(driver_id: str = "LED", source: str = "cold-driver") -> dict:
    safe = driver_id.lower()
    return {
        "source": source,
        "status": "ready",
        "driver_id": driver_id,
        "path": f"firmware/drivers/{safe}_driver/{safe}.py",
        "hardware_marker": f"SELF_TEST_PASS:{driver_id}:SMOKE",
    }


def assert_json_files_parse() -> None:
    for path in list((ROOT / "sample").glob("*.json")) + list((ROOT / "knowledge").glob("*.json")):
        load_json(path)
    sample = load_json(ROOT / "sample" / "phase_complete.upy_generate_plugin.success.json")
    payload = sample["payload"]
    if payload["next_phase"] != "upy-deploy-plugin":
        raise AssertionError("success sample must default to upy-deploy-plugin")
    optional = {item["phase"] for item in payload.get("optional_next_phases", [])}
    if {"upy-diagram-plugin", "upy-wiring-plugin"} - optional:
        raise AssertionError("success sample must include diagram and wiring optional phases")
    if "pylint" not in payload.get("lint", {}) or "pc_unittest" not in payload.get("tests", {}):
        raise AssertionError("success sample must expose pylint and PC unittest results")
    if "generate" not in payload.get("manifest_content", {}):
        raise AssertionError("success sample manifest_content must include generate section")
    fix = load_json(ROOT / "sample" / "start_phase.upy_generate_plugin.fix.json")
    if fix["payload"].get("source") != "user_feedback_after_deploy":
        raise AssertionError("fix sample must cover manual deploy feedback")


def assert_references_and_knowledge_docs() -> None:
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8-sig")
    required_refs = [
        "references/protocol_fields.md",
        "references/legacy_constraints.md",
        "references/driver_factory_templates.md",
        "references/task_generation_rules.md",
        "references/device_unittest_subset.md",
        "references/main_conf_rules.md",
        "references/cloud_integrations.md",
        "references/validation_gates.md",
        "references/final_review_checklist.md",
    ]
    for rel in required_refs:
        if rel not in skill_text:
            raise AssertionError(f"SKILL.md must link {rel}")
        if not (ROOT / rel).exists():
            raise AssertionError(f"missing reference file: {rel}")
    required_knowledge_links = [
        "knowledge/esp32_timer_scheduler_api.pitfall.json",
        "knowledge/driver_api_usage.pitfall.json",
        "knowledge/micropython_imports.pitfall.json",
        "knowledge/mip_runtime_dependencies.pitfall.json",
        "knowledge/micropython_official_library_index.json",
    ]
    for rel in required_knowledge_links:
        if rel not in skill_text:
            raise AssertionError(f"SKILL.md must route detailed rules to {rel}")
        if not (ROOT / rel).exists():
            raise AssertionError(f"missing knowledge file: {rel}")
    protocol = (ROOT / "references" / "protocol_fields.md").read_text(encoding="utf-8-sig")
    for field in ("protocol_version", "session_id", "idempotency_key", "file_manifest", "structured_errors", "cloud_integrations"):
        if field not in protocol:
            raise AssertionError(f"protocol field not documented: {field}")
    for field in ("workflow_session_root", "diagnostic_log_session", "error_context", "Deploy Feedback And Fix Boundary"):
        if field not in protocol:
            raise AssertionError(f"protocol boundary not documented: {field}")
    main_conf = (ROOT / "references" / "main_conf_rules.md").read_text(encoding="utf-8-sig")
    for phrase in ("Framework Ownership", "firmware/lib/scheduler/*", "time.ticks_ms()", "Do not edit"):
        if phrase not in main_conf:
            raise AssertionError(f"main/conf ownership rule missing: {phrase}")
    validation = (ROOT / "references" / "validation_gates.md").read_text(encoding="utf-8-sig")
    for phrase in ("_IS_MICROPYTHON", "MPY_IMPORT_CPYTHON_ONLY_GUARD", "Official Documentation Evidence", "machine.Timer"):
        if phrase not in validation:
            raise AssertionError(f"validation reference missing generated rule: {phrase}")
    timer_pitfall = load_json(ROOT / "knowledge" / "esp32_timer_scheduler_api.pitfall.json")
    timer_text = json.dumps(timer_pitfall, ensure_ascii=False)
    for phrase in ("RP2040", "RP2350", "Scheduler()", "non-negative hardware timer id"):
        if phrase not in timer_text:
            raise AssertionError(f"timer pitfall missing rule: {phrase}")
    imports_pitfall = load_json(ROOT / "knowledge" / "micropython_imports.pitfall.json")
    imports_text = json.dumps(imports_pitfall, ensure_ascii=False)
    for phrase in ("_IS_MICROPYTHON", "MPY_IMPORT_CPYTHON_ONLY_GUARD", "direct runtime import logging"):
        if phrase not in imports_text:
            raise AssertionError(f"imports pitfall missing rule: {phrase}")
    driver_api_pitfall = load_json(ROOT / "knowledge" / "driver_api_usage.pitfall.json")
    driver_api_text = json.dumps(driver_api_pitfall, ensure_ascii=False)
    for phrase in ("trusted driver API evidence", "driver.source=micropython_lib", "api_ref"):
        if phrase not in driver_api_text:
            raise AssertionError(f"driver API pitfall missing rule: {phrase}")
    mip_pitfall = load_json(ROOT / "knowledge" / "mip_runtime_dependencies.pitfall.json")
    mip_text = json.dumps(mip_pitfall, ensure_ascii=False)
    for phrase in ("mpremote fs ls", "runtime_dependency_install_network_unavailable", "Do not copy micropython-lib source"):
        if phrase not in mip_text:
            raise AssertionError(f"mip pitfall missing rule: {phrase}")
    template = load_json(ROOT / "knowledge" / "_template.pitfall.json")
    for field in ("field_descriptions", "id", "title", "category", "detection", "fix_guidance", "verified_by"):
        if field not in template:
            raise AssertionError(f"pitfall template must document/contain field: {field}")
    catalog = load_json(ROOT / "knowledge" / "cloud_service_catalog.json")
    provider_ids = {item["id"] for item in catalog.get("providers", [])}
    for provider_id in ("volcengine_ark", "aliyun_bailian", "tencent_hunyuan", "baidu_qianfan", "custom_http_proxy"):
        if provider_id not in provider_ids:
            raise AssertionError(f"cloud service catalog missing provider: {provider_id}")


def assert_plugin_json_shape() -> None:
    plugin = load_json(ROOT / ".codex-plugin" / "plugin.json")
    if plugin["name"] != "upy-generate-plugin":
        raise AssertionError("plugin name mismatch")
    if "interface" not in plugin or "defaultPrompt" not in plugin["interface"]:
        raise AssertionError("plugin interface metadata missing")


def assert_resolver_offline() -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "resolve_upypi_packages.py"),
        "--queries",
        '["温湿度 MQTT 上报", "ssd1306 oled display"]',
        "--offline",
    ]
    rc, stdout, stderr = run_cmd(cmd)
    if rc != 0:
        raise AssertionError(f"resolver failed: {stderr}")
    payload = json.loads(stdout)
    first = payload["queries"][0]["english_keywords"]
    for expected in ("temperature", "humidity", "mqtt", "publish"):
        if expected not in first:
            raise AssertionError(f"resolver did not normalize Chinese query to English: {first}")


def assert_download_drivers_offline() -> None:
    manifest = {
        "phase": "scaffold",
        "devices": [
            {"name": "LED", "driver": {"source": "none"}},
            {"name": "DHT22", "driver": {"source": "upypi", "package_name": "dht"}},
            {
                "name": "BMA423 IMU",
                "driver": {
                    "source": "upypi",
                    "package_name": "bma423_driver",
                    "version": "1.0.0",
                    "module": "bma423",
                    "url": "https://upypi.net/pkgs/bma423_driver/1.0.0",
                },
            },
        ],
    }
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "download_drivers.py"),
        "--manifest",
        "-",
        "--offline",
    ]
    rc, stdout, stderr = run_cmd(cmd, input_obj=manifest)
    if rc != 0:
        raise AssertionError(f"ordinary source-only driver resolution should not fail: {stderr}")
    payload = json.loads(stdout)
    if not isinstance(payload.get("drivers"), list) or len(payload["drivers"]) != 3:
        raise AssertionError(f"driver payload invalid: {payload}")
    if "DRIVER_SOURCE_UNSUPPORTED" in stdout or "NO_DRIVER_FILES" in stdout:
        raise AssertionError(f"upypi should not be treated as unsupported or missing files: {stdout}")
    deps = payload.get("runtime_dependencies", {}).get("mip", [])
    if not any(
        item.get("package") == "https://upypi.net/pkgs/bma423_driver/1.0.0"
        and item.get("verify_import") == "bma423"
        and item.get("source") == "upypi"
        for item in deps
    ):
        raise AssertionError(f"upypi driver must emit deploy-time package URL mip dependency: {payload}")

    micropython_lib_manifest = {
        "phase": "scaffold",
        "devices": [
            {
                "name": "BLE stack",
                "type": "middleware",
                "driver": {
                    "source": "micropython_lib",
                    "package_name": "aioble",
                    "install_cmd": "mpremote mip install aioble",
                    "repo_url": "https://github.com/micropython/micropython-lib",
                    "search_provider": "micropython_lib_classifier",
                    "api_ref": {
                        "import": "import aioble",
                        "usage": "Use documented aioble async helpers; do not call low-level bluetooth.BLE directly unless cited separately",
                    },
                },
            }
        ],
    }
    rc, stdout, stderr = run_cmd(cmd, input_obj=micropython_lib_manifest)
    if rc != 0:
        raise AssertionError(f"micropython_lib runtime dependency should pass offline driver resolution: {stderr}")
    payload = json.loads(stdout)
    if "DRIVER_SOURCE_UNSUPPORTED" in stdout or "NO_DRIVER_FILES" in stdout:
        raise AssertionError(f"micropython_lib should not be treated as unsupported or missing files: {stdout}")
    driver = payload["drivers"][0]
    if driver["files"]:
        raise AssertionError(f"micropython_lib must not vendor source or placeholder files by default: {driver}")
    deps = payload.get("runtime_dependencies", {}).get("mip", [])
    if not deps or deps[0].get("package") != "aioble" or deps[0].get("install_phase") != "deploy":
        raise AssertionError(f"micropython_lib must emit deploy-time mip dependency: {payload}")

    missing_package_manifest = {
        "phase": "scaffold",
        "devices": [{"name": "BLE stack", "driver": {"source": "micropython_lib"}}],
    }
    rc, stdout, _stderr = run_cmd(cmd, input_obj=missing_package_manifest)
    if rc == 0 or "MICROPYTHON_LIB_PACKAGE_MISSING" not in stdout:
        raise AssertionError(f"micropython_lib without package_name must fail driver resolution: {stdout}")

    missing_upypi_package_manifest = {
        "phase": "scaffold",
        "devices": [{"name": "BMA423 IMU", "driver": {"source": "upypi"}}],
    }
    rc, stdout, _stderr = run_cmd(cmd, input_obj=missing_upypi_package_manifest)
    if rc == 0 or "UPYPI_PACKAGE_MISSING" not in stdout:
        raise AssertionError(f"upypi without package_name must fail driver resolution: {stdout}")

    ready_manifest = {
        "phase": "scaffold",
        "devices": [{"name": "Ready Sensor", "driver": ready_driver("READY_SENSOR")}],
    }
    rc, stdout, stderr = run_cmd(cmd, input_obj=ready_manifest)
    if rc != 0:
        raise AssertionError(f"explicit hardware-ready driver should pass offline driver resolution: {stderr}")

    for status, expected_code in (
        ("cold_driver_required", "COLD_DRIVER_REQUIRED"),
        ("pending_validation", "DRIVER_NOT_READY"),
        ("unverified", "DRIVER_NOT_READY"),
        ("failed", "DRIVER_NOT_READY"),
    ):
        blocked_manifest = {
            "phase": "scaffold",
            "devices": [{"name": "Cold Sensor", "driver": {"source": "cold-driver", "status": status}}],
        }
        rc, stdout, _stderr = run_cmd(cmd, input_obj=blocked_manifest)
        if rc == 0 or expected_code not in stdout:
            raise AssertionError(f"driver gate should block {status}: {stdout}")

    fake_ready_manifest = {
        "phase": "scaffold",
        "devices": [
            {
                "name": "Fake Ready",
                "driver": {"source": "cold-driver", "status": "ready", "driver_id": "FAKE", "path": "firmware/drivers/fake_driver/fake.py"},
            }
        ],
    }
    rc, stdout, _stderr = run_cmd(cmd, input_obj=fake_ready_manifest)
    if rc == 0 or "DRIVER_READY_MARKER_MISSING" not in stdout:
        raise AssertionError(f"driver gate should reject ready without SELF_TEST_PASS marker: {stdout}")


def valid_deploy_plan() -> dict:
    return {
        "firmware_root": "firmware",
        "entrypoint": "firmware/main.py",
        "source_only": ["firmware/main.py", "firmware/boot.py", "firmware/conf.py"],
        "upload_include": ["firmware/**/*.py"],
        "upload_exclude": [
            "test/**",
            "docs/**",
            "build/**",
            "firmware/drivers/**/mock.py",
            "firmware/drivers/**/mock.mpy",
        ],
        "requires_boot_delay_seconds": 3,
    }


def write_scaffold_phase_complete(path: Path, manifest: dict) -> None:
    payload = {
        "type": "phase_complete",
        "phase": "upy-scaffold-plugin",
        "session_id": path.parent.name,
        "payload": {
            "phase": "scaffold",
            "result": "success",
            "next_phase": "upy-generate-plugin",
            "manifest_content": manifest,
            "file_manifest": {"files": [{"path": "project-manifest.json", "role": "manifest"}]},
            "artifacts": [{"type": "file_manifest", "path": "scaffold_file_manifest.json"}],
            "lint": {"returncode": 0, "stdout": "", "stderr": ""},
            "structured_errors": [],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_project(root: Path, mode: str = "timer", include_plan: bool = True) -> None:
    files = {
        ".flake8": "[flake8]\nmax-line-length = 120\nbuiltins = const\n",
        "firmware/board.py": "I2C0_SCL = 6\nI2C0_SDA = 5\n",
        "firmware/conf.py": (
            "PROJECT_NAME = 'demo'\n"
            "VERSION = '0.1.0'\n"
            "SAMPLE_INTERVAL_MS = 1000\n"
            "LOG_DIR = '/log'\n"
            "LOG_FILES_MAX = 4\n"
            "LOG_LINES_PER_FILE = 150\n"
            "LOG_LEVEL = 'INFO'\n"
            "BUSINESS_ENABLED = True\n"
        ),
        "firmware/lib/logger/__init__.py": (
            "DEBUG = 10\n"
            "INFO = 20\n"
            "def install_rotating(log_dir, max_files=4, lines_per_file=150): return None\n"
            "def setLevel(level): return None\n"
            "def getLogger(name): return None\n"
            "def info(msg): print(msg)\n"
            "def warning(msg): print(msg)\n"
            "def error(msg): print(msg)\n"
            "def debug(msg): print(msg)\n"
            "def exception(exc, msg): print(msg)\n"
        ),
        "firmware/lib/time_helper.py": "def timed_function(fn):\n    return fn\n\ndef timed_coro(fn):\n    return fn\n",
        "firmware/lib/scheduler/timer_sched.py": (
            "from machine import Timer\n\n"
            "class Scheduler:\n"
            "    def __init__(self, timer_id=-1, tick_ms=100, idle_cb=None, error_cb=None):\n"
            "        self._timer = Timer(timer_id)\n"
            "        self._error_cb = error_cb\n"
            "    def add_task(self, callback, interval_ms, name=None): return name\n"
            "    def start(self): pass\n"
            "    def stop(self): self._timer.deinit()\n"
        ),
        "firmware/drivers/status_driver/__init__.py": (
            "class StatusOutput:\n"
            "    def write(self, message):\n"
            "        return message\n"
            "\n"
            "\n"
            "def create_status_output():\n"
            "    return StatusOutput()\n"
        ),
        "firmware/tasks/business_task.py": (
            "from conf import BUSINESS_ENABLED, SAMPLE_INTERVAL_MS\n"
            "from lib.time_helper import timed_function\n\n"
            "\n"
            "@timed_function\n"
            "def business_tick():\n"
            "    if not BUSINESS_ENABLED:\n"
            "        return None\n"
            "    print(SAMPLE_INTERVAL_MS)\n"
            "    return SAMPLE_INTERVAL_MS\n"
        ),
        "firmware/main.py": (
            "import time\n"
            "import sys\n"
            "from conf import LOG_DIR, LOG_LEVEL, LOG_FILES_MAX, LOG_LINES_PER_FILE, SAMPLE_INTERVAL_MS\n"
            "from lib import logger\n"
            "from lib.scheduler.timer_sched import Scheduler\n"
            "from tasks.business_task import business_tick\n"
            "\n"
            "\n"
            "def _on_scheduler_error(tid, exc):\n"
            "    sys.print_exception(exc)\n"
            "    logger.exception(exc, '[t=%dms] task failed %s' % (time.ticks_ms(), tid))\n"
            "\n"
            "\n"
            "def _main():\n"
            "    time.sleep(3)\n"
            "    logger.install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)\n"
            "    logger.setLevel(logger.DEBUG if LOG_LEVEL == 'DEBUG' else logger.INFO)\n"
            "    business_tick()\n"
            "    logger.info('[t=%dms] ok' % time.ticks_ms())\n"
            "    scheduler = Scheduler(timer_id=0, error_cb=_on_scheduler_error)\n"
            "    scheduler.add_task(business_tick, SAMPLE_INTERVAL_MS, name='business_tick')\n"
            "\n"
            "\n"
            "try:\n"
            "    _main()\n"
            "except Exception as exc:\n"
            "    sys.print_exception(exc)\n"
            "    logger.exception(exc, '[t=%dms] startup failed' % time.ticks_ms())\n"
            "    raise\n"
        ),
        "test/pc/test_business_task.py": (
            "import sys\n"
            "import unittest\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'firmware'))\n"
            "from tasks.business_task import business_tick  # noqa: E402\n\n"
            "\n"
            "class TestBusinessTask(unittest.TestCase):\n"
            "    def test_business_tick(self):\n"
            "        self.assertEqual(business_tick(), 1000)\n"
        ),
        "test/device/test_business_device.py": (
            "import sys\n"
            "import unittest\n\n"
            "sys.path.insert(0, '../firmware')\n\n"
            "from conf import BUSINESS_ENABLED, SAMPLE_INTERVAL_MS  # noqa: E402\n"
            "from drivers.status_driver.mock import MockStatusOutput  # noqa: E402\n"
            "from tasks.business_task import business_tick  # noqa: E402\n\n"
            "\n"
            "class TestBusinessDevice(unittest.TestCase):\n"
            "    def test_output_adapter_records_message(self):\n"
            "        output = MockStatusOutput()\n"
            "        output.write('device-ready')\n"
            "        self.assertIn('device-ready', output.messages[0])\n"
            "        self.assertIsNotNone(business_tick)\n\n"
            "    def test_generated_config_available(self):\n"
            "        self.assertTrue(BUSINESS_ENABLED)\n"
            "        self.assertGreaterEqual(SAMPLE_INTERVAL_MS, 1)\n"
            "\n"
            "\n"
            "unittest.main()\n"
        ),
        "tools/flash_device.py": (
            "import argparse\n"
            "import json\n"
            "\n"
            "SOURCE_ONLY_FILES = {'main.py', 'boot.py', 'conf.py'}\n"
            "COMPILE_EXCLUDE_PATTERNS = {'drivers/*/mock.py'}\n"
            "UPLOAD_EXCLUDE_PATTERNS = {'drivers/*/mock.py', 'drivers/*/mock.mpy'}\n"
            "_SUMMARY = {'compiled_files': [], 'uploaded_files': [], 'skipped_files': []}\n"
            "\n"
            "\n"
            "def _remote_parent_dirs(rel_path: str) -> list[str]:\n"
            "    parts = rel_path.split('/')[:-1]\n"
            "    return [':' + '/'.join(parts[:index]) for index in range(1, len(parts) + 1)]\n"
            "\n"
            "\n"
            "def _ensure_remote_dirs(rel_path: str):\n"
            "    for remote_dir in _remote_parent_dirs(rel_path):\n"
            "        _mpremote([\"resume\", \"fs\", \"mkdir\", remote_dir], check=False)\n"
            "\n"
            "\n"
            "def _mpremote(cmd, check=True):\n"
            "    return cmd, check\n"
            "\n"
            "\n"
            "def upload(src, remote):\n"
            "    _ensure_remote_dirs(remote.lstrip(':'))\n"
            "    return _mpremote([\"resume\", \"fs\", \"cp\", src, remote])\n"
            "\n"
            "\n"
            "def main():\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument('--json-summary', action='store_true')\n"
            "    parser.add_argument('--summary-file')\n"
            "    args = parser.parse_args([])\n"
            "    return json.dumps({'json_summary': args.json_summary})\n"
        ),
        "tools/read_device_log.py": (
            "import subprocess\n"
            "\n"
            "\n"
            "def _mpremote(cmd, **kwargs):\n"
            "    kwargs.setdefault('encoding', 'utf-8')\n"
            "    kwargs.setdefault('errors', 'replace')\n"
            "    return subprocess.run(['mpremote'] + cmd, text=True, **kwargs)\n"
        ),
        "device/tests/test_business_device.py": (
            "import sys\n"
            "import unittest\n\n"
            "sys.path.insert(0, '../firmware')\n\n"
            "from conf import BUSINESS_ENABLED, SAMPLE_INTERVAL_MS  # noqa: E402\n"
            "from drivers.status_driver.mock import MockStatusOutput  # noqa: E402\n"
            "from tasks.business_task import business_tick  # noqa: E402\n\n"
            "\n"
            "class TestDeviceTestsLayout(unittest.TestCase):\n"
            "    def test_alternate_layout(self):\n"
            "        output = MockStatusOutput()\n"
            "        output.write('alternate-layout')\n"
            "        self.assertEqual(output.messages[0], 'alternate-layout')\n"
            "        self.assertIsNotNone(business_tick)\n"
            "\n"
            "    def test_generated_config_available(self):\n"
            "        self.assertTrue(BUSINESS_ENABLED)\n"
            "        self.assertGreaterEqual(SAMPLE_INTERVAL_MS, 1)\n"
            "\n"
            "\n"
            "unittest.main()\n"
        ),
        "project-manifest.json": json.dumps(
            {
                "phase": "scaffold",
                "scaffold_mode": mode,
                "mcu": {"model": "ESP32-C3"},
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
                    ],
                    "builtin_required": ["machine", "time", "gc", "sys"],
                },
                "generate": {
                    "doc_evidence": [
                        {
                            "module": "machine",
                            "url": "https://docs.micropython.org/en/latest/library/machine.html",
                            "reason": "baseline hardware API evidence",
                        },
                        {
                            "module": "machine.Timer",
                            "url": "https://docs.micropython.org/en/latest/library/machine.Timer.html",
                            "reason": "timer scheduler API evidence",
                        },
                        {
                            "module": "machine.Pin",
                            "url": "https://docs.micropython.org/en/latest/library/machine.Pin.html",
                            "reason": "GPIO pin API evidence",
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
    }
    if include_plan:
        files["generate_plan.json"] = json.dumps(
            {
                "schema_version": "1.0",
                "scheduler_mode": mode,
                "tasks": [{"name": "business_task", "path": "firmware/tasks/business_task.py"}],
                "drivers": [{"name": "status_driver", "path": "firmware/drivers/status_driver/__init__.py"}],
                "config_constants": [
                    {"name": "BUSINESS_ENABLED", "value": True},
                    {"name": "SAMPLE_INTERVAL_MS", "value": 1000},
                ],
                "main_assembly": {
                    "imports": ["conf", "logger", "status_driver", "business_task"],
                    "drivers": ["status_output"],
                    "tasks": ["business_tick"],
                },
                "tests": [
                    {"path": "test/pc/test_business_task.py", "scenarios": ["normal"]},
                    {"path": "device/tests/test_business_device.py", "scenarios": ["interface_contract", "config_contract"]},
                ],
                "data_flow_contract": [
                    {
                        "name": "status_message",
                        "producer": "tasks.business_task.business_tick",
                        "storage": "local_result.message",
                        "consumer": "drivers.status_driver.write",
                        "invariant": "status output receives the generated business message",
                        "covered_by_tests": ["test/pc/test_business_task.py::TestBusinessTask::test_normal"],
                    }
                ],
            },
            ensure_ascii=False,
        )
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def assert_check_scripts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        checks = [
            ["ensure_pylintrc.py", "--project-dir", str(project)],
            ["check_generate_plan.py", "--project-dir", str(project)],
            ["check_conf_contract.py", "--project-dir", str(project)],
            ["check_mpy_imports.py", "--project-dir", str(project)],
            ["check_dead_config.py", "--project-dir", str(project), "--warn-only"],
            ["check_task_no_machine_import.py", "--project-dir", str(project)],
            ["check_device_unittest_subset.py", "--project-dir", str(project)],
            ["check_runtime_dependencies.py", "--project-dir", str(project)],
            ["check_doc_evidence.py", "--project-dir", str(project)],
            ["check_driver_source_compile.py", "--project-dir", str(project)],
            ["check_skeleton_compliance.py", "--project-dir", str(project)],
            ["check_cloud_integrations.py", "--project-dir", str(project)],
        ]
        for item in checks:
            cmd = [sys.executable, str(ROOT / "scripts" / item[0]), *item[1:]]
            rc, stdout, stderr = run_cmd(cmd)
            if rc != 0:
                raise AssertionError(f"{item[0]} failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
            payload = json.loads(stdout)
            if payload.get("errors"):
                raise AssertionError(f"{item[0]} emitted errors: {payload}")
        rc, stdout, stderr = run_cmd([sys.executable, str(ROOT / "scripts" / "run_quality_gates.py"), "--project-dir", str(project)])
        if rc != 0:
            raise AssertionError(f"run_quality_gates.py failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        quality = json.loads(stdout)
        for name in (
            "flake8",
            "pylint",
            "pc_unittest",
            "task_no_machine_import",
            "device_unittest_subset",
            "runtime_dependencies",
            "doc_evidence",
            "cloud_integrations",
        ):
            if not quality["checks"][name]["ok"]:
                raise AssertionError(f"quality gate {name} not ok: {quality['checks'][name]}")


def assert_check_scripts_negative_cases() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest.pop("runtime_dependencies", None)
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_runtime_dependencies.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "MPY_RUNTIME_DEPENDENCY_UNDECLARED" not in stdout:
            raise AssertionError("check_runtime_dependencies.py must require unittest mip dependency for device tests")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["devices"] = [
            {
                "name": "BLE stack",
                "type": "middleware",
                "driver": {
                    "source": "micropython_lib",
                    "package_name": "aioble",
                    "install_cmd": "mpremote mip install aioble",
                    "repo_url": "https://github.com/micropython/micropython-lib",
                    "search_provider": "micropython_lib_classifier",
                    "api_ref": {
                        "import": "import aioble",
                        "usage": "Use documented aioble async helpers; do not call low-level bluetooth.BLE directly unless cited separately",
                    },
                },
            }
        ]
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_runtime_dependencies.py"), "--project-dir", str(project)]
        )
        if rc == 0 or '"package": "aioble"' not in stdout or "MPY_RUNTIME_DEPENDENCY_UNDECLARED" not in stdout:
            raise AssertionError("check_runtime_dependencies.py must require mip dependency for manifest micropython_lib drivers")
        manifest["runtime_dependencies"]["mip"].append(
            {
                "package": "aioble",
                "reason": "BLE stack requires MicroPython-lib package aioble",
                "required_for": ["BLE stack"],
                "target": "/lib",
                "version": "latest",
                "install_phase": "deploy",
                "verify_import": "aioble",
            }
        )
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_runtime_dependencies.py"), "--project-dir", str(project)]
        )
        if rc != 0:
            raise AssertionError(f"check_runtime_dependencies.py should accept declared micropython_lib mip dependency: {stdout}\n{stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["devices"] = [
            {
                "name": "BMA423 IMU",
                "type": "imu",
                "driver": {
                    "source": "upypi",
                    "package_name": "bma423_driver",
                    "version": "1.0.0",
                    "module": "bma423",
                    "url": "https://upypi.net/pkgs/bma423_driver/1.0.0",
                    "package_json_url": "https://upypi.net/pkgs/bma423_driver/1.0.0/package.json",
                    "search_provider": "upy-pkg-guide",
                    "search_mode": "real",
                },
            }
        ]
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_runtime_dependencies.py"), "--project-dir", str(project)]
        )
        if (
            rc == 0
            or '"package": "https://upypi.net/pkgs/bma423_driver/1.0.0"' not in stdout
            or "MPY_RUNTIME_DEPENDENCY_UNDECLARED" not in stdout
        ):
            raise AssertionError("check_runtime_dependencies.py must require mip dependency for manifest upypi drivers")
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
            }
        )
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_runtime_dependencies.py"), "--project-dir", str(project)]
        )
        if rc != 0:
            raise AssertionError(f"check_runtime_dependencies.py should accept declared upypi mip dependency: {stdout}\n{stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["devices"] = [
            {
                "name": "BLE stack",
                "type": "middleware",
                "driver": {
                    "source": "micropython_lib",
                    "package_name": "aioble",
                    "install_cmd": "mpremote mip install aioble",
                    "repo_url": "https://github.com/micropython/micropython-lib",
                    "search_provider": "micropython_lib_classifier",
                },
            }
        ]
        manifest["runtime_dependencies"]["mip"].append(
            {
                "package": "aioble",
                "reason": "BLE stack requires MicroPython-lib package aioble",
                "required_for": ["BLE stack"],
                "target": "/lib",
                "version": "latest",
                "install_phase": "deploy",
                "verify_import": "aioble",
            }
        )
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_runtime_dependencies.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "MPY_RUNTIME_DEPENDENCY_API_REFERENCE_MISSING" not in stdout:
            raise AssertionError("check_runtime_dependencies.py must require API evidence for micropython_lib code generation")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["devices"] = [{"name": "BLE stack", "driver": {"source": "micropython_lib"}}]
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_runtime_dependencies.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "MPY_RUNTIME_DEPENDENCY_PACKAGE_NAME_MISSING" not in stdout:
            raise AssertionError("check_runtime_dependencies.py must require package_name for micropython_lib drivers")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["generate"]["doc_evidence"] = []
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(main_py.read_text(encoding="utf-8") + "\nimport machine\n_PIN = machine.Pin(1)\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_doc_evidence.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "DOC_EVIDENCE_MISSING" not in stdout:
            raise AssertionError("check_doc_evidence.py must require official MicroPython docs for hardware APIs")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        plan = {
            "schema_version": "1.0",
            "scheduler_mode": "timer",
            "tasks": [{"name": "business_task", "path": "firmware/tasks/business_task.py"}],
            "drivers": [{"name": "status_driver", "path": "firmware/drivers/status_driver/__init__.py"}],
            "config_constants": [{"name": "SAMPLE_INTERVAL_MS", "value": 1000}],
            "main_assembly": {"imports": ["conf"], "drivers": ["status"], "tasks": ["business_tick"]},
            "tests": [{"path": "test/pc/test_business_task.py"}],
        }
        (project / "generate_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        task = project / "firmware" / "tasks" / "bad_task.py"
        task.write_text("from machine import Pin\n\ndef bad():\n    return Pin(1)\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_task_no_machine_import.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "TASK_IMPORTS_MACHINE" not in stdout:
            raise AssertionError("check_task_no_machine_import.py must reject machine imports in tasks")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        device_test = project / "test" / "device" / "test_bad.py"
        device_test.write_text(
            "import unittest\n\n"
            "class TestBad(unittest.TestCase):\n"
            "    def test_bad(self):\n"
            "        self.assertLess(1, 2)\n"
            "\n"
            "unittest.main()\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd([sys.executable, str(ROOT / "scripts" / "check_device_unittest_subset.py"), "--project-dir", str(project)])
        if rc == 0 or "DEVICE_UNITTEST_ASSERT_UNSUPPORTED" not in stdout:
            raise AssertionError("check_device_unittest_subset.py must reject unsupported MPY unittest asserts")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        device_test = project / "device" / "tests" / "test_bad_import.py"
        device_test.parent.mkdir(parents=True, exist_ok=True)
        device_test.write_text(
            "import unittest\nfrom unittest import mock\n\n"
            "class TestBadImport(unittest.TestCase):\n"
            "    def test_bad_import(self):\n"
            "        self.assertTrue(True)\n"
            "        self.assertIsNotNone(mock)\n\n"
            "unittest.main()\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_device_unittest_subset.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "DEVICE_UNITTEST_IMPORT_UNSUPPORTED" not in stdout:
            raise AssertionError("check_device_unittest_subset.py must reject CPython-only device test imports")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        bad_driver = project / "firmware" / "lib" / "bad_driver.py"
        bad_driver.write_text("def broken(:\n    pass\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_driver_source_compile.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "DRIVER_SOURCE_COMPILE_FAILED" not in stdout:
            raise AssertionError("check_driver_source_compile.py must reject invalid driver source")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        main_py = project / "firmware" / "main.py"
        main_py.write_text(main_py.read_text(encoding="utf-8") + "\nprint(conf.MISSING_INTERVAL_MS)\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_conf_contract.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "CONF_REFERENCE_MISSING" not in stdout:
            raise AssertionError("check_conf_contract.py must reject missing conf.X references")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        conf = project / "firmware" / "conf.py"
        conf.write_text(conf.read_text(encoding="utf-8") + "\nSAMPLE_INTERVAL_MS = 2000\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_conf_contract.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "CONF_DUPLICATE_CONSTANT" not in stdout:
            raise AssertionError("check_conf_contract.py must reject duplicate conf constants")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, include_plan=False)
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generate_plan.py"), "--project-dir", str(project), "--require-plan"]
        )
        if rc == 0 or "GENERATE_PLAN_MISSING" not in stdout:
            raise AssertionError("check_generate_plan.py must reject missing required plan")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        missing_driver = project / "firmware" / "drivers" / "status_driver" / "__init__.py"
        missing_driver.unlink()
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_generate_plan.py"),
                "--project-dir",
                str(project),
                "--require-plan",
                "--check-files",
            ]
        )
        if rc == 0 or "GENERATE_PLAN_FILE_MISSING" not in stdout:
            raise AssertionError("check_generate_plan.py --check-files must reject planned files that were not generated")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        plan = json.loads((project / "generate_plan.json").read_text(encoding="utf-8"))
        plan.pop("data_flow_contract", None)
        plan["tasks"] = [{"name": "voice_dialogue", "path": "firmware/tasks/voice_dialogue.py", "states": ["LISTENING", "PROCESSING"]}]
        plan["drivers"] = [{"name": "mic", "path": "firmware/drivers/mic_driver/__init__.py", "interface": "audio_record"}]
        plan["tests"] = [{"path": "test/pc/test_voice_dialogue.py"}]
        (project / "generate_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generate_plan.py"), "--project-dir", str(project), "--require-plan"]
        )
        if rc == 0 or "GENERATE_PLAN_DATA_FLOW_CONTRACT_MISSING" not in stdout:
            raise AssertionError("check_generate_plan.py must require data_flow_contract for complex voice/audio flows")


def assert_mpy_import_fallback_policy() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "network_task.py"
        task.write_text(
            "try:\n"
            "    import uasyncio as asyncio\n"
            "except ImportError:\n"
            "    import asyncio\n\n"
            "async def sleep_once():\n"
            "    await asyncio.sleep_ms(1)\n",
            encoding="utf-8",
        )
        rc, stdout, stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_mpy_imports.py"), "--project-dir", str(project)]
        )
        if rc != 0:
            raise AssertionError(f"CPython fallback import should be warning-only:\nSTDOUT={stdout}\nSTDERR={stderr}")
        payload = json.loads(stdout)
        if "MPY_IMPORT_CPYTHON_FALLBACK" not in stdout or payload.get("errors"):
            raise AssertionError(f"fallback warning not recorded correctly: {payload}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "bad_async_task.py"
        task.write_text("import asyncio\n\nasync def bad():\n    await asyncio.sleep(1)\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_mpy_imports.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "MPY_IMPORT_UNSUPPORTED" not in stdout:
            raise AssertionError("direct CPython asyncio import must remain a strong failure")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        logger_dir = project / "firmware" / "lib" / "logger"
        logger_dir.mkdir(parents=True, exist_ok=True)
        (logger_dir / "rotating_logger.py").write_text(
            "try:\n"
            "    from time import ticks_ms\n"
            "    _IS_MICROPYTHON = True\n"
            "except ImportError:\n"
            "    _IS_MICROPYTHON = False\n\n"
            "if _IS_MICROPYTHON:\n"
            "    from . import logging as _logging\n"
            "else:\n"
            "    import logging as _cp_logging\n\n"
            "def install():\n"
            "    return _logging if _IS_MICROPYTHON else _cp_logging\n",
            encoding="utf-8",
        )
        rc, stdout, stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_mpy_imports.py"), "--project-dir", str(project), "--include-lib"]
        )
        if rc != 0:
            raise AssertionError(f"_IS_MICROPYTHON guarded CPython import should be warning-only:\nSTDOUT={stdout}\nSTDERR={stderr}")
        payload = json.loads(stdout)
        if "MPY_IMPORT_CPYTHON_ONLY_GUARD" not in stdout or payload.get("errors"):
            raise AssertionError(f"CPython-only guard warning not recorded correctly: {payload}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        bad = project / "firmware" / "lib" / "bad_logging.py"
        bad.write_text("import logging\n\nLOGGER = logging.getLogger(__name__)\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_mpy_imports.py"), "--project-dir", str(project), "--include-lib"]
        )
        if rc == 0 or "MPY_IMPORT_UNSUPPORTED" not in stdout:
            raise AssertionError("direct CPython logging import must remain a strong failure")


def assert_phase_complete_consistency() -> None:
    sample_path = ROOT / "sample" / "phase_complete.upy_generate_plugin.success.json"
    rc, stdout, stderr = run_cmd(
        [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(sample_path)]
    )
    if rc != 0:
        raise AssertionError(f"valid success sample failed consistency check:\nSTDOUT={stdout}\nSTDERR={stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "valid-session"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        valid = load_json(sample_path)
        manifest = valid["payload"]["manifest_content"]
        scaffold_manifest = dict(manifest)
        scaffold_manifest.update({"phase": "scaffold", "domain_phase": "scaffold", "final_status": "scaffolded"})
        scaffold_manifest.pop("generate", None)
        upstream_path = session_dir / "phase_complete.upy_scaffold_plugin.json"
        write_scaffold_phase_complete(upstream_path, scaffold_manifest)
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        manifest_hash = sha256_file(project / "project-manifest.json")
        state = valid["payload"]["checks"]["session_state_checkpoint"]["state"]
        state.update(
            {
                "session_id": session_dir.name,
                "manifest_hash": manifest_hash,
                "artifacts": [
                    {"type": "project_manifest", "path": "project/project-manifest.json"},
                    {"type": "generate_plan", "path": "project/generate_plan.json"},
                ],
                "last_ok_artifact": {"type": "generate_plan", "path": "project/generate_plan.json"},
            }
        )
        valid["payload"]["checks"]["session_state_checkpoint"]["state"] = state
        phase_path = session_dir / "phase_complete.upy_generate_plugin.json"
        phase_path.write_text(json.dumps(valid, ensure_ascii=False), encoding="utf-8")
        (session_dir / "session_state.upy_generate_plugin.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_phase_complete_consistency.py"),
                "--phase-complete",
                str(phase_path),
                "--project-dir",
                str(project),
                "--upstream-phase-complete",
                str(upstream_path),
            ]
        )
        if rc != 0:
            raise AssertionError(f"valid success with project manifest failed:\nSTDOUT={stdout}\nSTDERR={stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "new-hardware-session"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        phase = load_json(sample_path)
        manifest = phase["payload"]["manifest_content"]
        scaffold_manifest = dict(manifest)
        scaffold_manifest.update({"phase": "scaffold", "domain_phase": "scaffold", "final_status": "scaffolded"})
        scaffold_manifest.pop("generate", None)
        upstream_path = session_dir / "phase_complete.upy_scaffold_plugin.json"
        write_scaffold_phase_complete(upstream_path, scaffold_manifest)
        changed = json.loads(json.dumps(manifest))
        changed["devices"].append({"name": "DHT22", "driver": {"source": "upypi", "package": "dht"}})
        changed["pinout"].append({"device": "DHT22", "pin_name": "DATA", "gpio": "7"})
        phase["payload"]["manifest_content"] = changed
        (project / "project-manifest.json").write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        phase_path = session_dir / "phase_complete.upy_generate_plugin.json"
        phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_phase_complete_consistency.py"),
                "--phase-complete",
                str(phase_path),
                "--project-dir",
                str(project),
                "--upstream-phase-complete",
                str(upstream_path),
            ]
        )
        for expected in ("NEW_HARDWARE_REQUIRES_UPSTREAM_SELECTION", "PINOUT_CHANGE_REQUIRES_SELECT_HW_OR_SCAFFOLD"):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"generate must reject hardware changes not present in upstream scaffold: {expected}\n{stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "incremental-hardware-session"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        phase = load_json(sample_path)
        manifest = json.loads(json.dumps(phase["payload"]["manifest_content"]))
        manifest["devices"].append({"name": "DHT22", "driver": {"source": "upypi", "package": "dht"}})
        manifest["pinout"].append({"device": "DHT22", "pin_name": "DATA", "gpio": "7"})
        scaffold_manifest = dict(manifest)
        scaffold_manifest.update(
            {
                "phase": "scaffold",
                "domain_phase": "scaffold",
                "final_status": "scaffolded",
                "incremental": True,
                "generate_scope": "new_devices_only",
            }
        )
        scaffold_manifest.pop("generate", None)
        upstream_path = session_dir / "phase_complete.upy_scaffold_plugin.json"
        write_scaffold_phase_complete(upstream_path, scaffold_manifest)
        phase["payload"]["manifest_content"] = manifest
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        phase_path = session_dir / "phase_complete.upy_generate_plugin.json"
        phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_phase_complete_consistency.py"),
                "--phase-complete",
                str(phase_path),
                "--project-dir",
                str(project),
                "--upstream-phase-complete",
                str(upstream_path),
            ]
        )
        if "NEW_HARDWARE_REQUIRES_UPSTREAM_SELECTION" in stdout or "PINOUT_CHANGE_REQUIRES_SELECT_HW_OR_SCAFFOLD" in stdout:
            raise AssertionError(f"incremental scaffold baseline should authorize new hardware facts:\nSTDOUT={stdout}\nSTDERR={stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_null_next_phase.json"
        bad = load_json(sample_path)
        bad["payload"]["next_phase"] = None
        bad["payload"].pop("next_phase_decision", None)
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "NEXT_PHASE_NULL_WITHOUT_DECISION" not in stdout:
            raise AssertionError("success phase_complete with next_phase=null must record an explicit decision")

    with tempfile.TemporaryDirectory() as temp_dir:
        ok_path = Path(temp_dir) / "ok_null_next_phase.json"
        ok = load_json(sample_path)
        ok["payload"]["next_phase"] = None
        ok["payload"]["next_phase_decision"] = {
            "value": None,
            "reason": "user_selected_stop_after_generate",
        }
        ok_path.write_text(json.dumps(ok, ensure_ascii=False), encoding="utf-8")
        rc, stdout, stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(ok_path)]
        )
        if rc != 0:
            raise AssertionError(f"explicit stop-after-generate decision should pass:\nSTDOUT={stdout}\nSTDERR={stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "old-deploy-tools"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        (project / "tools" / "flash_device.py").write_text(
            "import argparse\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--json-summary', action='store_true')\n",
            encoding="utf-8",
        )
        phase = load_json(sample_path)
        phase["payload"]["manifest_content"] = load_json(project / "project-manifest.json")
        phase["payload"]["manifest_content"].update(
            {
                "phase": "generate",
                "domain_phase": "generate",
                "final_status": "generated",
                "requirements": {"description": "demo"},
                "devices": [{"name": "LED", "driver": {"source": "none"}}],
                "mcu": {"model": "mock"},
                "pinout": [{"device": "LED", "pin_name": "status", "gpio": "mock"}],
                "generate": {"deploy_plan": valid_deploy_plan(), "behavior_spec": {}, "simulation_hints": {}},
            }
        )
        (project / "project-manifest.json").write_text(
            json.dumps(phase["payload"]["manifest_content"], ensure_ascii=False),
            encoding="utf-8",
        )
        phase_path = session_dir / "phase_complete.upy_generate_plugin.json"
        phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_phase_complete_consistency.py"),
                "--phase-complete",
                str(phase_path),
                "--project-dir",
                str(project),
            ]
        )
        if rc == 0 or "DEPLOY_TOOL_INCOMPATIBLE" not in stdout:
            raise AssertionError("deploy handoff must reject old project/tools deploy helpers")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_failed_gate.json"
        bad = load_json(sample_path)
        bad["payload"]["checks"]["mpy_imports"] = {"returncode": 2, "ok": False}
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "GATE_NOT_OK" not in stdout:
            raise AssertionError("success phase_complete with failed mpy_imports must be rejected")
        payload = json.loads(stdout)
        if payload.get("result") != "failed" or payload.get("payload_result") != "success":
            raise AssertionError(f"phase consistency check must separate check result from payload result: {payload}")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_thin_manifest.json"
        bad = load_json(sample_path)
        bad["payload"]["manifest_content"] = {
            "phase": "generate",
            "schema_version": "1.0",
            "project_name": "demo",
            "updated_at": "2026-06-23T00:00:00Z",
            "generate": {"deploy_plan": valid_deploy_plan(), "behavior_spec": {}, "simulation_hints": {}},
        }
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "MANIFEST_REQUIRED_FIELD_MISSING" not in stdout:
            raise AssertionError("success phase_complete with thin manifest_content must be rejected")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_pylint_error.json"
        bad = load_json(sample_path)
        bad["payload"]["lint"]["pylint"] = {"returncode": 3, "ok": False}
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "PYLINT_STRONG_FAILURE" not in stdout:
            raise AssertionError("success phase_complete with pylint fatal/error must be rejected")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_pylint_skipped.json"
        bad = load_json(sample_path)
        bad["payload"]["lint"]["pylint"] = {"returncode": None, "ok": True, "policy": "skipped_no_pylintrc"}
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "PYLINT_SKIPPED_ON_SUCCESS" not in stdout:
            raise AssertionError("success phase_complete with skipped pylint must be rejected")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_optional_phases.json"
        bad = load_json(sample_path)
        bad["payload"]["optional_next_phases"] = []
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "OPTIONAL_NEXT_PHASE_MISSING" not in stdout:
            raise AssertionError("success phase_complete must offer diagram/wiring optional phases")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_git.json"
        bad = load_json(sample_path)
        bad["payload"]["generate"]["git"] = {"commit": None, "status": "permission_required_or_dry_run"}
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "GIT_COMMIT_MISSING" not in stdout:
            raise AssertionError("success phase_complete must record a completed git commit")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_manifest_git_commit_role.json"
        bad = load_json(sample_path)
        bad["payload"]["manifest_content"]["generate"]["git"] = {"commit": "a" * 40}
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "MANIFEST_GIT_COMMIT_ROLE_MISSING" not in stdout:
            raise AssertionError("manifest generate.git.commit must declare commit_role when present")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_file_manifest_plan.json"
        bad = load_json(sample_path)
        bad["payload"]["file_manifest"]["files"] = [
            item for item in bad["payload"]["file_manifest"]["files"] if item.get("role") != "plan"
        ]
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "FILE_MANIFEST_MISSING_GENERATE_PLAN" not in stdout:
            raise AssertionError("success phase_complete must include generate_plan.json in file_manifest")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_session_state.json"
        bad = load_json(sample_path)
        bad["payload"]["checks"].pop("session_state_checkpoint", None)
        bad["payload"]["file_manifest"]["files"] = [
            item for item in bad["payload"]["file_manifest"]["files"] if not item.get("path", "").endswith("session_state.upy_generate_plugin.json")
        ]
        bad["payload"]["artifacts"] = [
            item for item in bad["payload"].get("artifacts", []) if item.get("type") != "session_state"
        ]
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        for expected in (
            "SESSION_STATE_CHECKPOINT_MISSING",
            "FILE_MANIFEST_MISSING_SESSION_STATE",
            "SESSION_STATE_ARTIFACT_MISSING",
        ):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"success phase_complete must enforce session state {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_artifacts_missing.json"
        bad = load_json(sample_path)
        bad["payload"].pop("artifacts", None)
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "ARTIFACTS_MISSING" not in stdout:
            raise AssertionError("success phase_complete must require payload.artifacts")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_python_cache_manifest.json"
        bad = load_json(sample_path)
        bad["payload"]["file_manifest"]["files"].append(
            {
                "path": "firmware/tasks/__pycache__/business_task.cpython-39.pyc",
                "role": "artifact",
                "status": "created",
            }
        )
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "FILE_MANIFEST_PYTHON_CACHE_PRESENT" not in stdout:
            raise AssertionError("success phase_complete must reject Python cache files in file_manifest")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_session_state_simplified.json"
        bad = load_json(sample_path)
        bad["payload"]["checks"]["session_state_checkpoint"] = {
            "returncode": 0,
            "ok": True,
            "state": {
                "manifest_hash": "a" * 64,
                "git_commit": "b" * 40,
                "usage": {"token_budget_status": "ok", "remaining_budget": None},
            },
        }
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "SESSION_STATE_CHECKPOINT_FIELD_MISSING" not in stdout:
            raise AssertionError("success phase_complete must reject simplified embedded session_state")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_session_hash_is_commit.json"
        bad = load_json(sample_path)
        bad["payload"]["checks"]["session_state_checkpoint"]["state"]["manifest_hash"] = "a" * 40
        bad["payload"]["checks"]["session_state_checkpoint"]["state"]["git_commit"] = "a" * 40
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        if rc == 0 or "SESSION_STATE_CHECKPOINT_MANIFEST_HASH_IS_GIT_COMMIT" not in stdout:
            raise AssertionError("success phase_complete must reject manifest_hash copied from git_commit")

    with tempfile.TemporaryDirectory() as temp_dir:
        for status, expected_code in (
            ("cold_driver_required", "COLD_DRIVER_REQUIRED"),
            ("pending_validation", "DRIVER_NOT_READY"),
            ("unverified", "DRIVER_NOT_READY"),
            ("failed", "DRIVER_NOT_READY"),
        ):
            bad_path = Path(temp_dir) / f"bad_driver_status_{status}.json"
            bad = load_json(sample_path)
            bad["payload"]["manifest_content"]["devices"][0]["driver"] = {
                "source": "cold-driver",
                "status": status,
                "driver_id": "AHT20",
            }
            bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            rc, stdout, _stderr = run_cmd(
                [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
            )
            if rc == 0 or expected_code not in stdout:
                raise AssertionError(f"success phase_complete must reject driver status {status}: {stdout}")

        bad_unknown_status = load_json(sample_path)
        bad_unknown_status["payload"]["manifest_content"]["devices"][0]["driver"] = {
            "source": "cold-driver",
            "status": "local_generated",
        }
        bad_unknown_status_path = Path(temp_dir) / "bad_driver_status_unknown.json"
        bad_unknown_status_path.write_text(json.dumps(bad_unknown_status, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_unknown_status_path)]
        )
        if rc == 0 or "DRIVER_STATUS_UNSUPPORTED" not in stdout:
            raise AssertionError(f"success phase_complete must reject unknown driver status: {stdout}")

        bad_marker = load_json(sample_path)
        bad_marker["payload"]["manifest_content"]["devices"][0]["driver"] = {
            "source": "cold-driver",
            "status": "ready",
            "driver_id": "AHT20",
            "path": "firmware/drivers/aht20_driver/aht20.py",
        }
        bad_marker_path = Path(temp_dir) / "bad_driver_ready_without_marker.json"
        bad_marker_path.write_text(json.dumps(bad_marker, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_marker_path)]
        )
        if rc == 0 or "DRIVER_READY_MARKER_MISSING" not in stdout:
            raise AssertionError(f"success phase_complete must reject ready without SELF_TEST_PASS marker: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        bad_path = Path(temp_dir) / "bad_domain_phase.json"
        bad = load_json(sample_path)
        bad["payload"]["manifest_content"]["domain_phase"] = "scaffold"
        bad["payload"]["manifest_content"]["final_status"] = "scaffolded"
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(bad_path)]
        )
        for expected in ("MANIFEST_DOMAIN_PHASE_NOT_GENERATE", "MANIFEST_FINAL_STATUS_NOT_GENERATED"):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"success phase_complete must reject stale manifest phase field {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "disk-state-session"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest.update(
            {
                "phase": "generate",
                "domain_phase": "generate",
                "final_status": "generated",
                "requirements": {"description": "demo"},
                "devices": [{"name": "LED", "driver": {"source": "none"}}],
                "mcu": {"model": "mock"},
                "pinout": [{"device": "LED", "pin_name": "status", "gpio": "mock"}],
                "generate": {"deploy_plan": valid_deploy_plan(), "behavior_spec": {}, "simulation_hints": {}},
            }
        )
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        phase = load_json(sample_path)
        phase["payload"]["manifest_content"] = manifest
        phase["payload"]["checks"]["session_state_checkpoint"] = {
            "returncode": 0,
            "ok": True,
            "state": {
                "manifest_hash": "a" * 64,
                "git_commit": "b" * 40,
                "usage": {"token_budget_status": "ok", "remaining_budget": None},
            },
        }
        phase_path = session_dir / "phase_complete.upy_generate_plugin.json"
        phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
        (session_dir / "session_state.upy_generate_plugin.json").write_text(
            json.dumps(
                {
                    "session_id": session_dir.name,
                    "phase": "upy-generate-plugin",
                    "manifest_hash": "b" * 40,
                    "git_commit": "b" * 40,
                    "usage": {"token_budget_status": "ok", "remaining_budget": None},
                    "last_checkpoint": "phase_completed",
                    "status": "completed",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_phase_complete_consistency.py"),
                "--phase-complete",
                str(phase_path),
                "--project-dir",
                str(project),
            ]
        )
        if rc == 0 or "SESSION_STATE_DISK_CHECK_FAILED" not in stdout:
            raise AssertionError("phase_complete consistency must validate disk session_state when project-dir is supplied")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "git-mismatch-session"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        rc, stdout, stderr = run_cmd(["git", "init"], cwd=project)
        if rc != 0:
            raise AssertionError(f"git init failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        rc, stdout, stderr = run_cmd(["git", "add", "."], cwd=project)
        if rc != 0:
            raise AssertionError(f"git add failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        rc, stdout, stderr = run_cmd(
            [
                "git",
                "-c",
                "user.name=upy-generate-plugin-test",
                "-c",
                "user.email=upy-generate-plugin-test@example.invalid",
                "commit",
                "-m",
                "test commit",
            ],
            cwd=project,
        )
        if rc != 0:
            raise AssertionError(f"git commit failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        rc, head, stderr = run_cmd(["git", "rev-parse", "HEAD"], cwd=project)
        if rc != 0:
            raise AssertionError(f"git rev-parse failed:\nSTDOUT={head}\nSTDERR={stderr}")
        head = head.strip()
        manifest = load_json(project / "project-manifest.json")
        manifest.update(
            {
                "phase": "generate",
                "domain_phase": "generate",
                "final_status": "generated",
                "requirements": {"description": "demo"},
                "devices": [{"name": "LED", "driver": {"source": "none"}}],
                "mcu": {"model": "mock"},
                "pinout": [{"device": "LED", "pin_name": "status", "gpio": "mock"}],
                "generate": {"deploy_plan": valid_deploy_plan(), "behavior_spec": {}, "simulation_hints": {}},
            }
        )
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        manifest_hash = sha256_file(project / "project-manifest.json")
        bad_commit = "f" * 40 if head != "f" * 40 else "e" * 40
        phase = load_json(sample_path)
        phase["payload"]["manifest_content"] = manifest
        phase["payload"]["generate"]["git"]["commit"] = head
        state = phase["payload"]["checks"]["session_state_checkpoint"]["state"]
        state.update(
            {
                "session_id": session_dir.name,
                "manifest_hash": manifest_hash,
                "git_commit": bad_commit,
                "artifacts": [
                    {"type": "project_manifest", "path": "project/project-manifest.json"},
                    {"type": "generate_plan", "path": "project/generate_plan.json"},
                ],
                "last_ok_artifact": {"type": "generate_plan", "path": "project/generate_plan.json"},
            }
        )
        phase["payload"]["checks"]["session_state_checkpoint"]["state"] = state
        phase_path = session_dir / "phase_complete.upy_generate_plugin.json"
        phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
        (session_dir / "session_state.upy_generate_plugin.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_phase_complete_consistency.py"),
                "--phase-complete",
                str(phase_path),
                "--project-dir",
                str(project),
            ]
        )
        if rc == 0 or "SESSION_STATE_GIT_COMMIT_NOT_HEAD" not in stdout:
            raise AssertionError("phase_complete consistency must reject disk session_state.git_commit != HEAD")

    with tempfile.TemporaryDirectory() as temp_dir:
        ok_path = Path(temp_dir) / "pylint_warning_only.json"
        ok = load_json(sample_path)
        ok["payload"]["lint"]["pylint"] = {"returncode": 12, "ok": True, "warnings": []}
        ok_path.write_text(json.dumps(ok, ensure_ascii=False), encoding="utf-8")
        rc, stdout, stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_phase_complete_consistency.py"), "--phase-complete", str(ok_path)]
        )
        if rc != 0:
            raise AssertionError(f"pylint warning/refactor-only result should pass default policy:\nSTDOUT={stdout}\nSTDERR={stderr}")


def assert_session_state_stale_detection() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "stale-session"
        project = session_dir / "project"
        project.mkdir(parents=True)
        make_project(project, include_plan=False)
        sample = load_json(ROOT / "sample" / "phase_complete.upy_generate_plugin.success.json")
        (session_dir / "phase_complete.upy_generate_plugin.json").write_text(
            json.dumps(sample, ensure_ascii=False),
            encoding="utf-8",
        )
        (session_dir / "generate_phase_log.md").write_text("# stale generate log\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_session_state.py"),
                "--session-dir",
                str(session_dir),
            ]
        )
        for expected in (
            "STALE_GENERATE_PHASE_COMPLETE",
            "STALE_GENERATE_PLAN_MISSING",
            "STALE_GENERATE_FILE_MANIFEST_MISSING_FILES",
        ):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"check_session_state.py must reject stale generate state {expected}: {stdout}")


def assert_session_state_checkpoint() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "checkpoint-session"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        manifest_hash = sha256_file(project / "project-manifest.json")
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "update_session_state.py"),
                "--session-dir",
                str(session_dir),
                "--session-id",
                "checkpoint-session",
                "--checkpoint",
                "tests_generated",
                "--step",
                "quality_gates",
                "--status",
                "running",
                "--idempotency-key",
                "upy-generate-plugin:checkpoint-session:quality-gates:v1",
                "--manifest-hash",
                manifest_hash,
                "--usage-json",
                '{"token_budget_status":"ok","remaining_budget":12345}',
            ]
        )
        if rc != 0:
            raise AssertionError(f"update_session_state.py failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "update_session_state.py"),
                "--session-dir",
                str(session_dir),
                "--project-dir",
                str(project),
                "--check",
            ]
        )
        if rc != 0 or "session_state_checkpoint" not in stdout:
            raise AssertionError(f"update_session_state.py --check should pass:\nSTDOUT={stdout}\nSTDERR={stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "bad-manifest-hash"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        bad_commit = "a" * 40
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "update_session_state.py"),
                "--session-dir",
                str(session_dir),
                "--session-id",
                "bad-manifest-hash",
                "--checkpoint",
                "phase_completed",
                "--step",
                "phase_complete",
                "--status",
                "completed",
                "--idempotency-key",
                "upy-generate-plugin:bad-manifest-hash:phase-complete:v1",
                "--manifest-hash",
                bad_commit,
                "--git-commit",
                bad_commit,
                "--artifacts-json",
                '[{"type":"project_manifest","path":"project/project-manifest.json"},{"type":"generate_plan","path":"project/generate_plan.json"}]',
            ]
        )
        if rc != 0:
            raise AssertionError(f"bad manifest hash setup should write state:\nSTDOUT={stdout}\nSTDERR={stderr}")
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "update_session_state.py"),
                "--session-dir",
                str(session_dir),
                "--project-dir",
                str(project),
                "--check",
            ]
        )
        for expected in ("SESSION_STATE_MANIFEST_HASH_IS_GIT_COMMIT", "SESSION_STATE_MANIFEST_HASH_MISMATCH"):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"update_session_state.py --check must reject bad manifest hash {expected}: {stdout}")

    error_expectations = {
        "NETWORK_DISCONNECTED": True,
        "RATE_LIMITED": True,
        "UPSTREAM_TIMEOUT": True,
        "TOKEN_BUDGET_EXCEEDED": False,
        "MODEL_CONTEXT_EXHAUSTED": False,
        "CANCELLED_BY_USER": False,
    }
    for code, retryable in error_expectations.items():
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "sessions" / f"checkpoint-{code.lower()}"
            session_dir.mkdir(parents=True)
            rc, stdout, stderr = run_cmd(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "update_session_state.py"),
                    "--session-dir",
                    str(session_dir),
                    "--session-id",
                    session_dir.name,
                    "--checkpoint",
                    "dependency_resolved",
                    "--step",
                    "resolve_dependencies",
                    "--status",
                    "retrying" if retryable else "failed",
                    "--idempotency-key",
                    f"upy-generate-plugin:{session_dir.name}:resolve-dependencies:v1",
                    "--manifest-hash",
                    "sha256:checkpoint-manifest",
                    "--usage-json",
                    '{"token_budget_status":"exhausted","remaining_budget":0}' if "TOKEN" in code else '{"token_budget_status":"ok","remaining_budget":999}',
                    "--error-code",
                    code,
                    "--error-message",
                    code.lower(),
                ]
            )
            if rc != 0:
                raise AssertionError(f"interruption session update failed for {code}:\nSTDOUT={stdout}\nSTDERR={stderr}")
            state = json.loads(stdout)["state"]
            if state.get("last_error", {}).get("retryable") is not retryable:
                raise AssertionError(f"{code} retryable flag mismatch: {state.get('last_error')}")
            rc, stdout, stderr = run_cmd(
                [sys.executable, str(ROOT / "scripts" / "update_session_state.py"), "--session-dir", str(session_dir), "--check"]
            )
            if rc != 0:
                raise AssertionError(f"interruption session check failed for {code}:\nSTDOUT={stdout}\nSTDERR={stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "completed-without-commit"
        session_dir.mkdir(parents=True)
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "update_session_state.py"),
                "--session-dir",
                str(session_dir),
                "--session-id",
                "completed-without-commit",
                "--checkpoint",
                "phase_completed",
                "--step",
                "phase_complete",
                "--status",
                "completed",
                "--idempotency-key",
                "upy-generate-plugin:completed-without-commit:phase-complete:v1",
                "--manifest-hash",
                "sha256:checkpoint-manifest",
                "--artifacts-json",
                '[{"type":"project_manifest","path":"project/project-manifest.json"},{"type":"generate_plan","path":"project/generate_plan.json"}]',
            ]
        )
        if rc != 0:
            raise AssertionError(f"completed update without commit should write state:\nSTDOUT={stdout}\nSTDERR={stderr}")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "update_session_state.py"), "--session-dir", str(session_dir), "--check"]
        )
        if rc == 0 or "SESSION_STATE_GIT_COMMIT_MISSING" not in stdout:
            raise AssertionError("completed phase checkpoint must require git_commit")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "completed-without-artifacts"
        project = session_dir / "project"
        session_dir.mkdir(parents=True)
        make_project(project)
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "update_session_state.py"),
                "--session-dir",
                str(session_dir),
                "--project-dir",
                str(project),
                "--session-id",
                "completed-without-artifacts",
                "--checkpoint",
                "phase_completed",
                "--step",
                "phase_complete",
                "--status",
                "completed",
                "--idempotency-key",
                "upy-generate-plugin:completed-without-artifacts:phase-complete:v1",
                "--git-commit",
                "b" * 40,
            ]
        )
        if rc != 0:
            raise AssertionError(f"completed update without artifacts should write state:\nSTDOUT={stdout}\nSTDERR={stderr}")
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "update_session_state.py"),
                "--session-dir",
                str(session_dir),
                "--project-dir",
                str(project),
                "--check",
            ]
        )
        if rc == 0 or "SESSION_STATE_ARTIFACTS_MISSING" not in stdout:
            raise AssertionError("completed phase checkpoint must require resumable artifacts")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "missing-state"
        session_dir.mkdir(parents=True)
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "update_session_state.py"), "--session-dir", str(session_dir), "--check"]
        )
        if rc == 0 or "SESSION_STATE_MISSING" not in stdout:
            raise AssertionError("update_session_state.py --check must reject missing state")


def assert_generated_semantics_negative_cases() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "dialog_task.py"
        task.write_text(
            "async def dialog_tick(pir, touch):\n"
            "    state = 'idle'\n"
            "    last_trigger = 0\n"
            "    return {'state': state, 'last_trigger': last_trigger}\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SEMANTIC_STATE_RESETS_EACH_TICK" not in stdout:
            raise AssertionError("semantic check must reject per-tick state reset")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "voice_task.py"
        task.write_text(
            "async def voice_interact(mic, wifi):\n"
            "    audio_data = mic.read_samples(16000)\n"
            "    _ = audio_data\n"
            "    return wifi.http_post('https://example.invalid', json_data={'audio': 'base64_placeholder'})\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        for expected in (
            "SEMANTIC_PLACEHOLDER_IN_RUNTIME",
            "SEMANTIC_ASYNC_BLOCKING_IO",
            "SEMANTIC_ASYNC_SYNC_IO",
            "SEMANTIC_DATA_READ_UNUSED",
        ):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"semantic check must reject {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "wifi_task.py"
        task.write_text(
            "async def wifi_tick(wifi):\n"
            "    wifi.connect('ssid', 'password')\n"
            "    return True\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SEMANTIC_ASYNC_BLOCKING_IO" not in stdout:
            raise AssertionError("semantic check must reject blocking connect() inside async tasks")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "hidden_blocking_task.py"
        task.write_text(
            "async def async_record(mic):\n"
            "    _record = getattr(mic, 'record')\n"
            "    return _record(5000)\n"
            "\n"
            "async def async_play(speaker, audio):\n"
            "    return speaker.__getattribute__('play')(audio)\n"
            "\n"
            "async def async_lambda_record(mic):\n"
            "    _record = lambda duration_ms: mic.record(duration_ms)\n"
            "    return _record(5000)\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        for expected in (
            "SEMANTIC_ASYNC_DYNAMIC_BLOCKING_LOOKUP",
            "SEMANTIC_ASYNC_DYNAMIC_BLOCKING_CALL",
            "SEMANTIC_ASYNC_BLOCKING_LAMBDA",
        ):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"semantic check must reject dynamically hidden blocking calls {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "wrapper_blocking_task.py"
        task.write_text(
            "def record_adapter(mic):\n"
            "    return mic.record(5000)\n"
            "\n"
            "async def voice_tick(mic):\n"
            "    return record_adapter(mic)\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SEMANTIC_ASYNC_BLOCKING_WRAPPER" not in stdout:
            raise AssertionError(f"semantic check must reject async calls to blocking sync wrappers: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from drivers.inmp441_driver import create_inmp441\n"
            "from drivers.max98357_driver import create_max98357\n"
            "mic = create_inmp441()\n"
            "amp = create_max98357()\n",
            encoding="utf-8",
        )
        manifest = load_json(project / "project-manifest.json")
        manifest["phase"] = "generate"
        manifest["generate"] = {}
        (project / "project-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SEMANTIC_SHARED_I2S_WITHOUT_RESOURCE_PLAN" not in stdout:
            raise AssertionError("semantic check must require resource_plan for shared I2S")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        manifest = load_json(project / "project-manifest.json")
        manifest["devices"] = [
            {"name": "WS2812", "interface": "GPIO"},
            {"name": "MAX98357", "interface": "I2S"},
        ]
        manifest["pinout"] = [
            {"device": "MAX98357", "pin_name": "BCLK", "gpio": "8", "type": "i2s_bck", "bus": "i2s0"},
            {"device": "MAX98357", "pin_name": "LRC", "gpio": "9", "type": "i2s_ws", "bus": "i2s0"},
            {"device": "WS2812", "pin_name": "DIN", "gpio": "21", "type": "gpio_out"},
        ]
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from machine import I2C, Pin\n"
            "i2c0 = I2C(0, scl=Pin(9), sda=Pin(8), freq=400000)\n"
            "_ = i2c0.scan()\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        for expected in ("SEMANTIC_UNDECLARED_I2C_SCAN", "SEMANTIC_I2C_PIN_CONFLICT"):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"semantic check must reject generated I2C misuse {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from machine import Timer\n"
            "from lib.scheduler.timer_sched import Scheduler\n"
            "tim = Timer(-1)\n"
            "sc = Scheduler()\n"
            "sc.register(lambda: None)\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        for expected in ("SCHEDULER_TIMER_INVALID_FOR_PORT", "SCHEDULER_API_METHOD_MISSING"):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"semantic check must reject scheduler issue {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        (project / "firmware" / "lib" / "scheduler" / "timer_sched.py").write_text(
            "from machine import Timer\n\n"
            "class Scheduler:\n"
            "    def __init__(self, timer_id=-1, tick_ms=100):\n"
            "        self._timer = Timer(timer_id)\n"
            "    def add_task(self, callback, interval_ms, name=None): return name\n",
            encoding="utf-8",
        )
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from lib.scheduler.timer_sched import Scheduler\n"
            "def tick(): pass\n"
            "sc = Scheduler(timer_id=-1)\n"
            "sc.add_task(tick, 100, name='tick')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" not in stdout:
            raise AssertionError(f"semantic check must reject Scheduler(timer_id=-1): {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        (project / "firmware" / "lib" / "scheduler" / "timer_sched.py").write_text(
            "from machine import Timer\n\n"
            "class Scheduler:\n"
            "    def __init__(self, timer_id=-1, tick_ms=100):\n"
            "        self._timer = Timer(timer_id)\n"
            "    def add_task(self, callback, interval_ms, name=None): return name\n",
            encoding="utf-8",
        )
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from lib.scheduler.timer_sched import Scheduler\n"
            "def tick(): pass\n"
            "sc = Scheduler()\n"
            "sc.add_task(tick, 100, name='tick')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" not in stdout:
            raise AssertionError(f"semantic check must reject Scheduler() when default timer_id=-1: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        (project / "firmware" / "lib" / "scheduler" / "timer_sched.py").write_text(
            "from machine import Timer\n\n"
            "class Scheduler:\n"
            "    def __init__(self, timer_id=-1, tick_ms=100, idle_cb=None, error_cb=None):\n"
            "        self._timer = Timer(timer_id)\n"
            "        self._error_cb = error_cb\n"
            "    def add_task(self, callback, interval_ms, name=None): return name\n",
            encoding="utf-8",
        )
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "import sys\n"
            "import time\n"
            "from lib.scheduler.timer_sched import Scheduler\n"
            "from lib import logger\n"
            "def _on_scheduler_error(tid, exc):\n"
            "    sys.print_exception(exc)\n"
            "    logger.exception(exc, '[t=%dms] task failed' % time.ticks_ms())\n"
            "def tick(): pass\n"
            "sc = Scheduler(timer_id=0, error_cb=_on_scheduler_error)\n"
            "sc.add_task(tick, 100, name='tick')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc != 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" in stdout:
            raise AssertionError(f"semantic check must allow ESP32 main.py with explicit timer_id=0 while scheduler default is -1: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        set_mcu_model(project, "STM32")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from lib.scheduler.timer_sched import Scheduler\n"
            "def tick(): pass\n"
            "sc = Scheduler(timer_id=-1)\n"
            "sc.add_task(tick, 100, name='tick')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" not in stdout:
            raise AssertionError(f"semantic check must reject virtual Timer(-1) on general hardware-timer ports: {stdout}")

    for model in ("Raspberry Pi Pico W", "Zephyr"):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            make_project(project, mode="timer")
            set_mcu_model(project, model)
            main_py = project / "firmware" / "main.py"
            main_py.write_text(
                "import sys\n"
                "import time\n"
                "from lib.scheduler.timer_sched import Scheduler\n"
                "from lib import logger\n"
                "def _on_scheduler_error(tid, exc):\n"
                "    sys.print_exception(exc)\n"
                "    logger.exception(exc, '[t=%dms] task failed' % time.ticks_ms())\n"
                "def tick(): pass\n"
                "sc = Scheduler(timer_id=-1, error_cb=_on_scheduler_error)\n"
                "sc.add_task(tick, 100, name='tick')\n",
                encoding="utf-8",
            )
            rc, stdout, _stderr = run_cmd(
                [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
            )
            if rc != 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" in stdout:
                raise AssertionError(f"semantic check must allow virtual Timer(-1) on {model}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from conf import LOG_DIR, LOG_FILES_MAX, LOG_LINES_PER_FILE\n"
            "from lib import logger\n"
            "logger.install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)\n"
            "logger.info('missing timestamp')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "LOGGER_ROTATING_TIMESTAMP_MISSING" not in stdout:
            raise AssertionError(f"semantic check must require timestamped rotating logger calls: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "import time\n"
            "from conf import LOG_DIR, LOG_FILES_MAX, LOG_LINES_PER_FILE\n"
            "from lib import logger\n"
            "logger.install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)\n"
            "logger.info('[t=%dms] boot' % time.ticks_ms())\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "LOGGER_STARTUP_FATAL_GUARD_MISSING" not in stdout:
            raise AssertionError(f"semantic check must require startup fatal guard: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "import sys\n"
            "import time\n"
            "from conf import LOG_DIR, LOG_FILES_MAX, LOG_LINES_PER_FILE\n"
            "from lib import logger\n"
            "from lib.scheduler.timer_sched import Scheduler\n"
            "def _main():\n"
            "    logger.install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)\n"
            "    logger.info('[t=%dms] boot' % time.ticks_ms())\n"
            "    Scheduler().add_task(lambda: None, 100, name='tick')\n"
            "try:\n"
            "    _main()\n"
            "except Exception as exc:\n"
            "    sys.print_exception(exc)\n"
            "    logger.exception(exc, '[t=%dms] startup failed' % time.ticks_ms())\n"
            "    raise\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_ERROR_CALLBACK_MISSING" not in stdout:
            raise AssertionError(f"semantic check must require Scheduler(error_cb=...): {stdout}")


def assert_cloud_integrations_policy() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["phase"] = "generate"
        manifest["generate"] = {
            "cloud_integrations": [
                {
                    "provider_id": "aliyun_bailian",
                    "category": "llm",
                    "services": ["chat_completions"],
                    "mode": "direct_https",
                    "official_links": {
                        "docs": "https://help.aliyun.com/zh/model-studio/get-api-key",
                        "console": "https://bailian.console.aliyun.com/",
                        "pricing": "https://help.aliyun.com/zh/model-studio/",
                    },
                    "credential_management": {
                        "requires_credentials": True,
                        "status": "deferred_to_deploy",
                        "secret_names": ["DASHSCOPE_API_KEY"],
                        "storage": "device_secrets_file",
                        "forbidden_locations": ["firmware/conf.py", "git", "phase_complete"],
                    },
                    "user_action_required": [
                        "Create API Key in provider console",
                        "Enable billing or token plan if required",
                        "Provide secret during deploy permission prompt",
                    ],
                    "deploy_ready": False,
                    "deploy_blocker": "credentials_deferred_to_deploy",
                }
            ]
        }
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_cloud_integrations.py"),
                "--project-dir",
                str(project),
                "--next-phase",
                "upy-deploy-plugin",
            ]
        )
        if rc != 0:
            raise AssertionError(f"deferred-to-deploy cloud credentials should pass:\nSTDOUT={stdout}\nSTDERR={stderr}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        conf = project / "firmware" / "conf.py"
        conf.write_text(conf.read_text(encoding="utf-8") + "\nOPENAI_API_KEY = 'sk-test1234567890abcdef'\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_cloud_integrations.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "CLOUD_SECRET_HARDCODED" not in stdout:
            raise AssertionError("cloud integration check must reject hard-coded API secrets")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["phase"] = "generate"
        manifest["requirements"] = {"description": "Voice assistant using cloud ASR LLM TTS APIs"}
        manifest["generate"] = {"deploy_plan": {"requires_secrets": True}}
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        (project / "firmware" / "conf.py").write_text(
            (project / "firmware" / "conf.py").read_text(encoding="utf-8")
            + "\nCLOUD_ASR_URL = 'YOUR_ASR_API_URL'\nCLOUD_LLM_URL = 'YOUR_LLM_API_URL'\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_cloud_integrations.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "CLOUD_INTEGRATIONS_REQUIRED" not in stdout:
            raise AssertionError("cloud integration check must require a plan when cloud APIs are used")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["phase"] = "generate"
        manifest["generate"] = {
            "cloud_integrations": [
                {
                    "provider_id": "volcengine_ark",
                    "category": "llm",
                    "services": ["chat_completions"],
                    "credential_management": {"requires_credentials": True, "status": "mock_only", "secret_names": []},
                    "deploy_ready": False,
                }
            ]
        }
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_cloud_integrations.py"),
                "--project-dir",
                str(project),
                "--next-phase",
                "upy-deploy-plugin",
            ]
        )
        for expected in ("CLOUD_OFFICIAL_LINKS_MISSING", "CLOUD_CREDENTIALS_REQUIRED"):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"cloud integration check must reject {expected}: {stdout}")


def assert_final_review_consistency() -> None:
    sample_path = ROOT / "sample" / "phase_complete.upy_generate_plugin.success.json"
    rc, stdout, stderr = run_cmd(
        [sys.executable, str(ROOT / "scripts" / "check_final_review_consistency.py"), "--phase-complete", str(sample_path)]
    )
    if rc != 0:
        raise AssertionError(f"valid review consistency failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
    with tempfile.TemporaryDirectory() as temp_dir:
        phase_path = Path(temp_dir) / "phase.json"
        log_path = Path(temp_dir) / "generate_phase_log.md"
        phase = load_json(sample_path)
        log_path.write_text("## 审查结果\n\n### 关键 Bug\n\n| 严重 | firmware/tasks/dialog_task.py |\n", encoding="utf-8")
        phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_final_review_consistency.py"),
                "--phase-complete",
                str(phase_path),
                "--log",
                str(log_path),
            ]
        )
        if rc == 0 or "SUCCESS_WITH_BLOCKING_REVIEW_FINDINGS" not in stdout:
            raise AssertionError("success with blocking final review findings must be rejected")


def assert_local_runner() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "generate-session"
        cmd = [
            sys.executable,
            str(ROOT / "test" / "run_local_mock_session.py"),
            "--session-dir",
            str(session_dir),
            "--mode",
            "timer",
            "--next-phase",
            "simulate",
            "--force",
            "--allow-git-commit",
            "--write-phase-complete",
        ]
        rc, stdout, stderr = run_cmd(cmd)
        if rc != 0:
            raise AssertionError(f"local runner failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        summary = json.loads(stdout)
        if summary["status"] != "success":
            raise AssertionError(f"runner status not success: {summary['status']}")
        payload = summary["phase_complete"]["payload"]
        if payload["next_phase"] != "upy-simulate-plugin":
            raise AssertionError("runner should honor next_phase simulate")
        if not (session_dir / "phase_complete.upy_generate_plugin.json").exists():
            raise AssertionError("runner should write phase_complete when requested")
        if not (session_dir / "project" / "generate_plan.json").exists():
            raise AssertionError("runner should write generate_plan.json before quality gates")
        manifest = load_json(session_dir / "project" / "project-manifest.json")
        if manifest.get("phase") != "generate":
            raise AssertionError("project manifest must advance to generate")
        file_roles = {entry.get("role") for entry in payload["file_manifest"]["files"]}
        if {"plan", "business_task", "entrypoint", "mock", "pc_test", "device_test", "artifact"} - file_roles:
            raise AssertionError("file_manifest should classify generated files")
        if not (session_dir / "session_state.upy_generate_plugin.json").exists():
            raise AssertionError("runner should write resumable session state")
        if "pylint" not in payload["lint"] or "pc_unittest" not in payload["tests"]:
            raise AssertionError("phase_complete must expose pylint and PC unittest gate results")
        for gate in (
            "flake8",
            "pylint",
            "pc_unittest",
            "task_no_machine_import",
            "device_unittest_subset",
            "runtime_dependencies",
            "doc_evidence",
            "session_state_checkpoint",
        ):
            if payload["checks"][gate].get("ok") is False:
                raise AssertionError(f"runner quality gate failed: {gate}")
        if "cloud_integrations" not in payload["checks"]:
            raise AssertionError("runner phase_complete must expose cloud_integrations gate")
        cloud_plan = manifest.get("generate", {}).get("cloud_integrations", [])
        if not cloud_plan:
            raise AssertionError("runner manifest must include a cloud_integrations plan for local coverage")
        rc, stdout, stderr = run_cmd(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_phase_complete_consistency.py"),
                "--phase-complete",
                str(session_dir / "phase_complete.upy_generate_plugin.json"),
                "--project-dir",
                str(session_dir / "project"),
            ]
        )
        if rc != 0:
            raise AssertionError(f"runner phase_complete consistency failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        project_dir = session_dir / "project"
        cache_paths = [
            path.relative_to(project_dir).as_posix()
            for path in project_dir.rglob("*")
            if path.name == "__pycache__" or path.suffix == ".pyc"
        ]
        if cache_paths:
            raise AssertionError(f"runner must not leave Python cache files in project: {cache_paths}")
        rc, stdout, stderr = run_cmd(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=project_dir)
        if rc != 0:
            raise AssertionError(f"failed to inspect runner git commit:\nSTDOUT={stdout}\nSTDERR={stderr}")
        tracked_cache = [line for line in stdout.splitlines() if "__pycache__/" in line or line.endswith(".pyc")]
        if tracked_cache:
            raise AssertionError(f"runner git commit must not include Python cache files: {tracked_cache}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "generate-micropython-lib"
        project = session_dir / "project"
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["devices"] = [
            {
                "name": "BLE stack",
                "type": "middleware",
                "driver": {
                    "source": "micropython_lib",
                    "package_name": "aioble",
                    "install_cmd": "mpremote mip install aioble",
                    "repo_url": "https://github.com/micropython/micropython-lib",
                    "search_provider": "micropython_lib_classifier",
                    "api_ref": {
                        "import": "import aioble",
                        "usage": "Use documented aioble async helpers; do not call low-level bluetooth.BLE directly unless cited separately",
                    },
                },
            }
        ]
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        cmd = [
            sys.executable,
            str(ROOT / "test" / "run_local_mock_session.py"),
            "--session-dir",
            str(session_dir),
            "--mode",
            "timer",
            "--next-phase",
            "stop",
            "--force",
            "--allow-git-commit",
            "--write-phase-complete",
        ]
        rc, stdout, stderr = run_cmd(cmd)
        if rc != 0:
            raise AssertionError(f"local runner with micropython_lib device failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        updated = load_json(project / "project-manifest.json")
        deps = updated.get("runtime_dependencies", {}).get("mip", [])
        if not any(item.get("package") == "aioble" and item.get("source") == "micropython_lib" for item in deps):
            raise AssertionError(f"local runner must propagate micropython_lib mip dependency: {deps}")
        phase_complete = load_json(session_dir / "phase_complete.upy_generate_plugin.json")
        phase_deps = (
            phase_complete.get("payload", {})
            .get("manifest_content", {})
            .get("generate", {})
            .get("runtime_dependencies", {})
            .get("mip", [])
        )
        if not any(item.get("package") == "aioble" for item in phase_deps):
            raise AssertionError(f"phase_complete must expose micropython_lib mip dependency for deploy: {phase_deps}")

    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "generate-upypi"
        project = session_dir / "project"
        make_project(project)
        manifest = load_json(project / "project-manifest.json")
        manifest["devices"] = [
            {
                "name": "BMA423 IMU",
                "type": "imu",
                "driver": {
                    "source": "upypi",
                    "package_name": "bma423_driver",
                    "version": "1.0.0",
                    "module": "bma423",
                    "url": "https://upypi.net/pkgs/bma423_driver/1.0.0",
                    "package_json_url": "https://upypi.net/pkgs/bma423_driver/1.0.0/package.json",
                    "search_provider": "upy-pkg-guide",
                    "search_mode": "real",
                },
            }
        ]
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        cmd = [
            sys.executable,
            str(ROOT / "test" / "run_local_mock_session.py"),
            "--session-dir",
            str(session_dir),
            "--mode",
            "timer",
            "--next-phase",
            "stop",
            "--force",
            "--allow-git-commit",
            "--write-phase-complete",
        ]
        rc, stdout, stderr = run_cmd(cmd)
        if rc != 0:
            raise AssertionError(f"local runner with upypi device failed:\nSTDOUT={stdout}\nSTDERR={stderr}")
        updated = load_json(project / "project-manifest.json")
        deps = updated.get("runtime_dependencies", {}).get("mip", [])
        if not any(
            item.get("package") == "https://upypi.net/pkgs/bma423_driver/1.0.0"
            and item.get("source") == "upypi"
            for item in deps
        ):
            raise AssertionError(f"local runner must propagate upypi mip dependency: {deps}")
        phase_complete = load_json(session_dir / "phase_complete.upy_generate_plugin.json")
        phase_deps = (
            phase_complete.get("payload", {})
            .get("manifest_content", {})
            .get("generate", {})
            .get("runtime_dependencies", {})
            .get("mip", [])
        )
        if not any(item.get("package") == "https://upypi.net/pkgs/bma423_driver/1.0.0" for item in phase_deps):
            raise AssertionError(f"phase_complete must expose upypi mip dependency for deploy: {phase_deps}")


def assert_session_chain_validator_negative_case() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "chain-session"
        session_dir.mkdir(parents=True)
        project = session_dir / "project"
        make_project(project)
        subprocess.run(["git", "init"], cwd=project, text=True, capture_output=True, check=False)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=project, text=True, capture_output=True, check=False)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, text=True, capture_output=True, check=False)
        subprocess.run(["git", "add", "."], cwd=project, text=True, capture_output=True, check=False)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=project, text=True, capture_output=True, check=False)
        first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, text=True, capture_output=True, check=False).stdout.strip()
        (project / "project-manifest.json").write_text(
            json.dumps({**load_json(project / "project-manifest.json"), "phase": "generate", "final_status": "generated"}, ensure_ascii=False),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=project, text=True, capture_output=True, check=False)
        subprocess.run(["git", "commit", "-m", "final"], cwd=project, text=True, capture_output=True, check=False)
        (project / "-").write_text('{"status":"success"}\n', encoding="utf-8")

        for name, phase, result in (
            ("phase_complete.analyze.json", "analyze", "success"),
            ("phase_complete.select_hw.json", "select-hw", "success"),
            ("phase_complete.upy_flash_mpy_firmware_plugin.json", "upy-flash-mpy-firmware-plugin", "success"),
        ):
            (session_dir / name).write_text(
                json.dumps(
                    {
                        "type": "phase_complete",
                        "phase": phase,
                        "session_id": session_dir.name,
                        "payload": {"phase": phase, "result": result, "next_phase": None},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        scaffold = {
            "type": "phase_complete",
            "phase": "upy-scaffold-plugin",
            "session_id": session_dir.name,
            "payload": {
                "phase": "scaffold",
                "result": "success",
                "next_phase": "upy-generate-plugin",
                "runtime_context": {"session_root": f"sessions/{session_dir.name}", "project_root": f"sessions/{session_dir.name}/project"},
                "file_manifest": {"files": []},
                "artifacts": [{"type": "file_manifest", "path": f"sessions/{session_dir.name}/scaffold_file_manifest.json"}],
                "lint": {"returncode": 0, "stdout": "", "stderr": ""},
                "structured_errors": [],
            },
        }
        (session_dir / "phase_complete.upy_scaffold_plugin.json").write_text(json.dumps(scaffold, ensure_ascii=False), encoding="utf-8")
        (session_dir / "scaffold_file_manifest.json").write_text('{"files":[]}\n', encoding="utf-8")

        generate = load_json(ROOT / "sample" / "phase_complete.upy_generate_plugin.success.json")
        generate["session_id"] = session_dir.name
        generate["payload"]["runtime_context"] = {
            "session_root": f"sessions/{session_dir.name}",
            "project_root": f"sessions/{session_dir.name}/project",
        }
        generate["payload"]["generate"]["git"]["commit"] = first
        generate["payload"]["manifest_content"].setdefault("generate", {}).setdefault("git", {})
        generate["payload"]["manifest_content"]["generate"]["git"]["commit"] = first
        (session_dir / "phase_complete.upy_generate_plugin.json").write_text(json.dumps(generate, ensure_ascii=False), encoding="utf-8")
        (session_dir / "session_state.upy_generate_plugin.json").write_text(
            json.dumps({"git_commit": first, "checkpoint": "phase_completed", "status": "success"}, ensure_ascii=False),
            encoding="utf-8",
        )

        deploy = {
            "type": "phase_complete",
            "phase": "upy-deploy-plugin",
            "session_id": session_dir.name,
            "payload": {
                "phase": "upy-deploy-plugin",
                "result": "success",
                "runtime_context": {"session_root": f"sessions/{session_dir.name}", "project_root": f"sessions/{session_dir.name}/project"},
                "deploy_result": {"result": "PASS"},
                "manifest_content": {"phase": "upy-deploy-plugin", "deploy_result": {"result": "PASS"}},
                "artifacts": [{"type": "deploy_log", "path": f"sessions/{session_dir.name}/phase_complete.upy_deploy_plugin.json"}],
            },
        }
        (session_dir / "phase_complete.upy_deploy_plugin.json").write_text(json.dumps(deploy, ensure_ascii=False), encoding="utf-8")
        rc, stdout, stderr = run_cmd([
            sys.executable,
            str(REPO / "shared-plugin-scripts" / "workflow" / "session_chain_validate.py"),
            "--session-dir",
            str(session_dir),
            "--require-deploy",
        ])
        if rc == 0:
            raise AssertionError(f"bad session chain must fail:\nSTDOUT={stdout}\nSTDERR={stderr}")
        for expected in ("PHASE_VALIDATOR_FAILED", "PROJECT_TEMP_ARTIFACT_PRESENT"):
            if expected not in stdout:
                raise AssertionError(f"session chain validator missing {expected}:\n{stdout}")


def main() -> int:
    tests = [
        assert_json_files_parse,
        assert_references_and_knowledge_docs,
        assert_plugin_json_shape,
        assert_resolver_offline,
        assert_download_drivers_offline,
        assert_check_scripts,
        assert_check_scripts_negative_cases,
        assert_mpy_import_fallback_policy,
        assert_phase_complete_consistency,
        assert_session_state_stale_detection,
        assert_session_state_checkpoint,
        assert_generated_semantics_negative_cases,
        assert_cloud_integrations_policy,
        assert_final_review_consistency,
        assert_local_runner,
        assert_session_chain_validator_negative_case,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print(f"[OK] {len(tests)} upy-generate-plugin smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
