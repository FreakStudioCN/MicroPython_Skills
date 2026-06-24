#!/usr/bin/env python3
"""Smoke tests for upy-flash-mpy-firmware-plugin resources."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample"
SCRIPTS = ROOT / "scripts"
PHASE = "upy-flash-mpy-firmware-plugin"
NEXT_PHASE = "upy-scaffold-plugin"
sys.dont_write_bytecode = True


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
        raise AssertionError(
            f"command failed: {' '.join(args)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def load_script_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_manifest_content_matches_firmware(path_name: str, payload: dict[str, Any]) -> None:
    firmware = payload.get("firmware") or {}
    manifest = payload.get("manifest_content")
    if not isinstance(manifest, dict):
        raise AssertionError(f"{path_name} success payload.manifest_content must be an object")
    if manifest.get("phase") != PHASE:
        raise AssertionError(f"{path_name} manifest_content.phase mismatch")
    if manifest.get("final_status") != "firmware_ready":
        raise AssertionError(f"{path_name} manifest_content.final_status mismatch")
    if not manifest.get("updated_at"):
        raise AssertionError(f"{path_name} manifest_content.updated_at missing")
    for field in ("project_name", "requirements", "devices", "mcu", "hardware_selection"):
        if field not in manifest:
            raise AssertionError(f"{path_name} manifest_content.{field} missing")
    flash = manifest.get("firmware_flash")
    if not isinstance(flash, dict):
        raise AssertionError(f"{path_name} manifest_content.firmware_flash missing")
    for field in ("status", "action", "board_name", "board_url", "latest_url", "file", "file_type", "source", "flash_method"):
        if field in firmware and firmware.get(field) is not None and flash.get(field) != firmware.get(field):
            raise AssertionError(f"{path_name} firmware_flash.{field} must match payload.firmware.{field}")
    if firmware.get("source") == "micropython_latest":
        for field in ("latest_version", "latest_date"):
            if not firmware.get(field):
                raise AssertionError(f"{path_name} payload.firmware.{field} missing")
            if flash.get(field) != firmware[field]:
                raise AssertionError(f"{path_name} firmware_flash.{field} must match payload.firmware.{field}")
    if isinstance(firmware.get("flash_result"), dict) and flash.get("flash_result") != firmware["flash_result"]:
        raise AssertionError(f"{path_name} firmware_flash.flash_result must match payload.firmware.flash_result")
    if firmware.get("flash_method") == "esptool.py":
        for field in ("baud", "chip", "write_offset"):
            if not firmware["flash_result"].get(field):
                raise AssertionError(f"{path_name} firmware.flash_result.{field} missing")


def all_sample_json_files_are_valid() -> None:
    paths = sorted(SAMPLE.glob("*.json"))
    if not paths:
        raise AssertionError("no sample JSON files found")
    for path in paths:
        load_json(path)


def skill_text_matches_protocol() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = [
        "phase_complete.select_hw.json",
        PHASE,
        NEXT_PHASE,
        "firmware_action_select",
        "esp32_flash_confirm",
        "pico_uf2_drag_drop",
        "manual_firmware_flash_confirm",
        "scripts/firmware_page_resolve.py",
        "scripts/firmware_download.py",
        "scripts/list_serial_ports.py",
        "scripts/find_uf2_mount.py",
        "scripts/esp32_flash.py",
        "manifest_content",
        "firmware_flash",
        "final_status=\"firmware_ready\"",
        "action_required=\"install\"",
        "确认烧录 -> bootstrap 检查/安装 -> `esp32_flash.py --plan-only` -> `esp32_flash.py --execute`",
        "Only mock/sample tests may use a fixed `serial_port=\"COM3\"`",
        "Claude Code live use and real plugin use must scan real serial ports",
        "/dev/ttyUSB0",
        "/dev/cu.usbmodem1101",
        "/Volumes/RPI-RP2",
        "/media/$USER/RPI-RP2",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise AssertionError(f"SKILL.md missing expected text: {missing}")
    forbidden = ["scripts/firmware_fetch.py", "scripts/flash_esp32.py", '"next_phase": "upy-scaffold"']
    present = [item for item in forbidden if item in text]
    if present:
        raise AssertionError(f"SKILL.md still mentions obsolete text: {present}")


def start_phase_samples_validate() -> None:
    for path in sorted(SAMPLE.glob("start_phase.upy_flash_mpy_firmware_plugin.*.json")):
        data = load_json(path)
        source = data["payload"]["source_phase_complete"]
        if source["payload"]["next_phase"] != PHASE:
            raise AssertionError(f"{path.name} upstream next_phase mismatch")
        source_path = Path(tempfile.gettempdir()) / f"{path.stem}.source_phase_complete.json"
        source_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
        upstream_result = run_json(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-upstream",
                "--input",
                str(source_path),
            ]
        )
        if upstream_result["status"] != "ok":
            raise AssertionError(f"{path.name} upstream validation failed: {upstream_result}")
        facts = upstream_result["board_facts"]
        if not facts["board_name"] or facts["family"] not in {"esp32", "pico", "manual"}:
            raise AssertionError(f"{path.name} board facts missing or invalid: {facts}")
        result = run_json(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-start-phase",
                "--input",
                str(path),
            ]
        )
        if result["status"] != "ok":
            raise AssertionError(f"{path.name} start validation failed: {result}")


def state_sample_validates() -> None:
    for path in sorted(SAMPLE.glob("flash_mpy_firmware_state.*.json")):
        result = run_json(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-state",
                "--input",
                str(path),
            ]
        )
        if result["status"] != "ok":
            raise AssertionError(f"{path.name} state sample validation failed: {result}")


def state_rejects_phase_complete_status() -> None:
    data = load_json(SAMPLE / "flash_mpy_firmware_state.esp32_c3_success.json")
    data["status"] = "phase_complete"
    data["firmware_file"] = data["payload"]["firmware_file"]
    with tempfile.TemporaryDirectory(prefix="flash-state-bad-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_state.json"
        temp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-state",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("state status=phase_complete should be rejected")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if 'status "phase_complete" is invalid' not in joined:
        raise AssertionError(f"phase_complete status error missing: {result}")
    if "state detail fields should be under payload" not in joined:
        raise AssertionError(f"top-level state detail error missing: {result}")


def firmware_page_resolves_esp32_c5_offset_from_page() -> None:
    data = run_json(
        [
            sys.executable,
            str(SCRIPTS / "firmware_page_resolve.py"),
            "--board-url",
            "https://micropython.org/download/ESP32_GENERIC_C5/",
            "--board-name",
            "ESP32_GENERIC_C5",
            "--board-family",
            "esp32",
            "--html-file",
            str(SAMPLE / "micropython_download_esp32_generic_c5.html"),
        ]
    )
    assert data["status"] == "success"
    assert data["latest"]["file_type"] == "bin"
    assert data["latest"]["url"].endswith("ESP32_GENERIC_C5-20260406-v1.28.0.bin")
    assert data["download_slug"] == "ESP32_GENERIC_C5"
    assert data["resolved"]["match_method"] == "firmware_url_slug"
    assert data["install"]["write_offset"] == "0x2000"
    assert data["install"]["baud"] == 460800
    assert data["install"]["erase_commands"]
    assert data["install"]["write_commands"]


def firmware_page_resolves_esp32_c3_zero_offset_from_page() -> None:
    data = run_json(
        [
            sys.executable,
            str(SCRIPTS / "firmware_page_resolve.py"),
            "--board-url",
            "https://micropython.org/download/ESP32_GENERIC_C3/",
            "--board-name",
            "ESP32_GENERIC_C3",
            "--board-family",
            "esp32",
            "--html-file",
            str(SAMPLE / "micropython_download_esp32_generic_c3.html"),
        ]
    )
    assert data["status"] == "success"
    assert data["latest"]["file_type"] == "bin"
    assert data["latest"]["url"].endswith("ESP32_GENERIC_C3-20260406-v1.28.0.bin")
    assert data["download_slug"] == "ESP32_GENERIC_C3"
    assert data["install"]["write_offset"] == "0"
    assert data["install"]["baud"] == 460800


def firmware_page_resolve_accepts_output_json_alias() -> None:
    with tempfile.TemporaryDirectory(prefix="flash-page-alias-") as temp_dir:
        output = Path(temp_dir) / "resolved.json"
        data = run_json(
            [
                sys.executable,
                str(SCRIPTS / "firmware_page_resolve.py"),
                "--board-url",
                "https://micropython.org/download/ESP32_GENERIC_C3/",
                "--board-name",
                "ESP32_GENERIC_C3",
                "--board-family",
                "esp32",
                "--html-file",
                str(SAMPLE / "micropython_download_esp32_generic_c3.html"),
                "--output-json",
                str(output),
            ]
        )
        assert data["status"] == "success"
        assert output.is_file()


def firmware_page_resolves_board_url_from_download_index() -> None:
    data = run_json(
        [
            sys.executable,
            str(SCRIPTS / "firmware_page_resolve.py"),
            "--download-index-url",
            "https://micropython.org/download/",
            "--board-name",
            "ESP32_GENERIC_C5",
            "--board-family",
            "esp32",
            "--index-html-file",
            str(SAMPLE / "micropython_download_index.html"),
            "--html-file",
            str(SAMPLE / "micropython_download_esp32_generic_c5.html"),
        ]
    )
    assert data["status"] == "success"
    assert data["board_url"] == "https://micropython.org/download/ESP32_GENERIC_C5/"
    assert data["index_source"].endswith("micropython_download_index.html")
    assert data["latest"]["filename"] == "ESP32_GENERIC_C5-20260406-v1.28.0.bin"


def firmware_page_resolves_pico_uf2() -> None:
    data = run_json(
        [
            sys.executable,
            str(SCRIPTS / "firmware_page_resolve.py"),
            "--board-url",
            "https://micropython.org/download/RPI_PICO_W/",
            "--board-name",
            "RPI_PICO_W",
            "--board-family",
            "pico",
            "--html-file",
            str(SAMPLE / "micropython_download_rpi_pico_w.html"),
        ]
    )
    assert data["status"] == "success"
    assert data["latest"]["file_type"] == "uf2"
    assert data["install"]["tool_hint"] == "uf2-drag-drop"
    assert any("RPI-RP2" in step for step in data["install"]["steps"])


def firmware_page_resolves_manual_without_serial_or_flash() -> None:
    data = run_json(
        [
            sys.executable,
            str(SCRIPTS / "firmware_page_resolve.py"),
            "--board-url",
            "https://micropython.org/download/PYBV11/",
            "--board-name",
            "PYBV11",
            "--board-family",
            "manual",
            "--html-file",
            str(SAMPLE / "micropython_download_pybv11.html"),
        ]
    )
    assert data["status"] == "success"
    assert data["latest"]["file_type"] == "dfu"
    assert data["install"]["tool_hint"] == "dfu-util"
    joined = "\n".join(data["install"]["steps"])
    assert "固件" in joined


def firmware_page_resolves_pybd_sf2_manual_instructions() -> None:
    data = run_json(
        [
            sys.executable,
            str(SCRIPTS / "firmware_page_resolve.py"),
            "--board-url",
            "https://micropython.org/download/PYBD_SF2/",
            "--board-name",
            "PYBD_SF2",
            "--board-family",
            "manual",
            "--html-file",
            str(SAMPLE / "micropython_download_pybd_sf2.html"),
        ]
    )
    assert data["status"] == "success"
    assert data["download_slug"] == "PYBD_SF2"
    assert data["resolved"]["board_url"] == "https://micropython.org/download/PYBD_SF2/"
    assert data["latest"]["file_type"] == "dfu"
    assert data["install"]["tool_hint"] == "dfu-util"
    excerpt = data["install"]["raw_text_excerpt"]
    assert "mboot" in excerpt
    assert "USR" in excerpt
    assert "RST" in excerpt
    assert data["install"]["commands"]
    assert all(command["execute_allowed"] is False for command in data["install"]["commands"])


def firmware_download_plan_writes_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="flash-fw-download-") as temp_dir:
        temp_path = Path(temp_dir)
        resolved = temp_path / "resolved.json"
        output = temp_path / "firmware_download.json"
        resolved.write_text(
            json.dumps(
                {
                    "latest": {
                        "url": "https://micropython.org/resources/firmware/test.bin",
                        "filename": "test.bin",
                        "file_type": "bin",
                    }
                }
            ),
            encoding="utf-8",
        )
        data = run_json(
            [
                sys.executable,
                str(SCRIPTS / "firmware_download.py"),
                "--resolved-json",
                str(resolved),
                "--out-dir",
                str(temp_path / "firmware"),
                "--artifact-root",
                str(temp_path),
                "--output-json",
                str(output),
                "--no-download",
            ]
        )
        assert data["status"] == "planned"
        assert data["downloaded"] is False
        assert "\\" not in data["downloaded_path"]
        assert data["downloaded_path"].endswith("/test.bin")
        assert data["downloaded_artifact_path"] == "firmware/test.bin"
        assert output.is_file()


def firmware_download_accepts_out_json_alias() -> None:
    with tempfile.TemporaryDirectory(prefix="flash-fw-download-alias-") as temp_dir:
        temp_path = Path(temp_dir)
        resolved = temp_path / "resolved.json"
        output = temp_path / "firmware_download.json"
        resolved.write_text(
            json.dumps(
                {
                    "latest": {
                        "url": "https://micropython.org/resources/firmware/test.bin",
                        "filename": "test.bin",
                        "file_type": "bin",
                    }
                }
            ),
            encoding="utf-8",
        )
        data = run_json(
            [
                sys.executable,
                str(SCRIPTS / "firmware_download.py"),
                "--resolved-json",
                str(resolved),
                "--out-dir",
                str(temp_path / "firmware"),
                "--artifact-root",
                str(temp_path),
                "--out-json",
                str(output),
                "--no-download",
            ]
        )
        assert data["status"] == "planned"
        assert data["downloaded_artifact_path"] == "firmware/test.bin"
        assert output.is_file()


def mock_serial_port_is_mock_mode_only() -> None:
    mock = run_json(
        [
            sys.executable,
            str(SCRIPTS / "list_serial_ports.py"),
            "--mode",
            "mock",
            "--mock-port",
            "COM3",
        ]
    )
    assert mock["status"] == "success"
    assert mock["mode"] == "mock"
    assert mock["ports"][0]["name"] == "COM3"
    assert mock["ports"][0]["source"] == "mock"
    assert "platform" in mock["ports"][0]

    posix_mock = run_json(
        [
            sys.executable,
            str(SCRIPTS / "list_serial_ports.py"),
            "--mode",
            "mock",
            "--mock-port",
            "/dev/cu.usbmodem1101",
        ]
    )
    assert posix_mock["status"] == "success"
    assert posix_mock["ports"][0]["name"] == "/dev/cu.usbmodem1101"

    proc = run(
        [
            sys.executable,
            str(SCRIPTS / "list_serial_ports.py"),
            "--mock-port",
            "COM3",
        ]
    )
    if proc.returncode == 0:
        raise AssertionError("--mock-port must not be accepted in live mode")
    data = json.loads(proc.stdout)
    assert data["error"]["code"] == "mock_port_not_allowed"


def list_serial_ports_accepts_out_json_alias() -> None:
    with tempfile.TemporaryDirectory(prefix="flash-serial-alias-") as temp_dir:
        output = Path(temp_dir) / "serial_ports.json"
        data = run_json(
            [
                sys.executable,
                str(SCRIPTS / "list_serial_ports.py"),
                "--mode",
                "mock",
                "--mock-port",
                "COM3",
                "--out-json",
                str(output),
            ]
        )
        assert data["status"] == "success"
        assert data["ports"][0]["name"] == "COM3"
        assert output.is_file()


def list_serial_ports_posix_fallback_deduplicates_candidates() -> None:
    wrapper = load_script_module("flash_list_serial_ports_wrapper", SCRIPTS / "list_serial_ports.py")
    script_path = wrapper.find_shared_script() if hasattr(wrapper, "find_shared_script") else SCRIPTS / "list_serial_ports.py"
    module = load_script_module("flash_shared_list_serial_ports", script_path)
    with tempfile.TemporaryDirectory(prefix="flash-posix-ports-") as temp_dir:
        temp_path = Path(temp_dir)
        port_a = temp_path / "ttyUSB0"
        port_b = temp_path / "ttyACM0"
        port_a.write_text("", encoding="utf-8")
        port_b.write_text("", encoding="utf-8")
        ports = module.posix_fallback_ports(
            [
                str(temp_path / "ttyUSB*"),
                str(temp_path / "ttyUSB0"),
                str(temp_path / "ttyACM*"),
            ]
        )
    names = [item["name"] for item in ports]
    assert names == [str(port_a), str(port_b)]
    assert ports[0]["source"] == "posix-glob"
    assert "platform" in ports[0]


def find_uf2_mount_reports_candidate_without_copying() -> None:
    with tempfile.TemporaryDirectory(prefix="flash-uf2-mount-") as temp_dir:
        mount = Path(temp_dir) / "RPI-RP2"
        output = Path(temp_dir) / "uf2_mount.json"
        mount.mkdir()
        data = run_json(
            [
                sys.executable,
                str(SCRIPTS / "find_uf2_mount.py"),
                "--candidate",
                str(mount),
                "--out-json",
                str(output),
            ]
        )
        assert data["status"] == "found"
        assert data["mounts"][0]["path"] == str(mount)
        assert data["label"] == "RPI-RP2"
        assert output.is_file()


def bootstrap_missing_is_action_required_not_failure() -> None:
    script = SCRIPTS / "bootstrap_esptool.py"
    original_text = script.read_text(encoding="utf-8")
    patched_text = original_text.replace('SCRIPT_DIR = Path(__file__).resolve().parent', 'SCRIPT_DIR = Path.cwd()')
    with tempfile.TemporaryDirectory(prefix="flash-bootstrap-missing-") as temp_dir:
        temp_path = Path(temp_dir)
        temp_script = temp_path / "bootstrap_esptool.py"
        temp_script.write_text(patched_text, encoding="utf-8")
        (temp_path / "requirements-esptool.txt").write_text("esptool==4.11.0\n", encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(temp_script),
                "--output-json",
                str(temp_path / "bootstrap.json"),
            ],
            cwd=temp_path,
        )
    if proc.returncode != 0:
        raise AssertionError(f"missing esptool env check should return 0:\n{proc.stdout}\n{proc.stderr}")
    data = json.loads(proc.stdout)
    assert data["status"] == "missing"
    assert data["action_required"] == "install"
    assert "error" not in data


def esp32_flash_plan_uses_page_offset_and_skill_local_esptool_path() -> None:
    with tempfile.TemporaryDirectory(prefix="flash-fw-plan-") as temp_dir:
        temp_path = Path(temp_dir)
        resolved = temp_path / "resolved.json"
        firmware = temp_path / "firmware.bin"
        firmware.write_bytes(b"dummy")
        resolved_data = run_json(
            [
                sys.executable,
                str(SCRIPTS / "firmware_page_resolve.py"),
                "--board-url",
                "https://micropython.org/download/ESP32_GENERIC_C5/",
                "--board-name",
                "ESP32_GENERIC_C5",
                "--board-family",
                "esp32",
                "--html-file",
                str(SAMPLE / "micropython_download_esp32_generic_c5.html"),
                "--out-json",
                str(resolved),
            ]
        )
        assert resolved_data["install"]["write_offset"] == "0x2000"
        data = run_json(
            [
                sys.executable,
                str(SCRIPTS / "esp32_flash.py"),
                "--resolved-json",
                str(resolved),
                "--firmware",
                str(firmware),
                "--chip-family",
                "esp32c5",
                "--port",
                "COM3",
                "--plan-only",
                "--command-style",
                "underscore",
                "--artifact-root",
                str(temp_path),
            ]
        )
    assert data["status"] == "planned"
    assert data["execute"] is False
    assert data["chip"] == "esp32c5"
    assert data["write_offset"] == "0x2000"
    assert data["commands"][0][-1] == "erase_flash"
    assert data["commands"][1][-3:] == ["write_flash", "0x2000", str(firmware)]
    assert ".venv-esptool" in data["commands"][0][0]
    assert data["firmware_artifact_path"] == "firmware.bin"
    assert data["rendered_commands_posix"][0].endswith("--port COM3 erase_flash")


def esp32_flash_accepts_out_json_alias() -> None:
    with tempfile.TemporaryDirectory(prefix="flash-fw-plan-alias-") as temp_dir:
        temp_path = Path(temp_dir)
        resolved = temp_path / "resolved.json"
        firmware = temp_path / "firmware.bin"
        output = temp_path / "esptool_plan.json"
        firmware.write_bytes(b"dummy")
        run_json(
            [
                sys.executable,
                str(SCRIPTS / "firmware_page_resolve.py"),
                "--board-url",
                "https://micropython.org/download/ESP32_GENERIC_C3/",
                "--board-name",
                "ESP32_GENERIC_C3",
                "--board-family",
                "esp32",
                "--html-file",
                str(SAMPLE / "micropython_download_esp32_generic_c3.html"),
                "--out-json",
                str(resolved),
            ]
        )
        data = run_json(
            [
                sys.executable,
                str(SCRIPTS / "esp32_flash.py"),
                "--resolved-json",
                str(resolved),
                "--firmware",
                str(firmware),
                "--chip-family",
                "esp32c3",
                "--port",
                "/dev/ttyUSB0",
                "--plan-only",
                "--artifact-root",
                str(temp_path),
                "--out-json",
                str(output),
            ]
        )
        assert data["status"] == "planned"
        assert data["port"] == "/dev/ttyUSB0"
        assert data["commands"][0][6] == "/dev/ttyUSB0"
        assert "--port /dev/ttyUSB0" in data["rendered_commands_posix"][0]
        assert data["write_offset"] == "0"
        assert data["firmware_artifact_path"] == "firmware.bin"
        assert output.is_file()


def phase_complete_samples_validate_with_artifacts() -> None:
    with tempfile.TemporaryDirectory(prefix="flash-phase-") as temp_dir:
        artifact_root = Path(temp_dir)
        for path in sorted(SAMPLE.glob("phase_complete.upy_flash_mpy_firmware_plugin.*.json")):
            data = load_json(path)
            for artifact in data["payload"].get("artifacts", []):
                if artifact.get("type") != "file_list":
                    continue
                for item in artifact.get("files", []):
                    target = artifact_root / item["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("sample artifact\n", encoding="utf-8")
            temp_phase = artifact_root / path.name
            shutil.copy2(path, temp_phase)
            result = run_json(
                [
                    sys.executable,
                    str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                    "--validate-phase-complete",
                    "--input",
                    str(temp_phase),
                    "--artifact-root",
                    str(artifact_root),
                ]
            )
            if result["status"] != "ok":
                raise AssertionError(f"{path.name} phase_complete validation failed: {result}")
            payload = data["payload"]
            if payload["result"] == "success":
                if payload["next_phase"] != NEXT_PHASE:
                    raise AssertionError(f"{path.name} success next_phase mismatch")
                if payload.get("source_phase") != "select-hw":
                    raise AssertionError(f"{path.name} success source_phase mismatch")
                if not payload.get("source_phase_complete_path"):
                    raise AssertionError(f"{path.name} success source_phase_complete_path missing")
                assert_manifest_content_matches_firmware(path.name, payload)
            if payload["result"] in {"partial", "failed"} and payload["next_phase"] is not None:
                raise AssertionError(f"{path.name} partial/failed next_phase must be null")
            declared = {
                item["path"]
                for artifact in payload.get("artifacts", [])
                if artifact.get("type") == "file_list"
                for item in artifact.get("files", [])
            }
            for artifact in payload.get("artifacts", []):
                if artifact.get("type") != "file_list":
                    continue
                for item in artifact.get("files", []):
                    description = item.get("description") or ""
                    if "flash-mpy-firmware" in description:
                        raise AssertionError(f"{path.name} artifact description uses obsolete phase name: {description}")
            firmware = payload.get("firmware") or {}
            if firmware.get("file") and firmware["file"] not in declared:
                raise AssertionError(f"{path.name} firmware.file missing from artifacts")
            flash_result = firmware.get("flash_result") or {}
            if flash_result.get("log") and flash_result["log"] not in declared:
                raise AssertionError(f"{path.name} flash_result.log missing from artifacts")


def phase_complete_success_requires_manifest_content() -> None:
    sample = load_json(SAMPLE / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_success.json")
    sample["payload"].pop("manifest_content", None)
    with tempfile.TemporaryDirectory(prefix="flash-phase-no-manifest-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_phase_complete.json"
        temp_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-phase-complete",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("success phase_complete without manifest_content should be rejected")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "success payload.manifest_content must be an object" not in joined:
        raise AssertionError(f"manifest_content missing error not reported: {result}")


def phase_complete_success_requires_source_chain() -> None:
    sample = load_json(SAMPLE / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_success.json")
    sample["payload"].pop("source_phase", None)
    sample["payload"].pop("source_phase_complete_path", None)
    with tempfile.TemporaryDirectory(prefix="flash-phase-no-source-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_phase_complete.json"
        temp_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-phase-complete",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("success phase_complete without source chain should be rejected")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "success payload.source_phase must be select-hw" not in joined:
        raise AssertionError(f"source_phase error not reported: {result}")
    if "success payload.source_phase_complete_path must be a relative path" not in joined:
        raise AssertionError(f"source_phase_complete_path error not reported: {result}")


def phase_complete_rejects_manifest_firmware_mismatch() -> None:
    sample = load_json(SAMPLE / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_success.json")
    sample["payload"]["manifest_content"]["firmware_flash"]["file"] = "sessions/sample-esp32-c5/firmware/wrong.bin"
    with tempfile.TemporaryDirectory(prefix="flash-phase-manifest-mismatch-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_phase_complete.json"
        temp_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-phase-complete",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("manifest_content.firmware_flash mismatch should be rejected")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "payload.manifest_content.firmware_flash.file must match payload.firmware.file" not in joined:
        raise AssertionError(f"manifest firmware mismatch error not reported: {result}")


def phase_complete_rejects_missing_latest_metadata() -> None:
    sample = load_json(SAMPLE / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_success.json")
    sample["payload"]["firmware"].pop("latest_version", None)
    sample["payload"]["manifest_content"]["firmware_flash"].pop("latest_version", None)
    with tempfile.TemporaryDirectory(prefix="flash-phase-no-latest-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_phase_complete.json"
        temp_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-phase-complete",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("micropython_latest success without latest metadata should be rejected")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "payload.firmware.latest_version is required for micropython_latest success" not in joined:
        raise AssertionError(f"latest_version missing error not reported: {result}")


def phase_complete_rejects_missing_esp32_flash_details() -> None:
    sample = load_json(SAMPLE / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_success.json")
    sample["payload"]["firmware"]["flash_result"].pop("baud", None)
    sample["payload"]["manifest_content"]["firmware_flash"]["flash_result"].pop("baud", None)
    with tempfile.TemporaryDirectory(prefix="flash-phase-no-baud-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_phase_complete.json"
        temp_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-phase-complete",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("ESP32 success without baud should be rejected")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "payload.firmware.flash_result.baud is required for ESP32 success" not in joined:
        raise AssertionError(f"baud missing error not reported: {result}")


def phase_complete_cwd_mode_rejects_bare_artifact_paths() -> None:
    sample = load_json(SAMPLE / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_success.json")
    for artifact in sample["payload"]["artifacts"]:
        if artifact.get("type") != "file_list":
            continue
        for item in artifact.get("files", []):
            item["path"] = Path(item["path"]).name
    with tempfile.TemporaryDirectory(prefix="flash-phase-bad-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_phase_complete.json"
        temp_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-phase-complete",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("cwd mode should reject bare artifact filenames")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "must be under sessions/sample-esp32-c5/" not in joined:
        raise AssertionError(f"cwd artifact path error missing: {result}")


def phase_complete_rejects_object_artifacts_with_clear_error() -> None:
    sample = load_json(SAMPLE / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_success.json")
    file_list = sample["payload"]["artifacts"][0]["files"]
    sample["payload"]["artifacts"] = {"file_list": file_list}
    with tempfile.TemporaryDirectory(prefix="flash-phase-object-artifacts-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_phase_complete.json"
        temp_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-phase-complete",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("object payload.artifacts should be rejected")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "not an object like {'file_list': [...]}" not in joined:
        raise AssertionError(f"object artifacts hint missing: {result}")


def phase_complete_rejects_flat_artifacts_with_clear_error() -> None:
    sample = load_json(SAMPLE / "phase_complete.upy_flash_mpy_firmware_plugin.esp32_success.json")
    sample["payload"]["artifacts"] = sample["payload"]["artifacts"][0]["files"]
    with tempfile.TemporaryDirectory(prefix="flash-phase-flat-artifacts-") as temp_dir:
        temp_path = Path(temp_dir) / "bad_phase_complete.json"
        temp_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(SCRIPTS / "flash_mpy_firmware_manifest.py"),
                "--validate-phase-complete",
                "--input",
                str(temp_path),
            ]
        )
    if proc.returncode == 0:
        raise AssertionError("flat payload.artifacts should be rejected")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "looks like a flat file entry and must move under files[]" not in joined:
        raise AssertionError(f"flat artifacts hint missing: {result}")


def main() -> int:
    checks = [
        all_sample_json_files_are_valid,
        skill_text_matches_protocol,
        start_phase_samples_validate,
        state_sample_validates,
        state_rejects_phase_complete_status,
        firmware_page_resolves_esp32_c5_offset_from_page,
        firmware_page_resolves_esp32_c3_zero_offset_from_page,
        firmware_page_resolve_accepts_output_json_alias,
        firmware_page_resolves_board_url_from_download_index,
        firmware_page_resolves_pico_uf2,
        firmware_page_resolves_manual_without_serial_or_flash,
        firmware_page_resolves_pybd_sf2_manual_instructions,
        firmware_download_plan_writes_manifest,
        firmware_download_accepts_out_json_alias,
        mock_serial_port_is_mock_mode_only,
        list_serial_ports_accepts_out_json_alias,
        list_serial_ports_posix_fallback_deduplicates_candidates,
        find_uf2_mount_reports_candidate_without_copying,
        bootstrap_missing_is_action_required_not_failure,
        esp32_flash_plan_uses_page_offset_and_skill_local_esptool_path,
        esp32_flash_accepts_out_json_alias,
        phase_complete_samples_validate_with_artifacts,
        phase_complete_success_requires_manifest_content,
        phase_complete_success_requires_source_chain,
        phase_complete_rejects_manifest_firmware_mismatch,
        phase_complete_rejects_missing_latest_metadata,
        phase_complete_rejects_missing_esp32_flash_details,
        phase_complete_cwd_mode_rejects_bare_artifact_paths,
        phase_complete_rejects_object_artifacts_with_clear_error,
        phase_complete_rejects_flat_artifacts_with_clear_error,
    ]
    for check in checks:
        check()
        print(f"[OK] {check.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
