#!/usr/bin/env python3
"""Smoke tests for upy-scaffold plugin-mode rendering."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SCRIPT = ROOT / "scripts" / "init_scaffold.py"
RUNNER = ROOT / "scripts" / "apply_scaffold.py"
VALIDATOR = ROOT / "scripts" / "scaffold_manifest.py"
SELECT_HW_SAMPLE = REPO / "upy-select-hw-plugin" / "sample" / "phase_complete.select_hw.success.json"
FLASH_SAMPLE = REPO / "upy-flash-mpy-firmware-plugin" / "sample" / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_c3_success.json"


def load_select_hw_manifest() -> dict:
    with SELECT_HW_SAMPLE.open("r", encoding="utf-8-sig") as handle:
        phase_complete = json.load(handle)
    return phase_complete["payload"]["manifest_content"]


def run_script(*args: str, stdin_obj: dict | None = None) -> dict:
    cmd = [sys.executable, str(SCRIPT), *args]
    stdin_text = json.dumps(stdin_obj, ensure_ascii=False) if stdin_obj is not None else None
    result = subprocess.run(
        cmd,
        input=stdin_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(cmd)}\nSTDERR:\n{result.stderr}")
    return json.loads(result.stdout)


def run_runner(*args: str) -> tuple[int, dict]:
    cmd = [sys.executable, str(RUNNER), *args]
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if not result.stdout.strip():
        raise AssertionError(f"runner produced no JSON: {' '.join(cmd)}\nSTDERR:\n{result.stderr}")
    return result.returncode, json.loads(result.stdout)


def run_json_allow_failure(cmd: list[str]) -> tuple[int, dict]:
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if not result.stdout.strip():
        raise AssertionError(f"command produced no JSON: {' '.join(cmd)}\nSTDERR:\n{result.stderr}")
    return result.returncode, json.loads(result.stdout)


def paths(output: dict) -> list[str]:
    return [item["path"] for item in output["files"]]


def content(output: dict, path: str) -> str:
    for item in output["files"]:
        if item["path"] == path:
            return item["content"]
    raise AssertionError(f"missing file: {path}")


def assert_generated_python_compiles(output: dict) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        py_paths: list[Path] = []
        for item in output["files"]:
            rel_path = item["path"]
            if not rel_path.endswith(".py"):
                continue
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item["content"], encoding="utf-8")
            py_paths.append(target)

        result = subprocess.run(
            [sys.executable, "-m", "py_compile", *[str(path) for path in py_paths]],
            text=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"generated Python failed syntax compile:\n{result.stderr}")


def assert_common_output(output: dict) -> None:
    if output["phase"] != "scaffold":
        raise AssertionError("phase must be scaffold")
    if not isinstance(output.get("files"), list) or not output["files"]:
        raise AssertionError("files must be a non-empty list")
    for item in output["files"]:
        if item.get("encoding") != "utf-8":
            raise AssertionError(f"encoding must be utf-8: {item}")
        if item.get("content", "").startswith("\ufeff"):
            raise AssertionError(f"generated file content must not include UTF-8 BOM: {item.get('path')}")
        path = item.get("path", "")
        if not path or path.startswith("/") or "\\" in path or ".." in path.split("/"):
            raise AssertionError(f"path must be safe relative POSIX path: {path}")
    if "file_tree" not in output:
        raise AssertionError("file_tree missing")
    if len(output.get("file_operations", [])) != len(output["files"]):
        raise AssertionError("file_operations must mirror files")
    for index, operation in enumerate(output["file_operations"], start=1):
        if operation.get("type") != "file_operation":
            raise AssertionError(f"file operation type invalid: {operation}")
        payload = operation.get("payload", {})
        if payload.get("op") != "write":
            raise AssertionError(f"file operation op must be write: {payload}")
        if payload.get("content", "").startswith("\ufeff"):
            raise AssertionError(f"file operation content must not include UTF-8 BOM: {payload.get('path')}")
        if payload.get("op_id") != f"scaffold_fo_{index:03d}":
            raise AssertionError(f"file operation op_id must be stable: {payload}")
    artifact_types = {artifact.get("type") for artifact in output.get("artifacts", [])}
    if {"file_tree", "file_list"} - artifact_types:
        raise AssertionError("artifacts must include file_tree and file_list")
    phase_payload = output.get("phase_complete_payload", {})
    if phase_payload.get("phase") != "scaffold" or phase_payload.get("result") != "success":
        raise AssertionError("phase_complete_payload must describe scaffold success")
    if phase_payload.get("domain_phase") != "scaffold":
        raise AssertionError("phase_complete_payload must include domain_phase=scaffold")
    if not output.get("status_updates"):
        raise AssertionError("status_updates missing")


def full_timer_generates_json_payload() -> None:
    manifest = load_select_hw_manifest()
    output = run_script("--mode", "timer", "--manifest", "-", stdin_obj=manifest)
    assert_common_output(output)
    assert_generated_python_compiles(output)
    file_paths = paths(output)
    required = {
        "firmware/board.py",
        "firmware/conf.py",
        "firmware/boot.py",
        "firmware/main.py",
        "firmware/lib/scheduler/timer_sched.py",
        "firmware/tasks/maintenance.py",
        "tools/flash_device.py",
        "tools/read_device_log.py",
        ".gitignore",
        ".upy/schemas/project-manifest.schema.json",
        ".upy/schemas/wiring.schema.json",
        ".upy/schemas/diagram.schema.json",
        ".upy/schemas/diagnostic_bundle.schema.json",
        ".upy/scripts/init_scaffold.py",
        ".upy/scripts/validate_json.py",
        ".upy/scripts/download_drivers.py",
        ".upy/scripts/render_wiring_local.py",
        ".upy/scripts/render_diagram_local.py",
        ".upy/scripts/extract_pdf.py",
        ".upy/scripts/convert_arduino.py",
        ".upy/scripts/flash_device.py",
        ".upy/scripts/read_device_log.py",
        ".upy/scripts/run_on_device.py",
        ".upy/scripts/hardware_sanity.py",
        ".upy/scripts/triage.py",
        ".upy/error_lib.json",
        "project-manifest.json",
        "docs/.gitkeep",
        "README.md",
        "LICENSE",
        ".flake8",
    }
    missing = required - set(file_paths)
    if missing:
        raise AssertionError(f"timer output missing files: {sorted(missing)}")
    main_py = content(output, "firmware/main.py")
    if "from lib.scheduler.timer_sched import Scheduler" not in main_py:
        raise AssertionError("timer main.py must import Scheduler")
    if "i2c0 = I2C(0, scl=Pin(6), sda=Pin(5)" not in main_py:
        raise AssertionError("timer main.py must use manifest I2C pins on bus 0")
    boot_py = content(output, "firmware/boot.py")
    if "from machine import WDT" not in boot_py or "wdt = WDT(timeout=8000)" not in boot_py:
        raise AssertionError("boot.py must include WDT enablement placeholder")
    if output["manifest_content"]["phase"] != "scaffold":
        raise AssertionError("manifest_content.phase must be scaffold")
    if output["manifest_content"].get("final_status") != "scaffolded":
        raise AssertionError("manifest_content.final_status must be scaffolded")
    manifest_file = json.loads(content(output, "project-manifest.json"))
    if manifest_file != output["manifest_content"]:
        raise AssertionError("project-manifest.json must mirror manifest_content")
    flake8_config = content(output, ".flake8")
    if flake8_config.startswith("\ufeff"):
        raise AssertionError(".flake8 must not include UTF-8 BOM")
    for expected_text in ("builtins =", "const"):
        if expected_text not in flake8_config:
            raise AssertionError(f".flake8 missing MicroPython-aware config: {expected_text}")
    if "firmware/board.py: E122,E128" in flake8_config:
        raise AssertionError(".flake8 must not ignore board.py indentation errors")
    if "F821" in flake8_config or "extend-ignore =\n    F401" in flake8_config:
        raise AssertionError(".flake8 must not globally ignore F821/F401")
    gitignore = content(output, ".gitignore")
    for expected_text in ("__pycache__/", "*.pyc", "build/mpy/"):
        if expected_text not in gitignore:
            raise AssertionError(f".gitignore must ignore generated local artifacts: {expected_text}")
    board_py = content(output, "firmware/board.py")
    if "\n {'device':" in board_py or "\n  {'device':" in board_py:
        raise AssertionError("board.py PINOUT should be rendered with stable visual indentation")
    if output["phase_complete_payload"]["next_phase"] != "upy-generate-plugin":
        raise AssertionError("full scaffold should advance to upy-generate-plugin")
    warning_text = json.dumps(output.get("warnings", []), ensure_ascii=False)
    if "run_on_device.py" in warning_text:
        raise AssertionError("run_on_device.py should be copied, not reported missing")


def full_accepts_phase_complete_envelope() -> None:
    with SELECT_HW_SAMPLE.open("r", encoding="utf-8-sig") as handle:
        envelope = json.load(handle)
    output = run_script("--mode", "timer", "--manifest", str(SELECT_HW_SAMPLE))
    assert_common_output(output)
    if output["manifest_content"]["project_name"] != envelope["payload"]["manifest_content"]["project_name"]:
        raise AssertionError("phase_complete envelope should unwrap payload.manifest_content")
    if output["manifest_content"]["phase"] != "scaffold":
        raise AssertionError("unwrapped manifest should be advanced to scaffold phase")


def full_accepts_flash_phase_complete_and_uses_firmware_version() -> None:
    if not FLASH_SAMPLE.exists():
        return
    output = run_script("--mode", "timer", "--manifest", str(FLASH_SAMPLE))
    assert_common_output(output)
    if output["manifest_content"].get("firmware_flash", {}).get("latest_version") != "v1.28.0":
        raise AssertionError("flash firmware facts must be preserved into scaffold manifest")
    board_py = content(output, "firmware/board.py")
    main_py = content(output, "firmware/main.py")
    scheduler_py = content(output, "firmware/lib/scheduler/timer_sched.py")
    for generated in (board_py, main_py, scheduler_py):
        if "MicroPython v1.23.0" in generated:
            raise AssertionError("generated files must not hard-code MicroPython v1.23.0")
        if "MicroPython v1.28.0" not in generated:
            raise AssertionError("generated files must use firmware latest_version label")


def timer_scaffold_is_esp32_safe_and_logs_fatal_startup() -> None:
    manifest = {
        "phase": "select_hw",
        "project_name": "Timer Guard Test",
        "requirements": {"sample_rate": "normal_1hz"},
        "mcu": {"model": "ESP32-C3", "display_name": "ESP32-C3-DevKitM-1"},
        "devices": [{"name": "WS2812", "type": "led_rgb", "interface": "GPIO"}],
        "pinout": [
            {"device": "WS2812", "pin_name": "DATA", "gpio": 21, "type": "gpio_out", "interface": "GPIO"},
            {"device": "Button", "pin_name": "IN", "gpio": 4, "type": "gpio_in", "interface": "GPIO"},
        ],
    }
    output = run_script("--mode", "timer", "--manifest", "-", stdin_obj=manifest)
    assert_common_output(output)
    assert_generated_python_compiles(output)
    main_py = content(output, "firmware/main.py")
    scheduler_py = content(output, "firmware/lib/scheduler/timer_sched.py")
    if "def __init__(self, timer_id=-1" not in scheduler_py:
        raise AssertionError("scheduler library must preserve its default timer_id=-1 contract for ports that support virtual timers")
    if "Scheduler(timer_id=0, tick_ms=100" not in main_py:
        raise AssertionError(f"Hardware-timer ports must pass an explicit non-negative Timer id:\n{main_py}")
    forbidden_main = ("Timer(-1)", "Timer(id=-1)", "Scheduler(timer_id=-1)", "Scheduler(tick_ms=100")
    found = [item for item in forbidden_main if item in main_py]
    if found:
        raise AssertionError(f"Hardware-timer ports must not rely on invalid or implicit Timer(-1) patterns: {found}")
    combined = main_py + "\n" + scheduler_py
    required = [
        "import sys",
        "def _log_exception(exc, message):",
        "sys.print_exception(exc)",
        "exception(exc, stamped)",
        "try:\n    _main()\nexcept Exception as exc:",
        "Scheduler(timer_id=0, tick_ms=100",
        "from machine import Timer",
        "self._timer = Timer(timer_id)",
    ]
    missing = [item for item in required if item not in combined]
    if missing:
        raise AssertionError(f"timer scaffold missing fatal/logging/scheduler safety: {missing}")
    if "ws2812_data_pin = Pin(21, Pin.OUT)" not in main_py:
        raise AssertionError(f"gpio_out DATA must render as Pin.OUT:\n{main_py}")
    if "button_in_pin = Pin(4, Pin.IN)" not in main_py:
        raise AssertionError(f"gpio_in must render as Pin.IN:\n{main_py}")


def timer_scaffold_keeps_rp2_virtual_timer_default() -> None:
    manifest = {
        "phase": "select_hw",
        "project_name": "Pico Timer Test",
        "requirements": {"sample_rate": "normal_1hz"},
        "mcu": {"model": "Raspberry Pi Pico W", "display_name": "Pico W"},
        "devices": [{"name": "LED", "type": "led", "interface": "GPIO"}],
        "pinout": [
            {"device": "LED", "pin_name": "DATA", "gpio": 25, "type": "gpio_out", "interface": "GPIO"},
        ],
    }
    output = run_script("--mode", "timer", "--manifest", "-", stdin_obj=manifest)
    assert_common_output(output)
    assert_generated_python_compiles(output)
    main_py = content(output, "firmware/main.py")
    scheduler_py = content(output, "firmware/lib/scheduler/timer_sched.py")
    if "def __init__(self, timer_id=-1" not in scheduler_py:
        raise AssertionError("scheduler library must keep timer_id=-1 as the default")
    if "Scheduler(timer_id=-1, tick_ms=100" not in main_py:
        raise AssertionError(f"RP2/Pico timer main.py should explicitly keep virtual Timer(-1):\n{main_py}")


def timer_scaffold_keeps_zephyr_virtual_timer_default() -> None:
    manifest = {
        "phase": "select_hw",
        "project_name": "Zephyr Timer Test",
        "requirements": {"sample_rate": "normal_1hz"},
        "mcu": {"model": "Zephyr", "display_name": "Zephyr board"},
        "devices": [],
        "pinout": [],
    }
    output = run_script("--mode", "timer", "--manifest", "-", stdin_obj=manifest)
    assert_common_output(output)
    assert_generated_python_compiles(output)
    main_py = content(output, "firmware/main.py")
    if "Scheduler(timer_id=-1, tick_ms=100" not in main_py:
        raise AssertionError(f"Zephyr timer main.py should explicitly keep virtual Timer(-1):\n{main_py}")


def timer_scaffold_uses_hardware_timer_for_general_ports() -> None:
    manifest = {
        "phase": "select_hw",
        "project_name": "STM32 Timer Test",
        "requirements": {"sample_rate": "normal_1hz"},
        "mcu": {"model": "STM32", "display_name": "Pyboard STM32"},
        "devices": [],
        "pinout": [],
    }
    output = run_script("--mode", "timer", "--manifest", "-", stdin_obj=manifest)
    assert_common_output(output)
    assert_generated_python_compiles(output)
    main_py = content(output, "firmware/main.py")
    if "Scheduler(timer_id=0, tick_ms=100" not in main_py:
        raise AssertionError(f"General hardware-timer ports should default to Timer id 0:\n{main_py}")
    if "Scheduler(timer_id=-1" in main_py:
        raise AssertionError(f"Only RP2/Pico and Zephyr should use virtual Timer(-1):\n{main_py}")


def async_omits_scheduler_when_not_timer() -> None:
    manifest = load_select_hw_manifest()
    output = run_script(
        "--mode",
        "async",
        "--modules",
        "logger,flash_device",
        "--manifest",
        "-",
        stdin_obj=manifest,
    )
    assert_common_output(output)
    assert_generated_python_compiles(output)
    file_paths = paths(output)
    if "firmware/lib/scheduler/timer_sched.py" in file_paths:
        raise AssertionError("async mode must not inject timer scheduler")
    if "firmware/tasks/maintenance.py" in file_paths:
        raise AssertionError("unselected maintenance module must not be injected")
    main_py = content(output, "firmware/main.py")
    if "import uasyncio as asyncio" not in main_py:
        raise AssertionError("async main.py must use uasyncio")
    if "from lib.scheduler" in main_py:
        raise AssertionError("async main.py must not import scheduler")


def thread_mode_uses_thread_frame_and_custom_files() -> None:
    manifest = load_select_hw_manifest()
    output = run_script(
        "--mode",
        "thread",
        "--modules",
        "logger,maintenance,log_tools",
        "--custom-files",
        "firmware/lib/my_utils.py,host/gui.py",
        "--manifest",
        "-",
        stdin_obj=manifest,
    )
    assert_common_output(output)
    assert_generated_python_compiles(output)
    file_paths = paths(output)
    if "firmware/lib/scheduler/timer_sched.py" in file_paths:
        raise AssertionError("thread mode must not inject timer scheduler")
    if "tools/read_device_log.py" not in file_paths or "tools/log_report.py" not in file_paths:
        raise AssertionError("module_log_tools selection should emit both log tools")
    for custom_path in ("firmware/lib/my_utils.py", "host/gui.py"):
        if custom_path not in file_paths:
            raise AssertionError(f"custom file missing: {custom_path}")
        if "TODO: custom file requested" not in content(output, custom_path):
            raise AssertionError(f"custom file should contain a placeholder: {custom_path}")
    main_py = content(output, "firmware/main.py")
    if "import _thread" not in main_py:
        raise AssertionError("thread main.py must import _thread")
    if "time.sleep_ms(100)" not in main_py:
        raise AssertionError("thread main.py must keep a maintenance loop")
    if output["manifest_content"].get("scaffold_custom_files") != ["firmware/lib/my_utils.py", "host/gui.py"]:
        raise AssertionError("manifest_content must record custom files")


def incremental_generates_only_new_driver_stub() -> None:
    devices = [
        {
            "name": "DHT22",
            "driver": {
                "source": "upypi",
                "install_cmd": "mpremote mip install dht",
            },
        }
    ]
    with tempfile.TemporaryDirectory() as temp_dir:
        devices_path = Path(temp_dir) / "new_devices.json"
        devices_path.write_text(json.dumps(devices, ensure_ascii=False), encoding="utf-8-sig")
        output = run_script("--mode", "incremental", "--new-devices", str(devices_path))
    assert_common_output(output)
    expected_paths = ["firmware/drivers/dht22_driver/__init__.py", "project-manifest.json"]
    if paths(output) != expected_paths:
        raise AssertionError(f"incremental must generate one driver stub plus manifest: {paths(output)}")
    stub = content(output, "firmware/drivers/dht22_driver/__init__.py")
    if "DHT22 driver stub" not in stub or "mpremote mip install dht" not in stub:
        raise AssertionError("incremental stub content missing driver facts")
    manifest_file = json.loads(content(output, "project-manifest.json"))
    if manifest_file.get("generate_scope") != "new_devices_only":
        raise AssertionError("incremental manifest must record generate_scope=new_devices_only")
    if manifest_file.get("final_status") != "scaffolded":
        raise AssertionError("incremental manifest must record final_status=scaffolded")
    phase_payload = output["phase_complete_payload"]
    if phase_payload["next_phase"] != "upy-generate-plugin":
        raise AssertionError("incremental scaffold should advance to upy-generate-plugin")
    if phase_payload.get("generate_scope") != "new_devices_only" or not phase_payload.get("incremental"):
        raise AssertionError("incremental phase payload must carry generate scope")


def incremental_forces_stub_even_when_driver_source_is_none() -> None:
    output = run_script(
        "--mode",
        "incremental",
        "--new-devices",
        '[{"name":"Manual Sensor","driver":{"source":"none"}}]',
    )
    assert_common_output(output)
    expected = ["firmware/drivers/manual_sensor_driver/__init__.py", "project-manifest.json"]
    if paths(output) != expected:
        raise AssertionError(f"incremental must force a new-device stub plus manifest: {paths(output)}")
    if "firmware/drivers/.gitkeep" in paths(output):
        raise AssertionError("incremental mode must not emit placeholder files")


def approval_sample_uses_item_groups() -> None:
    sample = ROOT / "sample" / "approval_request.scaffold_config.json"
    with sample.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    payload = data["payload"]
    groups = payload.get("item_groups", {})
    if groups.get("scheduler_mode", {}).get("multi_select") is not False:
        raise AssertionError("scheduler_mode must be single-select")
    if groups.get("extra_modules", {}).get("multi_select") is not True:
        raise AssertionError("extra_modules must be multi-select")
    if not any(item.get("group") == "scheduler_mode" for item in payload.get("items", [])):
        raise AssertionError("approval sample missing scheduler_mode items")
    if not any(item.get("id") == "module_time_helper" and item.get("group") == "extra_modules" for item in payload.get("items", [])):
        raise AssertionError("approval sample missing module_time_helper time measurement option")


def run_on_device_reports_missing_file_as_json() -> None:
    script = ROOT / "scripts" / "run_on_device.py"
    result = subprocess.run(
        [sys.executable, str(script), "--file", str(REPO / "missing_run_on_device_input.py"), "--json-summary"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 2:
        raise AssertionError(f"missing-file path should return 2, got {result.returncode}")
    payload = json.loads(result.stdout)
    if payload.get("status") != "error" or not payload.get("errors"):
        raise AssertionError(f"missing-file JSON summary invalid: {payload}")


def local_actual_runner_writes_session_project_and_file_manifest() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "sample-session"
        session_dir.mkdir(parents=True)
        returncode, summary = run_runner("--session-dir", str(session_dir), "--manifest", str(FLASH_SAMPLE if FLASH_SAMPLE.exists() else SELECT_HW_SAMPLE))
        if returncode != 0:
            raise AssertionError(f"runner should succeed, got {returncode}: {summary}")
        project_dir = session_dir / "project"
        if Path(summary["project_dir"]) != project_dir.resolve():
            raise AssertionError("runner must default project_dir to <session-dir>/project")
        if not (project_dir / "firmware" / "main.py").exists():
            raise AssertionError("runner did not write project files under session/project")
        for rel_path in [
            ".flake8",
            "firmware/board.py",
            "firmware/conf.py",
            "firmware/boot.py",
            "firmware/main.py",
        ]:
            data = (project_dir / rel_path).read_bytes()
            if data.startswith(b"\xef\xbb\xbf"):
                raise AssertionError(f"runner must write UTF-8 without BOM: {rel_path}")
        phase_complete = summary["phase_complete"]
        phase_path = session_dir / "phase_complete.inline.json"
        phase_path.write_text(json.dumps(phase_complete, ensure_ascii=False), encoding="utf-8")
        validator_rc, validator = run_json_allow_failure([
            sys.executable,
            str(VALIDATOR),
            "--input",
            str(phase_path),
            "--validate-phase-complete",
        ])
        if validator_rc != 0 or validator.get("status") != "ok":
            raise AssertionError(f"scaffold phase_complete validator rejected valid output: {validator}")
        payload = phase_complete["payload"]
        expected_project_root = "sessions/sample-session/project"
        runtime_context = payload["runtime_context"]
        if runtime_context.get("artifact_root") != ".":
            raise AssertionError(f"runtime_context.artifact_root must be protocol-relative: {runtime_context}")
        if ":" in runtime_context.get("artifact_root", ""):
            raise AssertionError(f"runtime_context.artifact_root must not be a local absolute path: {runtime_context}")
        if payload["runtime_context"]["project_root"] != expected_project_root:
            raise AssertionError("phase_complete must record artifact-relative runtime_context.project_root")
        if payload["runtime_context"].get("resource_root") != "upy-scaffold-plugin":
            raise AssertionError("runtime_context.resource_root must use stable skill id")
        if payload["lint"]["cwd"] != expected_project_root or payload["lint"]["returncode"] != 0:
            raise AssertionError("flake8 must record artifact-relative project_root cwd and return 0")
        scaffold = payload.get("scaffold", {})
        manifest_scaffold = payload.get("manifest_content", {}).get("scaffold", {})
        if scaffold.get("mode") != manifest_scaffold.get("mode"):
            raise AssertionError(f"payload.scaffold must mirror final scaffold mode: {scaffold}")
        if scaffold.get("modules") != manifest_scaffold.get("modules"):
            raise AssertionError(f"payload.scaffold must mirror final scaffold modules: {scaffold}")
        if scaffold.get("custom_files") != manifest_scaffold.get("custom_files"):
            raise AssertionError(f"payload.scaffold must mirror final scaffold custom_files: {scaffold}")
        if scaffold.get("result") != payload.get("result") or scaffold.get("next_phase") != payload.get("next_phase"):
            raise AssertionError(f"payload.scaffold must summarize phase result and next_phase: {scaffold}")
        if scaffold.get("session_root") != "sessions/sample-session":
            raise AssertionError(f"payload.scaffold must record artifact-relative session_root: {scaffold}")
        if scaffold.get("project_root") != expected_project_root:
            raise AssertionError(f"payload.scaffold must record artifact-relative project_root: {scaffold}")
        if scaffold.get("file_operation_root") != expected_project_root:
            raise AssertionError(f"payload.scaffold must record file_operation_root: {scaffold}")
        if scaffold.get("file_manifest_path") != "sessions/sample-session/scaffold_file_manifest.json":
            raise AssertionError(f"payload.scaffold must record file_manifest_path: {scaffold}")
        if scaffold.get("phase_complete_path") != "sessions/sample-session/phase_complete.upy_scaffold_plugin.json":
            raise AssertionError(f"payload.scaffold must record phase_complete_path: {scaffold}")
        if scaffold.get("file_count") != len(payload["file_manifest"]["files"]):
            raise AssertionError(f"payload.scaffold file_count mismatch: {scaffold}")
        if not isinstance(scaffold.get("directory_count"), int) or scaffold["directory_count"] <= 0:
            raise AssertionError(f"payload.scaffold directory_count invalid: {scaffold}")
        if scaffold.get("file_status_counts", {}).get("created") is None:
            raise AssertionError(f"payload.scaffold must record file_status_counts: {scaffold}")
        if scaffold.get("lint", {}).get("returncode") != 0:
            raise AssertionError(f"payload.scaffold must record lint summary: {scaffold}")
        if scaffold.get("source", {}).get("source_phase") != "upy-flash-mpy-firmware-plugin":
            raise AssertionError(f"payload.scaffold must record source summary: {scaffold}")
        if scaffold.get("approval_id") != "scaffold_config":
            raise AssertionError(f"payload.scaffold must record approval_id: {scaffold}")
        if scaffold.get("idempotency_key") != phase_complete.get("idempotency_key"):
            raise AssertionError(f"payload.scaffold idempotency_key should match phase_complete: {scaffold}")
        if scaffold.get("incremental") is not False or scaffold.get("generate_scope") != "full_project":
            raise AssertionError(f"payload.scaffold must record full-project scope: {scaffold}")
        source = payload.get("source", {})
        if source.get("source_phase") != "upy-flash-mpy-firmware-plugin":
            raise AssertionError(f"phase_complete must record payload.source.source_phase: {source}")
        if source.get("source_manifest_kind") != "phase_complete":
            raise AssertionError(f"phase_complete must record source_manifest_kind=phase_complete: {source}")
        expected_source_paths = {
            "sessions/sample-session/phase_complete.upy_flash_mpy_firmware_plugin.esp32_c3_success.json",
            "upy-flash-mpy-firmware-plugin/sample/phase_complete.upy_flash_mpy_firmware_plugin.esp32_c3_success.json",
        }
        if source.get("source_phase_complete_path") not in expected_source_paths:
            raise AssertionError(f"phase_complete must record artifact-relative source path: {source}")
        if ":" in source.get("source_phase_complete_path", ""):
            raise AssertionError(f"source path must not be a local absolute path: {source}")
        approval = payload.get("approval", {})
        if approval.get("approval_id") != "scaffold_config" or approval.get("confirmed") is not True:
            raise AssertionError(f"phase_complete must record scaffold_config approval: {approval}")
        if approval.get("selected", {}).get("modules") != scaffold.get("modules"):
            raise AssertionError(f"approval.selected.modules must be structured and normalized: {approval}")
        if not isinstance(approval.get("selected", {}).get("custom_files"), list):
            raise AssertionError(f"approval.selected.custom_files must be a list: {approval}")
        permissions = payload.get("permissions", [])
        permission_types = {item.get("type") for item in permissions}
        if not {"file_operation", "script_run"} <= permission_types:
            raise AssertionError(f"phase_complete must record file/script permissions: {permissions}")
        file_permission = next(item for item in permissions if item.get("type") == "file_operation")
        if file_permission.get("root") != expected_project_root:
            raise AssertionError(f"file permission root must be artifact-relative: {file_permission}")
        file_manifest = payload["file_manifest"]
        if file_manifest.get("root") != expected_project_root:
            raise AssertionError("file_manifest.root must be artifact-relative")
        expected_manifest_path = "sessions/sample-session/scaffold_file_manifest.json"
        if file_manifest.get("path") != expected_manifest_path:
            raise AssertionError("file_manifest.path must point to scaffold_file_manifest.json")
        if not any(artifact.get("type") == "file_manifest" for artifact in payload.get("artifacts", [])):
            raise AssertionError("artifacts must include final file_manifest")
        file_manifest_artifact = next(
            (artifact for artifact in payload.get("artifacts", []) if artifact.get("type") == "file_manifest"),
            None,
        )
        if file_manifest_artifact.get("path") != expected_manifest_path:
            raise AssertionError("file_manifest artifact must declare scaffold_file_manifest.json path")
        file_list = next((artifact for artifact in payload.get("artifacts", []) if artifact.get("type") == "file_list"), None)
        if not file_list or file_list.get("title") != "Scaffold 写入结果":
            raise AssertionError("final file_list title must describe write results")
        statuses = {entry["status"] for entry in file_manifest["files"]}
        if "pending" in statuses:
            raise AssertionError("final file_manifest must not use pending status")
        if not {"created"} <= statuses:
            raise AssertionError(f"first run should create files, got {statuses}")
        for entry in file_manifest["files"]:
            if not entry.get("sha256") or not isinstance(entry.get("bytes"), int):
                raise AssertionError(f"file_manifest entry missing hash/bytes: {entry}")
        if payload["next_phase"] != "upy-generate-plugin":
            raise AssertionError("successful runner should advance to upy-generate-plugin")

        returncode, second = run_runner("--session-dir", str(session_dir), "--manifest", str(FLASH_SAMPLE if FLASH_SAMPLE.exists() else SELECT_HW_SAMPLE))
        if returncode != 0:
            raise AssertionError(f"idempotent rerun should succeed, got {returncode}: {second}")
        statuses = {entry["status"] for entry in second["phase_complete"]["payload"]["file_manifest"]["files"]}
        if statuses != {"unchanged"}:
            raise AssertionError(f"idempotent rerun should mark unchanged, got {statuses}")

        returncode, written = run_runner(
            "--session-dir",
            str(session_dir),
            "--manifest",
            str(FLASH_SAMPLE if FLASH_SAMPLE.exists() else SELECT_HW_SAMPLE),
            "--write-phase-complete",
        )
        if returncode != 0:
            raise AssertionError(f"write-phase-complete rerun should succeed, got {returncode}: {written}")
        manifest_path = session_dir / "scaffold_file_manifest.json"
        if not manifest_path.exists():
            raise AssertionError("runner must write scaffold_file_manifest.json when requested")
        manifest_file = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest_file, dict) or manifest_file.get("root") != expected_project_root:
            raise AssertionError("scaffold_file_manifest.json must be an object with artifact-relative root")
        if len(manifest_file.get("files", [])) != len(file_manifest["files"]):
            raise AssertionError("scaffold_file_manifest.json file count must match phase_complete file_manifest")


def local_actual_runner_detects_conflict_without_force() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "conflict-session"
        session_dir.mkdir(parents=True)
        returncode, summary = run_runner("--session-dir", str(session_dir), "--manifest", str(SELECT_HW_SAMPLE))
        if returncode != 0:
            raise AssertionError(f"initial runner should succeed: {summary}")
        target = session_dir / "project" / "firmware" / "main.py"
        target.write_text("# user changed file\n", encoding="utf-8")
        returncode, conflict = run_runner("--session-dir", str(session_dir), "--manifest", str(SELECT_HW_SAMPLE))
        if returncode == 0:
            raise AssertionError("runner should return non-zero when conflicts are detected")
        payload = conflict["phase_complete"]["payload"]
        if payload["result"] != "partial" or payload["next_phase"] is not None:
            raise AssertionError("conflict should produce partial result with no next_phase")
        errors = payload.get("structured_errors", [])
        if not errors or errors[0].get("code") != "FILE_CONFLICT":
            raise AssertionError(f"conflict should emit FILE_CONFLICT: {errors}")


def scaffold_phase_validator_rejects_success_with_errors() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / "bad-scaffold"
        session_dir.mkdir(parents=True)
        returncode, summary = run_runner("--session-dir", str(session_dir), "--manifest", str(SELECT_HW_SAMPLE))
        if returncode != 0:
            raise AssertionError(f"runner should create a valid baseline: {summary}")
        bad = summary["phase_complete"]
        payload = bad["payload"]
        payload["result"] = "success"
        payload["next_phase"] = "upy-generate-plugin"
        payload["structured_errors"] = [
            {
                "code": "SCAFFOLD_LINT_FAILED",
                "message": "flake8 gate failed",
                "severity": "error",
            }
        ]
        payload["errors"] = ["flake8 gate failed"]
        payload["lint"]["returncode"] = 0
        payload["lint"]["stdout"] = "firmware\\main.py:19:1: E303 too many blank lines (3)\n"
        bad_path = session_dir / "bad_phase_complete.json"
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, result = run_json_allow_failure([
            sys.executable,
            str(VALIDATOR),
            "--input",
            str(bad_path),
            "--validate-phase-complete",
        ])
        if rc == 0 or result.get("status") != "failed":
            raise AssertionError(f"validator must reject success with lint errors: {result}")
        text = json.dumps(result, ensure_ascii=False)
        for expected in ("success payload.structured_errors must be empty", "flake8 violations"):
            if expected not in text:
                raise AssertionError(f"validator did not report {expected}: {result}")


def flash_device_template_has_stable_json_summary() -> None:
    script = ROOT / "templates" / "pc" / "flash_device.py"
    result = subprocess.run(
        [sys.executable, str(script), "--json-summary"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode == 0:
        raise AssertionError("flash_device.py should fail when no action is selected")
    last_line = result.stdout.strip().splitlines()[-1]
    summary = json.loads(last_line)
    if summary.get("status") != "failed" or summary.get("exit_code") != result.returncode:
        raise AssertionError(f"flash_device summary must reflect failure exit: {summary}")
    errors = summary.get("errors", [])
    if not errors or errors[0].get("code") != "no_action":
        raise AssertionError(f"flash_device summary must report no_action: {summary}")


def flash_device_template_upload_uses_resume_fs() -> None:
    text = (ROOT / "templates" / "pc" / "flash_device.py").read_text(encoding="utf-8")
    required = [
        '["resume", "fs", "cp", src, remote]',
        '["resume", "fs", "mkdir", remote_dir]',
        'separators=(",", ":")',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise AssertionError(f"flash_device.py missing stable deploy behavior: {missing}")


def flash_device_template_excludes_source_only_and_mocks() -> None:
    text = (ROOT / "templates" / "pc" / "flash_device.py").read_text(encoding="utf-8")
    required = [
        'SOURCE_ONLY_FILES = {"main.py", "boot.py", "conf.py"}',
        'SOURCE_ONLY_MPY_FILES = {"main.mpy", "boot.mpy", "conf.mpy"}',
        'COMPILE_EXCLUDE_PATTERNS = {"drivers/*/mock.py"}',
        'UPLOAD_EXCLUDE_PATTERNS = {"drivers/*/mock.py", "drivers/*/mock.mpy"}',
        "import shutil",
        "shutil.rmtree(MPY_DIR)",
        "_clear_mpy_dir()",
        "compile_skip_reason(rel)",
        "_stale_mpy_for_source(rel)",
        "forbidden_upload_reason(rel, src)",
        "wrong_firmware_root",
        "python_cache_not_runtime",
        "source_only_compiled",
        "forbidden_upload_artifact",
        "upload_skip_reason(rel)",
        "\"compiled_files\": []",
        "\"uploaded_files\": []",
        "\"skipped_files\": []",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise AssertionError(f"flash_device.py missing production deploy filters: {missing}")
    forbidden = ["ENTRY_FILES", "firmware/{main,boot}.py"]
    present = [item for item in forbidden if item in text]
    if present:
        raise AssertionError(f"flash_device.py still has old entry-only policy: {present}")


def time_helper_templates_do_not_depend_on_cpython_function_repr() -> None:
    class FakeTime:
        current = 0

        @classmethod
        def ticks_us(cls):
            cls.current += 1000
            return cls.current

        @staticmethod
        def ticks_diff(end, start):
            return end - start

    class MicroPythonLikeCallable:
        def __str__(self):
            return "micropython_callable"

        def __call__(self):
            return "ok"

    class MicroPythonLikeAsyncCallable:
        def __str__(self):
            return "micropython_async_callable"

        async def __call__(self):
            return "async-ok"

    template_paths = [
        ROOT / "templates" / "lib" / "time_helper.py",
        REPO / "upy-scaffold" / "templates" / "lib" / "time_helper.py",
    ]
    for template_path in template_paths:
        text = template_path.read_text(encoding="utf-8")
        forbidden = ["split(' ')[1]", 'split(" ")[1]']
        found = [item for item in forbidden if item in text]
        if found:
            raise AssertionError(f"{template_path} still depends on CPython function repr: {found}")
        namespace: dict[str, object] = {}
        exec(compile(text, str(template_path), "exec"), namespace)
        namespace["time"] = FakeTime

        timed_function = namespace["timed_function"](MicroPythonLikeCallable())
        if timed_function() != "ok":
            raise AssertionError(f"{template_path} timed_function wrapper did not return original result")

        timed_coro = namespace["timed_coro"](MicroPythonLikeAsyncCallable())
        if asyncio.run(timed_coro()) != "async-ok":
            raise AssertionError(f"{template_path} timed_coro wrapper did not return original result")


def main() -> int:
    tests = [
        full_timer_generates_json_payload,
        full_accepts_phase_complete_envelope,
        full_accepts_flash_phase_complete_and_uses_firmware_version,
        timer_scaffold_is_esp32_safe_and_logs_fatal_startup,
        timer_scaffold_keeps_rp2_virtual_timer_default,
        timer_scaffold_keeps_zephyr_virtual_timer_default,
        timer_scaffold_uses_hardware_timer_for_general_ports,
        async_omits_scheduler_when_not_timer,
        thread_mode_uses_thread_frame_and_custom_files,
        incremental_generates_only_new_driver_stub,
        incremental_forces_stub_even_when_driver_source_is_none,
        approval_sample_uses_item_groups,
        run_on_device_reports_missing_file_as_json,
        local_actual_runner_writes_session_project_and_file_manifest,
        local_actual_runner_detects_conflict_without_force,
        scaffold_phase_validator_rejects_success_with_errors,
        flash_device_template_has_stable_json_summary,
        flash_device_template_upload_uses_resume_fs,
        flash_device_template_excludes_source_only_and_mocks,
        time_helper_templates_do_not_depend_on_cpython_function_repr,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print(f"[OK] {len(tests)} upy-scaffold smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
