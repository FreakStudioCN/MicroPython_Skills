#!/usr/bin/env python3
"""Local mock runner for upy-generate-plugin.

This runner is intentionally conservative: it creates a minimal generated
firmware layer for protocol and script validation. Real business code should
still be authored by the LLM following SKILL.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SCRIPTS = ROOT / "scripts"
UPYPI_BASE = "https://upypi.net"
SCAFFOLD_RUNNER = REPO / "upy-scaffold-plugin" / "scripts" / "apply_scaffold.py"
FLASH_SAMPLE = REPO / "upy-flash-mpy-firmware-plugin" / "sample" / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_c3_success.json"
SELECT_SAMPLE = REPO / "upy-select-hw-plugin" / "sample" / "phase_complete.select_hw.success.json"


def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def utc_now() -> str:
    helper = REPO / "upy-project-gen-toolchain-spec" / "scripts" / "workflow_time.py"
    if helper.exists():
        result = subprocess.run(
            [sys.executable, str(helper), "--json"],
            text=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)["utc"]
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else "" for line in text.splitlines(True))


def run_session_state(
    session_dir: Path,
    checkpoint: str,
    step: str,
    status: str,
    artifacts: list[dict[str, Any]] | None = None,
    error: dict[str, Any] | None = None,
    attempt: int | None = None,
    manifest_hash: str = "",
    git_commit: str = "",
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(SCRIPTS / "update_session_state.py"),
        "--session-dir",
        str(session_dir),
        "--session-id",
        session_dir.name,
        "--checkpoint",
        checkpoint,
        "--step",
        step,
        "--status",
        status,
        "--idempotency-key",
        f"upy-generate-plugin:{session_dir.name}:{step}:v1",
    ]
    if manifest_hash:
        cmd.extend(["--manifest-hash", manifest_hash])
    if git_commit:
        cmd.extend(["--git-commit", git_commit])
    if usage:
        cmd.extend(["--usage-json", json.dumps(usage, ensure_ascii=False)])
    if attempt is not None:
        cmd.extend(["--attempt", str(attempt)])
    if artifacts:
        cmd.extend(["--artifacts-json", json.dumps(artifacts, ensure_ascii=False)])
    if error:
        cmd.extend(
            [
                "--error-code",
                str(error.get("code", "UPSTREAM_TIMEOUT")),
                "--error-message",
                str(error.get("message", "")),
                "--error-details-json",
                json.dumps(error.get("details", {}), ensure_ascii=False),
            ]
        )
    result = run_cmd(cmd)
    try:
        payload = json.loads(result["stdout"]) if result["stdout"].strip() else {}
    except json.JSONDecodeError:
        payload = {"parse_error": result["stdout"]}
    if result["returncode"] != 0:
        return {
            "returncode": result["returncode"],
            "payload": payload,
            "ok": False,
            "errors": [{"code": "SESSION_STATE_UPDATE_FAILED", "message": result["stderr"] or result["stdout"]}],
            "warnings": [],
        }
    return payload if isinstance(payload, dict) else {"payload": payload, "ok": True, "errors": [], "warnings": []}


def relative_to_artifact(path: Path, artifact_root: Path | None) -> str:
    if artifact_root:
        try:
            return path.resolve().relative_to(artifact_root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_manifest_hash(project_dir: Path) -> str:
    manifest_path = project_dir / "project-manifest.json"
    return sha256_file(manifest_path) if manifest_path.exists() else "unknown"


def run_cmd(cmd: list[str], cwd: Path | None = None, input_text: str | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": " ".join(cmd),
        "cwd": str(cwd) if cwd else "",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def ensure_scaffold_project(session_dir: Path, manifest_path: Path, mode: str) -> dict[str, Any]:
    project_dir = session_dir / "project"
    if (project_dir / "project-manifest.json").exists():
        phase_path = session_dir / "phase_complete.upy_scaffold_plugin.json"
        phase = load_json(phase_path) if phase_path.exists() else {"payload": {"manifest_content": load_json(project_dir / "project-manifest.json")}}
        return normalize_scaffold_hardware_baseline(project_dir, session_dir, phase, mode)
    if not SCAFFOLD_RUNNER.exists():
        project_dir.mkdir(parents=True, exist_ok=True)
        return normalize_scaffold_hardware_baseline(project_dir, session_dir, create_minimal_scaffold(project_dir, session_dir, mode), mode)
    cmd = [
        sys.executable,
        str(SCAFFOLD_RUNNER),
        "--session-dir",
        str(session_dir),
        "--manifest",
        str(manifest_path),
        "--mode",
        mode,
        "--modules",
        "logger,time_helper,maintenance,flash_device,log_tools",
        "--write-phase-complete",
    ]
    result = run_cmd(cmd)
    if result["returncode"] != 0:
        return normalize_scaffold_hardware_baseline(project_dir, session_dir, create_minimal_scaffold(project_dir, session_dir, mode), mode)
    return normalize_scaffold_hardware_baseline(project_dir, session_dir, load_json(session_dir / "phase_complete.upy_scaffold_plugin.json"), mode)


def normalize_scaffold_hardware_baseline(
    project_dir: Path,
    session_dir: Path,
    phase_complete: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    payload = phase_complete.setdefault("payload", {})
    manifest = payload.get("manifest_content")
    if not isinstance(manifest, dict):
        manifest = load_json(project_dir / "project-manifest.json") if (project_dir / "project-manifest.json").exists() else {}
    normalized = deepcopy(manifest)
    normalized["phase"] = "scaffold"
    normalized.setdefault("project_name", "mock_project")
    normalized.setdefault("scaffold_mode", mode)
    requirements = normalized.get("requirements")
    if not isinstance(requirements, dict) or not requirements.get("description"):
        normalized["requirements"] = {"description": normalized.get("project_name", "mock project")}
    if not isinstance(normalized.get("devices"), list) or not normalized.get("devices"):
        normalized["devices"] = [{"name": "LED", "driver": {"source": "none"}}]
    if not isinstance(normalized.get("mcu"), dict):
        normalized["mcu"] = {"model": "mock"}
    if not isinstance(normalized.get("pinout"), list) or not normalized.get("pinout"):
        normalized["pinout"] = [{"device": "LED", "pin_name": "status", "gpio": "mock"}]
    payload["manifest_content"] = normalized
    write_json(project_dir / "project-manifest.json", normalized)
    write_json(session_dir / "phase_complete.upy_scaffold_plugin.json", phase_complete)
    return phase_complete


def create_minimal_scaffold(project_dir: Path, session_dir: Path, mode: str) -> dict[str, Any]:
    project_dir.mkdir(parents=True, exist_ok=True)
    files = {
        ".flake8": "[flake8]\nmax-line-length = 120\nbuiltins = const\n",
        "firmware/board.py": "I2C0_SCL = 6\nI2C0_SDA = 5\n",
        "firmware/conf.py": (
            "PROJECT_NAME = 'mock_project'\n"
            "VERSION = '0.1.0'\n"
            "SAMPLE_INTERVAL_MS = 1000\n"
            "LOG_DIR = '/log'\n"
            "LOG_FILES_MAX = 4\n"
            "LOG_LINES_PER_FILE = 150\n"
            "LOG_LEVEL = 'INFO'\n"
        ),
        "firmware/main.py": "import time\ntime.sleep(3)\nprint('scaffold boot')\n",
        "firmware/lib/logger/__init__.py": (
            "DEBUG = 10\n"
            "INFO = 20\n"
            "\n"
            "def install_rotating(log_dir, max_files=4, lines_per_file=150):\n"
            "    return None\n"
            "\n"
            "def setLevel(level):\n"
            "    return None\n"
            "\n"
            "class _Logger:\n"
            "    def info(self, msg): print(msg)\n"
            "    def warning(self, msg): print(msg)\n"
            "    def error(self, msg): print(msg)\n"
            "    def debug(self, msg): print(msg)\n"
            "\n"
            "def getLogger(name):\n"
            "    return _Logger()\n"
            "\n"
            "def info(msg): print(msg)\n"
            "def warning(msg): print(msg)\n"
            "def error(msg): print(msg)\n"
            "def debug(msg): print(msg)\n"
            "def exception(exc, msg): print(msg)\n"
        ),
        "firmware/lib/time_helper.py": (
            "def timed_function(fn):\n"
            "    return fn\n"
            "\n"
            "def timed_coro(fn):\n"
            "    return fn\n"
        ),
        "firmware/lib/scheduler/timer_sched.py": (
            "class Scheduler:\n"
            "    def __init__(self, tick_ms=100, idle_cb=None, error_cb=None):\n"
            "        self.tasks = []\n"
            "        self.error_cb = error_cb\n"
            "\n"
            "    def add_task(self, callback, interval_ms, name=None):\n"
            "        self.tasks.append((callback, interval_ms, name))\n"
            "        return name or str(len(self.tasks))\n"
        ),
        "project-manifest.json": json.dumps(
            {
                "phase": "scaffold",
                "project_name": "mock_project",
                "scaffold_mode": mode,
                "devices": [{"name": "LED", "driver": {"source": "none"}}],
                "requirements": {"description": "Blink LED periodically"},
            },
            ensure_ascii=False,
            indent=2,
        ),
    }
    for rel, content in files.items():
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    phase_complete = {
        "type": "phase_complete",
        "phase": "upy-scaffold-plugin",
        "payload": {
            "phase": "scaffold",
            "result": "success",
            "next_phase": "upy-generate-plugin",
            "runtime_context": {
                "session_root": relative_to_artifact(session_dir, session_dir.parent.parent if session_dir.parent.name == "sessions" else session_dir),
                "project_root": relative_to_artifact(project_dir, session_dir.parent.parent if session_dir.parent.name == "sessions" else session_dir),
            },
            "manifest_content": load_json(project_dir / "project-manifest.json"),
        },
    }
    write_json(session_dir / "phase_complete.upy_scaffold_plugin.json", phase_complete)
    return phase_complete


def extract_manifest(phase_complete: dict[str, Any]) -> dict[str, Any]:
    payload = phase_complete.get("payload", {})
    manifest = payload.get("manifest_content")
    if isinstance(manifest, dict):
        return deepcopy(manifest)
    return {}


def target_allows_virtual_timer(manifest: dict[str, Any]) -> bool:
    text = json.dumps(manifest.get("mcu", {}), ensure_ascii=False).lower()
    return any(marker in text for marker in ("pico", "rp2", "rp2040", "rp2350", "zephyr"))


def scheduler_init_args(manifest: dict[str, Any]) -> str:
    if target_allows_virtual_timer(manifest):
        return "timer_id=-1, error_cb=_on_scheduler_error"
    return "timer_id=0, error_cb=_on_scheduler_error"


def generated_files(manifest: dict[str, Any], mode: str) -> dict[str, str]:
    project_name = manifest.get("project_name", "upy_project")
    sync_task_body = (
        "import time\n\n"
        "from conf import BUSINESS_ENABLED, SAMPLE_INTERVAL_MS\n"
        "from lib.time_helper import timed_function as _scaffold_timed_function\n\n"
        "\n"
        "def _timed_function(fn):\n"
        "    if hasattr(time, 'ticks_us'):\n"
        "        return _scaffold_timed_function(fn)\n"
        "    return fn\n\n"
        "\n"
        "def _log(level, message):\n"
        "    try:\n"
        "        from lib import logger\n"
        "        getattr(logger, level)(message)\n"
        "    except Exception:\n"
        "        pass\n"
        "    print(message)\n\n"
        "\n"
        "@_timed_function\n"
        "def business_tick(status_output=None):\n"
        "    result = {'enabled': BUSINESS_ENABLED, 'interval_ms': SAMPLE_INTERVAL_MS, 'ok': True}\n"
        "    msg = '[task] business tick {} ms'.format(SAMPLE_INTERVAL_MS)\n"
        "    _log('debug', msg)\n"
        "    if not BUSINESS_ENABLED:\n"
        "        result['ok'] = False\n"
        "        return result\n"
        "    if status_output is None:\n"
        "        _log('warning', '[task] status output missing')\n"
        "        result['missing_output'] = True\n"
        "        return result\n"
        "    try:\n"
        "        status_output.write(msg)\n"
        "    except Exception as exc:\n"
        "        _log('warning', '[task] status output failed: {}'.format(exc))\n"
        "        result['ok'] = False\n"
        "        result['error'] = str(exc)\n"
        "    result['message'] = msg\n"
        "    return result\n"
    )
    async_task_body = (
        "import time\n\n"
        "from conf import BUSINESS_ENABLED, SAMPLE_INTERVAL_MS\n"
        "from lib.time_helper import timed_coro as _scaffold_timed_coro\n\n"
        "\n"
        "def _timed_coro(fn):\n"
        "    if hasattr(time, 'ticks_us'):\n"
        "        return _scaffold_timed_coro(fn)\n"
        "    return fn\n\n"
        "\n"
        "def _log(level, message):\n"
        "    try:\n"
        "        from lib import logger\n"
        "        getattr(logger, level)(message)\n"
        "    except Exception:\n"
        "        pass\n"
        "    print(message)\n\n"
        "\n"
        "@_timed_coro\n"
        "async def business_tick(status_output=None):\n"
        "    result = {'enabled': BUSINESS_ENABLED, 'interval_ms': SAMPLE_INTERVAL_MS, 'ok': True}\n"
        "    msg = '[task] business tick {} ms'.format(SAMPLE_INTERVAL_MS)\n"
        "    _log('debug', msg)\n"
        "    if not BUSINESS_ENABLED:\n"
        "        result['ok'] = False\n"
        "        return result\n"
        "    if status_output is None:\n"
        "        _log('warning', '[task] status output missing')\n"
        "        result['missing_output'] = True\n"
        "        return result\n"
        "    try:\n"
        "        status_output.write(msg)\n"
        "    except Exception as exc:\n"
        "        _log('warning', '[task] status output failed: {}'.format(exc))\n"
        "        result['ok'] = False\n"
        "        result['error'] = str(exc)\n"
        "    result['message'] = msg\n"
        "    return result\n"
    )
    if mode == "async":
        mode_import = "import uasyncio as asyncio\n"
        main_loop = (
            "\n\n"
            "async def main():\n"
            "    msg = '[t={}ms] [main] async scheduler start interval={}ms'.format(time.ticks_ms(), SAMPLE_INTERVAL_MS)\n"
            "    print(msg)\n"
            "    logger.info(msg)\n"
            "    await business_tick(status_output)\n"
            "    await asyncio.sleep_ms(SAMPLE_INTERVAL_MS)\n\n"
            "asyncio.run(main())\n"
        )
        task_body = async_task_body
        pc_call = "asyncio.run(business_tick(output))"
        pc_missing_call = "asyncio.run(business_tick(None))"
        pc_fail_call = "asyncio.run(business_tick(output))"
        pc_import = "import asyncio\n"
        pre_loop_call = ""
    elif mode == "thread":
        mode_import = "import _thread\n"
        main_loop = (
            "\n\n"
            "def worker():\n"
            "    msg = '[t={}ms] [main] thread worker start interval={}ms'.format(time.ticks_ms(), SAMPLE_INTERVAL_MS)\n"
            "    print(msg)\n"
            "    logger.info(msg)\n\n"
            "_thread.start_new_thread(worker, ())\n"
            "while True:\n"
            "    time.sleep_ms(SAMPLE_INTERVAL_MS)\n"
        )
        task_body = sync_task_body
        pc_call = "business_tick(output)"
        pc_missing_call = "business_tick(None)"
        pc_fail_call = "business_tick(output)"
        pc_import = ""
        pre_loop_call = "business_tick(status_output)\n"
    else:
        mode_import = "from lib.scheduler.timer_sched import Scheduler\n"
        main_loop = (
            f"scheduler = Scheduler({scheduler_init_args(manifest)})\n"
            "scheduler.add_task(lambda: business_tick(status_output), SAMPLE_INTERVAL_MS, name='business_tick')\n"
            "msg = '[t={}ms] [main] timer scheduler ready interval={}ms'.format(time.ticks_ms(), SAMPLE_INTERVAL_MS)\n"
            "print(msg)\n"
            "logger.info(msg)\n"
        )
        task_body = sync_task_body
        pc_call = "business_tick(output)"
        pc_missing_call = "business_tick(None)"
        pc_fail_call = "business_tick(output)"
        pc_import = ""
        pre_loop_call = "business_tick(status_output)\n"
    main_py = (
        "import sys\n"
        "import time\n"
        f"{mode_import}"
        "from conf import LOG_DIR, LOG_LEVEL, LOG_FILES_MAX, LOG_LINES_PER_FILE, PROJECT_NAME, SAMPLE_INTERVAL_MS\n"
        "from drivers.status_driver import create_status_output\n"
        "from lib import logger\n"
        "from tasks.business_task import business_tick\n\n"
        "\n"
        "def _on_scheduler_error(tid, exc):\n"
        "    sys.print_exception(exc)\n"
        "    logger.exception(exc, '[t={}ms] [task] {} failed'.format(time.ticks_ms(), tid))\n\n"
        "\n"
        "def _main():\n"
        "    time.sleep(3)  # Boot delay: allow mpremote to reconnect after reset\n"
        "    if hasattr(logger, 'install_rotating'):\n"
        "        logger.install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)\n"
        "    if hasattr(logger, 'setLevel'):\n"
        "        logger.setLevel(logger.DEBUG if LOG_LEVEL == 'DEBUG' else logger.INFO)\n"
        "    _log = logger.getLogger('main') if hasattr(logger, 'getLogger') else None\n"
        "    _ = _log\n"
        "    status_output = create_status_output()\n"
        "    msg = '[t={}ms] [main] {} interval={}ms'.format(time.ticks_ms(), PROJECT_NAME, SAMPLE_INTERVAL_MS)\n"
        "    print(msg)\n"
        "    logger.info(msg)\n"
        f"{indent_block(pre_loop_call, 4) if pre_loop_call else ''}"
        f"{indent_block(main_loop, 4)}\n"
        "\n"
        "try:\n"
        "    _main()\n"
        "except Exception as exc:\n"
        "    sys.print_exception(exc)\n"
        "    logger.exception(exc, '[t={}ms] [fatal] main.py startup failed'.format(time.ticks_ms()))\n"
        "    raise\n"
    )
    conf_append = (
        "\n# Generated business configuration\n"
        "BUSINESS_ENABLED = True\n"
    )
    return {
        "generate_plan.json": json.dumps(
            generate_plan(manifest, mode),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "firmware/drivers/status_driver/__init__.py": (
            "class StatusOutput:\n"
            "    def __init__(self):\n"
            "        self.last = None\n\n"
            "    def write(self, message):\n"
            "        self.last = message\n"
            "        print(message)\n"
            "\n"
            "\n"
            "def create_status_output():\n"
            "    return StatusOutput()\n"
        ),
        "firmware/drivers/status_driver/mock.py": (
            "class MockStatusOutput:\n"
            "    def __init__(self, fail=False):\n"
            "        self.messages = []\n\n"
            "        self.fail = fail\n\n"
            "    def write(self, message):\n"
            "        if self.fail:\n"
            "            raise OSError('mock status output failure')\n"
            "        self.messages.append(message)\n"
        ),
        "firmware/tasks/business_task.py": task_body,
        "firmware/main.py": main_py,
        "test/pc/test_business_task.py": (
            f"{pc_import}"
            "import sys\n"
            "import unittest\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'firmware'))\n\n"
            "from drivers.status_driver.mock import MockStatusOutput  # noqa: E402\n"
            "from tasks.business_task import business_tick  # noqa: E402\n\n"
            "\n"
            "class TestBusinessTick(unittest.TestCase):\n"
            "    def test_normal_data(self):\n"
            "        output = MockStatusOutput()\n"
            f"        result = {pc_call}\n"
            "        self.assertTrue(result['message'])\n"
            "        self.assertTrue(output.messages)\n\n"
            "    def test_missing_device(self):\n"
            f"        result = {pc_missing_call}\n"
            "        self.assertTrue(result['missing_output'])\n\n"
            "    def test_driver_exception(self):\n"
            "        output = MockStatusOutput(fail=True)\n"
            f"        result = {pc_fail_call}\n"
            "        self.assertEqual(result['ok'], False)\n\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n"
        ),
        "device/tests/test_business_device.py": (
            "import sys\n"
            "import unittest\n\n"
            "sys.path.insert(0, 'firmware')\n"
            "sys.path.insert(0, '../firmware')\n"
            "sys.path.insert(0, '../../firmware')\n\n"
            "from conf import BUSINESS_ENABLED, SAMPLE_INTERVAL_MS  # noqa: E402\n"
            "from drivers.status_driver.mock import MockStatusOutput  # noqa: E402\n"
            "from tasks.business_task import business_tick  # noqa: E402\n\n"
            "\n"
            "class TestBusinessDevice(unittest.TestCase):\n"
            "    def test_output_adapter_contract(self):\n"
            "        output = MockStatusOutput()\n"
            "        output.write('device-ready')\n"
            "        self.assertIn('device-ready', output.messages[0])\n"
            "        self.assertIsNotNone(business_tick)\n\n"
            "    def test_config_contract(self):\n"
            "        self.assertTrue(BUSINESS_ENABLED)\n"
            "        self.assertGreaterEqual(SAMPLE_INTERVAL_MS, 1)\n"
            "\n"
            "\n"
            "unittest.main()\n"
        ),
        "docs/generate-notes.md": f"# Generate Notes\n\nProject: {project_name}\n",
        "_conf_append": conf_append,
    }


def generate_plan(manifest: dict[str, Any], mode: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "mode": "full",
        "scheduler_mode": mode,
        "requirements": manifest.get("requirements", {}),
        "drivers": [
            {
                "name": "status_driver",
                "path": "firmware/drivers/status_driver/__init__.py",
                "interface": "mock_status_output",
            }
        ],
        "tasks": [
            {
                "name": "business_task",
                "path": "firmware/tasks/business_task.py",
                "scheduler_mode": mode,
                "uses_config": ["BUSINESS_ENABLED", "SAMPLE_INTERVAL_MS"],
            }
        ],
        "config_constants": [
            {"name": "BUSINESS_ENABLED", "value": True, "source": "generate_plan"},
            {"name": "SAMPLE_INTERVAL_MS", "source": "scaffold_or_generate"},
        ],
        "main_assembly": {
            "imports": ["conf", "logger", "status_driver", "business_task"],
            "drivers": ["status_output"],
            "tasks": ["business_tick"],
        },
        "resource_plan": {
            "gpio": "generated status output only",
        },
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
        "cloud_integrations": [
            {
                "provider_id": "custom_http_proxy",
                "category": "data_api",
                "services": ["status_webhook"],
                "mode": "gateway_https",
                "credential_management": {"requires_credentials": False, "status": "not_required"},
            }
        ],
        "tests": [
            {"path": "test/pc/test_business_task.py", "scenarios": ["normal", "missing_device", "driver_exception"]},
            {"path": "device/tests/test_business_device.py", "scenarios": ["interface_contract", "config_contract"]},
        ],
        "data_flow_contract": [
            {
                "name": "status_message",
                "producer": "tasks.business_task.business_tick",
                "storage": "local_result.message",
                "consumer": "drivers.status_driver.write",
                "invariant": "status output receives the generated business message",
                "covered_by_tests": ["test/pc/test_business_task.py::TestBusinessTick::test_normal_data"],
            }
        ],
    }


def apply_generated_files(project_dir: Path, files: dict[str, str], force: bool) -> list[dict[str, Any]]:
    entries = []
    conf_append = files.pop("_conf_append", "")
    if conf_append:
        conf_path = project_dir / "firmware" / "conf.py"
        current = conf_path.read_text(encoding="utf-8-sig") if conf_path.exists() else ""
        if "BUSINESS_ENABLED" not in current:
            files["firmware/conf.py"] = current.rstrip() + "\n" + conf_append
    for rel, content in files.items():
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        before = sha256_file(target) if target.exists() else None
        desired = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if target.exists() and before == desired:
            status = "unchanged"
        elif target.exists() and not force and rel not in {"firmware/main.py", "firmware/conf.py"}:
            status = "skipped"
        else:
            status = "updated" if target.exists() else "created"
            with target.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        entries.append(
            {
                "path": rel,
                "status": status,
                "encoding": "utf-8",
                "bytes": len(content.encode("utf-8")),
                "sha256": desired if status != "skipped" else before,
                "sha256_before": before,
                "sha256_after": desired if status != "skipped" else before,
                "overwrite": status == "updated",
                "role": role_for_path(rel),
            }
        )
    return entries


def role_for_path(path: str) -> str:
    if path == "generate_plan.json":
        return "plan"
    if path == "firmware/main.py":
        return "entrypoint"
    if path == "firmware/conf.py":
        return "configuration"
    if path.endswith("/mock.py") and path.startswith("firmware/drivers/"):
        return "mock"
    if path.startswith("firmware/drivers/"):
        return "driver_adapter"
    if path.startswith("firmware/tasks/"):
        return "business_task"
    if path.startswith("test/pc/"):
        return "pc_test"
    if path.startswith("test/device/") or path.startswith("device/tests/"):
        return "device_test"
    return "artifact"


def run_checks(project_dir: Path, session_dir: Path | None = None, manifest_path: Path | None = None) -> dict[str, Any]:
    _ = manifest_path
    cmd = [sys.executable, str(SCRIPTS / "run_quality_gates.py"), "--project-dir", str(project_dir)]
    if session_dir is not None:
        cmd.extend(["--session-dir", str(session_dir)])
    result = run_cmd(cmd)
    try:
        payload = json.loads(result["stdout"]) if result["stdout"].strip() else {}
    except json.JSONDecodeError:
        payload = {"parse_error": result["stdout"]}
    if isinstance(payload, dict) and isinstance(payload.get("checks"), dict):
        return payload["checks"]
    return {"quality_gates": {**result, "payload": payload, "ok": result["returncode"] == 0}}


def check_ok(result: dict[str, Any]) -> bool:
    if result.get("ok") is not None:
        return bool(result.get("ok"))
    return result.get("returncode") in (0, None)


def add_mip_dependency(
    entries: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    raw: Any,
) -> None:
    if isinstance(raw, str):
        package = raw.strip()
        if not package:
            return
        entry = {
            "package": package,
            "reason": f"{package} runtime dependency",
            "required_for": [package],
            "target": "/lib",
            "version": "latest",
            "install_phase": "deploy",
            "verify_import": package.replace("-", "_"),
        }
    elif isinstance(raw, dict):
        package = str(raw.get("package") or "").strip()
        if not package:
            return
        entry = deepcopy(raw)
        entry["package"] = package
        entry["target"] = str(entry.get("target") or "/lib").strip() or "/lib"
        entry["version"] = str(entry.get("version") or "latest")
        entry["install_phase"] = str(entry.get("install_phase") or "deploy")
        entry["verify_import"] = str(entry.get("verify_import") or package.replace("-", "_")).strip()
    else:
        return
    key = (entry["package"], entry.get("verify_import") or "", entry["target"])
    if key in seen:
        return
    seen.add(key)
    entries.append(entry)


def add_builtin_required(values: list[str], seen: set[str], raw: Any) -> None:
    if not isinstance(raw, list):
        return
    for item in raw:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)


def runtime_dependency_for_micropython_lib(device: dict[str, Any], driver: dict[str, Any]) -> dict[str, Any] | None:
    package = str(driver.get("package_name") or "").strip()
    if not package:
        return None
    device_name = str(device.get("name") or "device")
    verify_import = str(driver.get("verify_import") or driver.get("module") or package.replace("-", "_")).strip()
    return {
        "package": package,
        "version": str(driver.get("version") or "latest"),
        "reason": f"{device_name} requires MicroPython-lib package {package}",
        "required_for": [device_name],
        "target": str(driver.get("target") or "/lib"),
        "install_phase": "deploy",
        "verify_import": verify_import,
        "source": "micropython_lib",
    }


def upypi_package_url(driver: dict[str, Any], package_name: str, version: str) -> str:
    url = str(driver.get("url") or "").strip()
    if url:
        url = url.rstrip("/")
        if url.endswith("/package.json"):
            url = url[: -len("/package.json")]
        return url
    return f"{UPYPI_BASE}/pkgs/{package_name}/{version}"


def runtime_dependency_for_upypi(device: dict[str, Any], driver: dict[str, Any]) -> dict[str, Any] | None:
    package_name = str(driver.get("package_name") or "").strip()
    if not package_name:
        return None
    version = str(driver.get("version") or "1.0.0").strip() or "1.0.0"
    package_url = upypi_package_url(driver, package_name, version)
    device_name = str(device.get("name") or "device")
    verify_import = str(driver.get("verify_import") or driver.get("module") or package_name.replace("-", "_")).strip()
    return {
        "package": package_url,
        "package_name": package_name,
        "version": version,
        "reason": f"{device_name} requires uPyPi package {package_name}",
        "required_for": [device_name],
        "target": str(driver.get("target") or "/lib"),
        "install_phase": "deploy",
        "verify_import": verify_import,
        "source": "upypi",
        "source_url": package_url,
        "package_json_url": str(driver.get("package_json_url") or f"{package_url}/package.json"),
        "asset_files": driver.get("asset_files") if isinstance(driver.get("asset_files"), list) else [],
    }


def merged_runtime_dependencies(manifest: dict[str, Any]) -> dict[str, Any]:
    mip_entries: list[dict[str, Any]] = []
    seen_mip: set[tuple[str, str, str]] = set()
    builtin_required: list[str] = []
    seen_builtin: set[str] = set()
    default_runtime = {
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
    }
    candidates: list[dict[str, Any]] = []
    for value in (default_runtime, manifest.get("runtime_dependencies")):
        if isinstance(value, dict):
            candidates.append(value)
    generate = manifest.get("generate")
    if isinstance(generate, dict) and isinstance(generate.get("runtime_dependencies"), dict):
        candidates.append(generate["runtime_dependencies"])
    for deps in candidates:
        for item in deps.get("mip") or []:
            add_mip_dependency(mip_entries, seen_mip, item)
        add_builtin_required(builtin_required, seen_builtin, deps.get("builtin_required"))
    devices = manifest.get("devices")
    if isinstance(devices, list):
        for device in devices:
            if not isinstance(device, dict):
                continue
            driver = device.get("driver")
            if not isinstance(driver, dict):
                continue
            source = str(driver.get("source") or "").strip().lower()
            dependency = None
            if source == "micropython_lib":
                dependency = runtime_dependency_for_micropython_lib(device, driver)
            elif source == "upypi":
                dependency = runtime_dependency_for_upypi(device, driver)
            if dependency:
                add_mip_dependency(mip_entries, seen_mip, dependency)
    return {"mip": mip_entries, "builtin_required": builtin_required}


def update_manifest(project_dir: Path, manifest: dict[str, Any], mode: str, checks: dict[str, Any], git_info: dict[str, Any]) -> dict[str, Any]:
    _ = git_info
    updated = deepcopy(manifest)
    runtime_dependencies = merged_runtime_dependencies(updated)
    updated["phase"] = "generate"
    updated["domain_phase"] = "generate"
    updated["final_status"] = "generated"
    updated["generate"] = {
        **updated.get("generate", {}),
        "mode": mode,
        "generated_at": utc_now(),
        "deploy_ready": True,
        "behavior_spec": {
            "source": "local_mock_runner",
            "description": updated.get("requirements", {}).get("description", ""),
        },
        "deploy_plan": {
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
        },
        "simulation_hints": {
            "scenarios": ["normal", "threshold_crossed", "sensor_failure", "network_failure"],
            "data_generators": [],
            "expected_outputs": ["serial"],
        },
        "runtime_dependencies": runtime_dependencies,
        "doc_evidence": [
            {
                "module": "machine",
                "url": "https://docs.micropython.org/en/latest/library/machine.html",
                "reason": "baseline hardware API reference for deploy target generation",
            },
            {
                "module": "machine.Pin",
                "url": "https://docs.micropython.org/en/latest/library/machine.Pin.html",
                "reason": "GPIO pin API evidence for generated firmware and scaffold compatibility",
            },
            {
                "module": "machine.Timer",
                "url": "https://docs.micropython.org/en/latest/library/machine.Timer.html",
                "reason": "timer scheduler evidence for the selected MicroPython port",
            }
        ],
        "cloud_integrations": [
            {
                "provider_id": "custom_http_proxy",
                "category": "data_api",
                "services": ["status_webhook"],
                "mode": "gateway_https",
                "official_links": {},
                "credential_management": {
                    "requires_credentials": False,
                    "status": "not_required",
                    "secret_names": [],
                    "storage": "none",
                    "forbidden_locations": ["firmware/conf.py", "git", "phase_complete"],
                },
                "user_action_required": [],
                "deploy_ready": True,
            }
        ],
        "resource_plan": {
            "gpio": "generated status output only",
        },
        "checks": {name: data.get("returncode") for name, data in checks.items()},
    }
    updated["runtime_dependencies"] = updated["generate"]["runtime_dependencies"]
    requirements = updated.get("requirements")
    if not isinstance(requirements, dict) or not requirements.get("description"):
        updated["requirements"] = {"description": updated.get("project_name", "mock project")}
    devices = updated.get("devices")
    if not isinstance(devices, list) or not devices:
        updated["devices"] = [{"name": "LED", "driver": {"source": "none"}}]
    if not isinstance(updated.get("mcu"), dict):
        updated["mcu"] = {"model": "mock"}
    pinout = updated.get("pinout")
    if not isinstance(pinout, list) or not pinout:
        updated["pinout"] = [{"device": "LED", "pin_name": "status", "gpio": "mock"}]
    updated.setdefault("scaffold_mode", mode)
    write_json(project_dir / "project-manifest.json", updated)
    return updated


def remove_python_caches(project_dir: Path) -> list[str]:
    removed: list[str] = []
    for cache_dir in sorted(project_dir.rglob("__pycache__"), reverse=True):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
            removed.append(cache_dir.relative_to(project_dir).as_posix())
    for pyc_file in sorted(project_dir.rglob("*.pyc")):
        if pyc_file.is_file():
            pyc_file.unlink()
            removed.append(pyc_file.relative_to(project_dir).as_posix())
    return removed


def maybe_git_commit(project_dir: Path, allow_commit: bool) -> dict[str, Any]:
    if not allow_commit:
        return {
            "commit": None,
            "message": "feat(generate): add business firmware code",
            "status": "permission_required_or_dry_run",
        }
    inside = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=project_dir)
    if inside["returncode"] != 0:
        run_cmd(["git", "init"], cwd=project_dir)
    removed_caches = remove_python_caches(project_dir)
    run_cmd(["git", "add", "."], cwd=project_dir)
    message = "feat(generate): add business firmware code"
    commit = run_cmd(
        [
            "git",
            "-c",
            "user.name=upy-generate-plugin",
            "-c",
            "user.email=upy-generate-plugin@example.invalid",
            "commit",
            "-m",
            message,
        ],
        cwd=project_dir,
    )
    rev = run_cmd(["git", "rev-parse", "HEAD"], cwd=project_dir)
    return {
        "commit": rev["stdout"].strip() if rev["returncode"] == 0 else None,
        "message": message,
        "status": "committed" if commit["returncode"] == 0 or "nothing to commit" in commit["stdout"].lower() else "failed",
        "committed": commit["returncode"] == 0 or "nothing to commit" in commit["stdout"].lower(),
        "cleaned_python_caches": removed_caches,
        "stdout": commit["stdout"],
        "stderr": commit["stderr"],
    }


def build_phase_complete(
    session_dir: Path,
    project_dir: Path,
    manifest: dict[str, Any],
    file_entries: list[dict[str, Any]],
    checks: dict[str, Any],
    git_info: dict[str, Any],
    next_phase: str | None,
) -> dict[str, Any]:
    artifact_root = session_dir.parent.parent if session_dir.parent.name == "sessions" else session_dir
    session_id = session_dir.name
    timestamp = utc_now()
    errors = []
    if any(entry["status"] == "skipped" for entry in file_entries):
        errors.append(
            {
                "code": "FILE_CONFLICT",
                "severity": "error",
                "phase_step": "file_write",
                "retryable": False,
                "message": "Generated file conflicts with existing content.",
            }
        )
    for name, result in checks.items():
        if not check_ok(result):
            errors.append(
                {
                    "code": f"{name.upper()}_FAILED",
                    "severity": "error",
                    "phase_step": name,
                    "retryable": True,
                    "message": f"{name} failed quality policy",
                }
            )
    if git_info.get("status") != "committed" or not git_info.get("commit"):
        errors.append(
            {
                "code": "GIT_COMMIT_REQUIRED",
                "severity": "error",
                "phase_step": "git_commit",
                "retryable": True,
                "message": "Quality-clean generated code must be committed before success.",
            }
        )
    result_status = "success" if not errors else "partial"
    if result_status != "success":
        next_phase = None
    session_state_path = session_dir / "session_state.upy_generate_plugin.json"
    session_state_entry = {
        "path": "session_state.upy_generate_plugin.json",
        "status": "updated" if session_state_path.exists() else "error",
        "encoding": "utf-8",
        "bytes": session_state_path.stat().st_size if session_state_path.exists() else 0,
        "sha256": sha256_file(session_state_path) if session_state_path.exists() else None,
        "role": "artifact",
    }
    file_manifest = {
        "root": relative_to_artifact(project_dir, artifact_root),
        "path": relative_to_artifact(session_dir / "generate_file_manifest.json", artifact_root),
        "generated_at": timestamp,
        "files": file_entries + [
            {
                "path": "project-manifest.json",
                "status": "updated",
                "encoding": "utf-8",
                "bytes": (project_dir / "project-manifest.json").stat().st_size,
                "sha256": sha256_file(project_dir / "project-manifest.json"),
                "role": "manifest",
            },
            session_state_entry,
        ],
    }
    return {
        "protocol_version": "1.0",
        "msg_id": f"local-generate-{session_id}",
        "session_id": session_id,
        "phase": "upy-generate-plugin",
        "timestamp": timestamp,
        "type": "phase_complete",
        "idempotency_key": f"upy-generate-plugin:{session_id}:phase-complete:v1",
        "retry_of": None,
        "payload": {
            "phase": "generate",
            "domain_phase": "generate",
            "result": result_status,
            "summary": "Local mock generate completed" if result_status == "success" else "Local mock generate completed with issues",
            "next_phase": next_phase,
            "optional_next_phases": [
                {
                    "phase": "upy-diagram-plugin",
                    "reason": "optional architecture and data-flow diagrams after generate",
                },
                {
                    "phase": "upy-wiring-plugin",
                    "reason": "optional wiring artifacts after generate",
                },
            ],
            "checkpoint": "phase_completed" if result_status == "success" else "checks_failed",
            "runtime_context": {
                "artifact_root": ".",
                "artifact_root_mode": "session_parent",
                "session_root": relative_to_artifact(session_dir, artifact_root),
                "project_root": relative_to_artifact(project_dir, artifact_root),
                "file_operation_root": relative_to_artifact(project_dir, artifact_root),
                "resource_root": ROOT.name,
            },
            "file_manifest": file_manifest,
            "lint": {
                "flake8": checks.get("flake8", {}),
                "pylint": checks.get("pylint", {}),
            },
            "tests": {
                "pc_unittest": checks.get("pc_unittest", {}),
            },
            "checks": checks,
            "permissions": [
                {
                    "type": "file_operation",
                    "operation": "write",
                    "root": relative_to_artifact(project_dir, artifact_root),
                    "approved": True,
                    "idempotency_key": f"upy-generate-plugin:{session_id}:file-write:v1",
                },
                {
                    "type": "git_commit",
                    "approved": git_info.get("status") == "committed",
                    "idempotency_key": f"upy-generate-plugin:{session_id}:git-commit:v1",
                },
            ],
            "generate": {**manifest.get("generate", {}), "git": git_info},
            "manifest_content": manifest,
            "review_findings": {
                "blocking": [],
                "warnings": [],
            },
            "artifacts": [
                {"type": "file_manifest", "path": relative_to_artifact(session_dir / "generate_file_manifest.json", artifact_root)},
                {"type": "session_state", "path": relative_to_artifact(session_state_path, artifact_root)},
                {"type": "file_list", "title": "Generate 写入结果", "files": file_manifest["files"]},
            ],
            "structured_errors": errors,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local mock upy-generate-plugin session")
    parser.add_argument("--session-dir", default="", help="Session directory; project defaults to <session-dir>/project")
    parser.add_argument("--manifest", default=str(FLASH_SAMPLE if FLASH_SAMPLE.exists() else SELECT_SAMPLE))
    parser.add_argument("--mode", default="timer", choices=["timer", "async", "thread"])
    parser.add_argument("--next-phase", default="deploy", choices=["deploy", "simulate", "stop"])
    parser.add_argument("--force", action="store_true", help="Overwrite generated files")
    parser.add_argument("--allow-git-commit", action="store_true", help="Actually run git commit in project dir")
    parser.add_argument("--write-phase-complete", action="store_true")
    parser.add_argument("--keep", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    temp_root: Path | None = None
    if args.session_dir:
        session_dir = Path(args.session_dir).resolve()
    else:
        temp_root = Path(tempfile.mkdtemp(prefix="upy_generate_mock_"))
        session_dir = temp_root / "sessions" / "sample-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    project_dir = session_dir / "project"
    scaffold_phase = ensure_scaffold_project(session_dir, Path(args.manifest), args.mode)
    manifest = extract_manifest(scaffold_phase)
    mode = manifest.get("scaffold_mode") or manifest.get("scaffold", {}).get("mode") or args.mode
    usage = {"token_budget_status": "ok", "remaining_budget": None}
    run_session_state(
        session_dir,
        "started",
        "start_phase",
        "running",
        attempt=1,
        manifest_hash=project_manifest_hash(project_dir),
        usage=usage,
    )
    files = generated_files(manifest, mode)
    entries = apply_generated_files(project_dir, files, args.force)
    run_session_state(
        session_dir,
        "tests_generated",
        "write_generated_files",
        "running",
        artifacts=[{"type": "file_list", "count": len(entries)}],
        attempt=1,
        manifest_hash=project_manifest_hash(project_dir),
        usage=usage,
    )
    update_manifest(project_dir, manifest, mode, {}, {})
    run_session_state(
        session_dir,
        "generate_plan_validated",
        "update_manifest",
        "running",
        artifacts=[{"type": "project_manifest", "path": "project/project-manifest.json"}],
        attempt=1,
        manifest_hash=project_manifest_hash(project_dir),
        usage=usage,
    )
    checks = run_checks(project_dir, session_dir=session_dir)
    updated_manifest = update_manifest(project_dir, manifest, mode, checks, {})
    git_info = maybe_git_commit(project_dir, args.allow_git_commit and all(check_ok(data) for data in checks.values()))
    next_phase = {"deploy": "upy-deploy-plugin", "simulate": "upy-simulate-plugin", "stop": None}[args.next_phase]
    final_checkpoint = "phase_completed" if git_info.get("status") == "committed" and all(check_ok(data) for data in checks.values()) else "checks_failed"
    final_status = "completed" if final_checkpoint == "phase_completed" else "partial"
    run_session_state(
        session_dir,
        final_checkpoint,
        "phase_complete",
        final_status,
        artifacts=[
            {"type": "project_manifest", "path": "project/project-manifest.json"},
            {"type": "generate_plan", "path": "project/generate_plan.json"},
            {"type": "phase_complete", "path": "phase_complete.upy_generate_plugin.json"},
            {"type": "file_manifest", "path": "generate_file_manifest.json"},
        ],
        attempt=1,
        manifest_hash=project_manifest_hash(project_dir),
        git_commit=str(git_info.get("commit") or ""),
        usage=usage,
    )
    session_state_check = run_cmd(
        [
            sys.executable,
            str(SCRIPTS / "update_session_state.py"),
            "--session-dir",
            str(session_dir),
            "--project-dir",
            str(project_dir),
            "--check",
        ]
    )
    try:
        session_state_payload = json.loads(session_state_check["stdout"]) if session_state_check["stdout"].strip() else {}
    except json.JSONDecodeError:
        session_state_payload = {"parse_error": session_state_check["stdout"]}
    checks["session_state_checkpoint"] = (
        session_state_payload
        if isinstance(session_state_payload, dict)
        else {"returncode": session_state_check["returncode"], "ok": session_state_check["returncode"] == 0}
    )
    phase_complete = build_phase_complete(session_dir, project_dir, updated_manifest, entries, checks, git_info, next_phase)
    if args.write_phase_complete:
        write_json(session_dir / "generate_file_manifest.json", phase_complete["payload"]["file_manifest"])
        write_json(session_dir / "phase_complete.upy_generate_plugin.json", phase_complete)
    summary = {
        "status": phase_complete["payload"]["result"],
        "session_dir": str(session_dir),
        "project_dir": str(project_dir),
        "next_phase": phase_complete["payload"]["next_phase"],
        "phase_complete": phase_complete,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if temp_root and not args.keep:
        shutil.rmtree(temp_root, ignore_errors=True)
    return 0 if summary["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
