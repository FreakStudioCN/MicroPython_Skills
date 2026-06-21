#!/usr/bin/env python3
"""
Validate and normalize upy-analyze V0 manifest and phase_complete messages.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "1.0"
PHASE = "analyze"
NEXT_PHASE_ON_SUCCESS = "select-hw"

VALID_ENUMS = {
    "scene": ["indoor", "outdoor", "vehicle", "industrial", "wearable", "underwater", "unknown"],
    "power": ["usb", "battery_li", "battery_disposable", "solar", "poe", "unknown"],
    "network": ["none", "wifi", "ble", "mqtt", "zigbee", "lora", "4g", "unknown"],
    "sample_rate": ["high_100hz_plus", "normal_1hz", "low_minute", "triggered", "unknown"],
    "precision": ["high", "normal", "low_power_first", "unknown"],
    "response_time": ["ms_level", "1s", "minute_level", "unknown"],
    "temp_range": ["normal_0_40", "extended_-20_70", "industrial_-40_85", "unknown"],
    "size_constraint": ["none", "compact", "wearable", "custom", "unknown"],
    "budget_yuan": ["low_30", "medium_50", "medium_100", "high_200", "unlimited", "unknown"],
    "experience": ["beginner", "experienced", "unknown"],
}

VALID_OUTPUT_TYPES = [
    "serial",
    "display_oled",
    "display_lcd",
    "display_eink",
    "buzzer",
    "led",
    "led_rgb",
    "cloud_mqtt",
    "cloud_http",
    "local_file",
    "relay",
    "motor",
    "servo",
]

VALID_SPECIAL_REQS = [
    "watchdog",
    "ota_update",
    "deep_sleep",
    "encryption",
    "button_control",
    "voice_control",
    "battery_monitor",
    "error_led",
    "none",
]

VALID_DEVICE_INTERFACES = [
    "I2C",
    "SPI",
    "UART",
    "GPIO",
    "PWM",
    "ADC",
    "I2S",
    "1-Wire",
    "CAN",
    "USB",
    "WiFi",
    "BLE",
]

VALID_DRIVER_SOURCES = [
    "builtin_runtime",
    "micropython_lib",
    "upypi",
    "awesome-micropython",
    "github",
    "local",
    "cold-driver",
    "none",
]
VALID_DEVICE_SOURCES = ["user_specified", "system_recommended"]
REAL_DRIVER_SOURCES = ["micropython_lib", "upypi", "awesome-micropython", "github", "local"]

PHASE_COMPLETE_RESULTS = ["success", "partial", "failed"]
ARTIFACT_TYPES = ["table", "file_tree", "markdown", "html", "code_diff", "file_list"]
ARTIFACT_FILE_STATUSES = ["created", "updated", "unchanged", "skipped", "error"]
STRUCTURED_ERROR_SEVERITIES = ["info", "warning", "error", "fatal"]

CORE_MANIFEST_FIELDS = [
    "schema_version",
    "phase",
    "project_name",
    "requirements",
    "devices",
    "final_status",
]

BUILTIN_INTERFACE_MODULE_MAP = {
    "ADC": "machine.ADC",
    "GPIO": "machine.Pin",
    "I2C": "machine.I2C",
    "SPI": "machine.SPI",
    "UART": "machine.UART",
    "I2S": "machine.I2S",
    "1-Wire": "onewire",
    "WiFi": "network",
    "BLE": "bluetooth",
}

BUILTIN_GPIO_DEVICE_TYPES = {
    "touch_sensor",
    "button",
    "buzzer",
    "relay",
    "led",
    "led_rgb",
}

MICROPYTHON_LIB_MIDDLEWARE_TYPES = {
    "ble_stack",
    "middleware",
    "protocol_stack",
    "network_stack",
}

REQUIREMENTS_DEFAULTS = {
    "scene": "indoor",
    "power": "usb",
    "network": "none",
    "sample_rate": "normal_1hz",
    "precision": "normal",
    "response_time": "1s",
    "temp_range": "normal_0_40",
    "size_constraint": "none",
    "budget_yuan": "medium_50",
    "experience": "beginner",
    "output": ["serial"],
    "existing_hardware": [],
    "special_requirements": ["none"],
    "mcu_specified": None,
}


def load_input(args: argparse.Namespace) -> dict[str, Any]:
    if args.stdin:
        return json.load(sys.stdin)
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            return json.load(f)
    raise ValueError("must provide --stdin or --input")


def is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def is_iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def validate_and_fill(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not data.get("project_name"):
        errors.append("missing required field: project_name")
    if "requirements" not in data:
        errors.append("missing required field: requirements")
    if "devices" not in data:
        errors.append("missing required field: devices")

    if errors:
        return errors

    requirements = data["requirements"]
    devices = data["devices"]

    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        return errors
    if not isinstance(devices, list):
        errors.append("devices must be an array")
        return errors
    if not devices:
        errors.append("devices must not be empty")
        return errors

    if not requirements.get("description"):
        errors.append("requirements.description is required")

    for field, default in REQUIREMENTS_DEFAULTS.items():
        if field not in requirements or requirements[field] is None:
            requirements[field] = copy.deepcopy(default)
            continue

        value = requirements[field]
        if field in VALID_ENUMS:
            if value not in VALID_ENUMS[field]:
                errors.append(
                    f"requirements.{field} invalid value '{value}', valid values: {VALID_ENUMS[field]}"
                )
        elif field == "output":
            if not isinstance(value, list):
                errors.append("requirements.output must be an array")
            else:
                for item in value:
                    if item not in VALID_OUTPUT_TYPES:
                        errors.append(
                            f"requirements.output invalid value '{item}', valid values: {VALID_OUTPUT_TYPES}"
                        )
        elif field == "special_requirements":
            if not isinstance(value, list):
                errors.append("requirements.special_requirements must be an array")
            else:
                for item in value:
                    if item not in VALID_SPECIAL_REQS:
                        errors.append(
                            f"requirements.special_requirements invalid value '{item}', valid values: {VALID_SPECIAL_REQS}"
                        )
        elif field == "existing_hardware":
            if not isinstance(value, list):
                errors.append("requirements.existing_hardware must be an array")

    for index, device in enumerate(devices):
        prefix = f"devices[{index}]"
        if not isinstance(device, dict):
            errors.append(f"{prefix} must be an object")
            continue

        for field in ["name", "type", "interface"]:
            if not device.get(field):
                errors.append(f"{prefix} missing required field: {field}")

        if not device.get("source"):
            errors.append(f"{prefix} missing required field: source")
        elif device["source"] not in VALID_DEVICE_SOURCES:
            errors.append(
                f"{prefix}.source invalid value '{device['source']}', valid values: {VALID_DEVICE_SOURCES}"
            )

        if device.get("interface") and device["interface"] not in VALID_DEVICE_INTERFACES:
            errors.append(
                f"{prefix}.interface invalid value '{device['interface']}', valid values: {VALID_DEVICE_INTERFACES}"
            )

        if "i2c_addr" in device and device["i2c_addr"]:
            if not isinstance(device["i2c_addr"], list):
                errors.append(f"{prefix}.i2c_addr must be an array")
            else:
                for addr in device["i2c_addr"]:
                    if not isinstance(addr, str) or not addr.startswith("0x"):
                        errors.append(f"{prefix}.i2c_addr '{addr}' must be a 0x-prefixed string")

        driver = device.get("driver")
        if not driver:
            errors.append(f"{prefix}.driver is required")
        elif not isinstance(driver, dict):
            errors.append(f"{prefix}.driver must be an object")
        else:
            source = driver.get("source")
            if not source:
                errors.append(f"{prefix}.driver.source is required")
            elif source not in VALID_DRIVER_SOURCES:
                errors.append(
                    f"{prefix}.driver.source invalid value '{source}', valid values: {VALID_DRIVER_SOURCES}"
                )

            if source in REAL_DRIVER_SOURCES:
                if not driver.get("package_name"):
                    errors.append(f"{prefix}.driver.package_name is required when driver.source={source}")
                if not driver.get("install_cmd"):
                    errors.append(f"{prefix}.driver.install_cmd is required when driver.source={source}")
                if source == "micropython_lib" and not driver.get("repo_url"):
                    errors.append(f"{prefix}.driver.repo_url is required when driver.source=micropython_lib")

        if "quantity" not in device:
            device["quantity"] = 1

    return errors


def validate_semantics(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    requirements = data.get("requirements", {})
    devices = data.get("devices", [])
    description = str(requirements.get("description", "")).lower()
    output = requirements.get("output", [])

    device_names = [str(device.get("name", "")).lower() for device in devices]
    device_types = [str(device.get("type", "")).lower() for device in devices]
    interfaces = [str(device.get("interface", "")) for device in devices]

    if len(devices) != len({(d.get("name"), d.get("interface")) for d in devices}):
        warnings.append("duplicate devices detected with same name/interface; analyze output may need deduplication")

    if any(keyword in description for keyword in ["语音", "对话", "voice", "audio"]):
        if not any("microphone" in item or "speaker" in item or interface == "I2S" for item, interface in zip(device_types, interfaces)):
            warnings.append("description suggests voice interaction, but no microphone/speaker or I2S device was found")

    if any(keyword in description for keyword in ["显示", "屏幕", "oled", "screen", "display"]):
        if not any("display" in item for item in device_types):
            warnings.append("description suggests display output, but no display device was found")
        if not any(str(item).startswith("display_") for item in output):
            warnings.append("description suggests display output, but requirements.output has no display_* target")

    if any(keyword in description for keyword in ["报警", "蜂鸣", "alert", "alarm", "buzzer"]):
        if not any(item in ["buzzer", "relay", "led", "led_rgb"] for item in device_types):
            warnings.append("description suggests alert/alarm output, but no buzzer/relay/led device was found")

    if any(keyword in description for keyword in ["土壤", "soil"]):
        if not any("soil" in item for item in device_types + device_names):
            warnings.append("description suggests soil sensing, but no soil-related device was found")

    if any(keyword in description for keyword in ["温湿度", "humidity", "temperature"]):
        if not any(("temperature" in item) or ("humidity" in item) or ("sht" in name) for item, name in zip(device_types, device_names)):
            warnings.append("description suggests temperature/humidity sensing, but no matching sensor was found")

    for index, device in enumerate(devices):
        prefix = f"devices[{index}]"
        driver = device.get("driver", {})
        source = device.get("source")
        driver_source = driver.get("source")
        interface = device.get("interface")
        device_type = str(device.get("type", "")).lower()
        driver_notes = str(driver.get("notes", "") or driver.get("note", "")).lower()
        driver_module = str(driver.get("module", "")).lower()

        if interface == "I22C":
            errors.append(f"{prefix}.interface has suspicious value 'I22C'; did you mean 'I2C'?")

        if driver_source == "cold-driver" and source != "user_specified":
            warnings.append(f"{prefix} uses cold-driver but source is not user_specified; confirm this is intentional")

        if driver_source == "builtin_runtime" and not driver_module:
            warnings.append(f"{prefix} uses builtin_runtime but driver.module is missing")

        if driver_source == "micropython_lib" and "machine." in driver_notes:
            warnings.append(f"{prefix} is marked micropython_lib but notes look like builtin runtime support; confirm classification")

        if driver_source == "micropython_lib" and device_type not in MICROPYTHON_LIB_MIDDLEWARE_TYPES:
            warnings.append(
                f"{prefix} uses micropython_lib; confirm this is an official ecosystem middleware/general-purpose package rather than a concrete device driver"
            )

        if isinstance(driver.get("api_ref"), str):
            warnings.append(f"{prefix}.driver.api_ref is a string; prefer a structured object with init/read notes")

        if driver_source in {"awesome-micropython", "github"} and not (driver.get("repo_url") or driver.get("url")):
            warnings.append(f"{prefix}.driver should include repo_url or url when driver.source={driver_source}")

        if driver_source == "local":
            errors.append(f"{prefix} uses driver.source=local, but analyze phase should prefer builtin_runtime / micropython_lib / upypi / github")

        builtin_module = BUILTIN_INTERFACE_MODULE_MAP.get(interface)
        builtin_expected = False
        if interface in {"ADC", "I2S", "WiFi", "BLE"}:
            builtin_expected = True
        elif interface == "GPIO" and device_type in BUILTIN_GPIO_DEVICE_TYPES:
            builtin_expected = True
        elif "machine." in driver_notes or driver_module.startswith("machine."):
            builtin_expected = True

        if driver_source == "none" and builtin_expected:
            module_hint = builtin_module or "builtin runtime"
            errors.append(
                f"{prefix} is using driver.source=none, but this device should be classified as builtin_runtime ({module_hint})"
            )

        if driver_source == "builtin_runtime" and interface == "1-Wire":
            if not any(part in driver_module for part in ["onewire", "ds18x20"]):
                warnings.append(f"{prefix} uses 1-Wire builtin_runtime; module should mention onewire or ds18x20")

        if driver_source == "builtin_runtime" and driver_module == "machine.touchpad":
            warnings.append(
                f"{prefix} uses machine.TouchPad; confirm the selected board supports ESP32 capacitive touch, otherwise use machine.Pin for an external touch module"
            )

        if driver_source == "none" and interface in {"I2C", "SPI", "UART", "I2S"} and source == "system_recommended":
            warnings.append(f"{prefix} is system_recommended on {interface} but still has no ready driver; consider replacement recommendation")

        if driver_source == "builtin_runtime" and interface in {"I2C", "SPI", "UART"} and source == "system_recommended":
            warnings.append(
                f"{prefix} currently only records builtin_runtime on {interface}; if this is a concrete device, analyze should still prefer checking upypi first"
            )

        if driver_source == "none":
            if interface == "ADC":
                warnings.append(f"{prefix} may be better classified as builtin_runtime (machine.ADC) instead of none")
            elif interface == "GPIO" and device_type in BUILTIN_GPIO_DEVICE_TYPES:
                warnings.append(f"{prefix} may be better classified as builtin_runtime (machine.Pin/PWM) instead of none")
            elif interface == "I2S":
                warnings.append(f"{prefix} may be better classified as builtin_runtime (machine.I2S) instead of none")
            elif "machine." in driver_notes:
                warnings.append(f"{prefix} note references a built-in machine.* API; consider driver.source=builtin_runtime")

        if driver_source == "upypi" and "pypi.org" in str(driver.get("install_cmd", "")).lower():
            warnings.append(f"{prefix} uses upypi source but install_cmd points to PyPI; confirm MicroPython package source")

        if device_type == "display" and not any(str(item).startswith("display_") for item in output):
            warnings.append(f"{prefix} is a display device but requirements.output has no display_* target")

    if any(keyword in description for keyword in ["语音", "对话", "voice", "audio"]):
        if output == ["serial"]:
            warnings.append("description suggests voice interaction, but requirements.output only contains serial; record audio/cloud limitations in warnings or notes")

    if any(keyword in description for keyword in ["云端", "联网", "llm", "api"]):
        if requirements.get("network") != "wifi":
            warnings.append("description suggests cloud/network use, but requirements.network is not wifi")

    if any(keyword in description for keyword in ["气体", "gas", "co2", "空气"]):
        if not any("gas" in item or "air" in item for item in device_types + device_names):
            warnings.append("description suggests gas/air sensing, but no gas/air-related device was found")

    return errors, warnings


def build_manifest(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": "1.0",
        "phase": PHASE,
        "created_at": now,
        "updated_at": now,
        "project_name": data["project_name"],
        "requirements": data["requirements"],
        "devices": data["devices"],
        "final_status": "pending",
    }


def normalize_manifest_for_compare(manifest: dict[str, Any]) -> dict[str, Any]:
    copy_manifest = copy.deepcopy(manifest)
    if "schema_version" not in copy_manifest:
        copy_manifest["schema_version"] = "1.0"
    if "phase" not in copy_manifest:
        copy_manifest["phase"] = PHASE
    if "final_status" not in copy_manifest:
        copy_manifest["final_status"] = "pending"
    return {field: copy_manifest.get(field) for field in CORE_MANIFEST_FIELDS}


def validate_structured_errors(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, list):
        return ["phase_complete.structured_errors must be an array"]
    for index, item in enumerate(value):
        prefix = f"phase_complete.structured_errors[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ["code", "message", "severity"]:
            if not item.get(field):
                errors.append(f"{prefix}.{field} is required")
        if item.get("severity") and item["severity"] not in STRUCTURED_ERROR_SEVERITIES:
            errors.append(
                f"{prefix}.severity invalid value '{item['severity']}', valid values: {STRUCTURED_ERROR_SEVERITIES}"
            )
        for bool_field in ["recoverable", "retryable"]:
            if bool_field in item and not isinstance(item[bool_field], bool):
                errors.append(f"{prefix}.{bool_field} must be boolean")
    return errors


def validate_checkpoint(value: Any, *, required: bool) -> list[str]:
    errors: list[str] = []
    if value is None:
        if required:
            errors.append("phase_complete.checkpoint is required when result=partial")
        return errors
    if not isinstance(value, dict):
        return ["phase_complete.checkpoint must be an object"]

    for field in ["checkpoint_id", "resume_phase", "resume_step", "resume_label", "reason"]:
        if not value.get(field):
            errors.append(f"phase_complete.checkpoint.{field} is required")
    if value.get("checkpoint_id") and not is_uuid(value["checkpoint_id"]):
        errors.append("phase_complete.checkpoint.checkpoint_id must be a UUID string")
    if value.get("resume_phase") != PHASE:
        errors.append("phase_complete.checkpoint.resume_phase must be 'analyze'")
    return errors


def validate_artifacts(artifacts: Any, artifact_root: str | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(artifacts, list):
        errors.append("phase_complete.artifacts must be an array")
        return errors, warnings

    root = Path(artifact_root) if artifact_root else None

    for index, artifact in enumerate(artifacts):
        prefix = f"phase_complete.artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{prefix} must be an object")
            continue

        artifact_type = artifact.get("type")
        if artifact_type not in ARTIFACT_TYPES:
            errors.append(f"{prefix}.type invalid value '{artifact_type}', valid values: {ARTIFACT_TYPES}")
            continue

        if artifact_type == "table":
            if not isinstance(artifact.get("headers"), list):
                errors.append(f"{prefix}.headers must be an array for table artifacts")
            if not isinstance(artifact.get("rows"), list):
                errors.append(f"{prefix}.rows must be an array for table artifacts")
        elif artifact_type == "file_list":
            files = artifact.get("files")
            if not isinstance(files, list):
                errors.append(f"{prefix}.files must be an array for file_list artifacts")
            else:
                for file_index, file_item in enumerate(files):
                    file_prefix = f"{prefix}.files[{file_index}]"
                    if not isinstance(file_item, dict):
                        errors.append(f"{file_prefix} must be an object")
                        continue
                    rel_path = file_item.get("path")
                    if not rel_path:
                        errors.append(f"{file_prefix}.path is required")
                    status = file_item.get("status")
                    if status not in ARTIFACT_FILE_STATUSES:
                        errors.append(
                            f"{file_prefix}.status invalid value '{status}', valid values: {ARTIFACT_FILE_STATUSES}"
                        )
                    if "kind" not in file_item:
                        warnings.append(f"{file_prefix}.kind is recommended")
                    if "description" not in file_item:
                        warnings.append(f"{file_prefix}.description is recommended")
                    if root and rel_path and not (root / rel_path).exists():
                        errors.append(f"{file_prefix}.path declares missing artifact file: {rel_path}")
        elif artifact_type == "markdown":
            if not isinstance(artifact.get("content"), str):
                errors.append(f"{prefix}.content must be a string for markdown artifacts")

    return errors, warnings


def validate_envelope(data: dict[str, Any]) -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []

    if data.get("protocol_version") != PROTOCOL_VERSION:
        errors.append(f"protocol_version must be '{PROTOCOL_VERSION}'")
    if not is_uuid(data.get("msg_id")):
        errors.append("msg_id must be a UUID string")
    if not is_uuid(data.get("session_id")):
        errors.append("session_id must be a UUID string")
    if data.get("phase") != PHASE:
        errors.append("top-level phase must be 'analyze'")
    if not is_iso_timestamp(data.get("timestamp")):
        errors.append("timestamp must be an ISO 8601 string")
    if data.get("type") != "phase_complete":
        errors.append("type must be 'phase_complete'")

    payload = data.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        return errors, None

    if payload.get("phase") != data.get("phase"):
        errors.append("payload.phase must match top-level phase")

    return errors, payload


def validate_phase_complete(
    data: dict[str, Any],
    *,
    compare_manifest_path: str | None = None,
    artifact_root: str | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    envelope_errors, payload = validate_envelope(data)
    errors.extend(envelope_errors)
    if payload is None:
        return errors, warnings

    result = payload.get("result")
    if result not in PHASE_COMPLETE_RESULTS:
        errors.append(f"phase_complete.result invalid value '{result}', valid values: {PHASE_COMPLETE_RESULTS}")

    if not payload.get("summary"):
        errors.append("phase_complete.summary is required")

    next_phase = payload.get("next_phase")
    if result == "success" and next_phase != NEXT_PHASE_ON_SUCCESS:
        errors.append("phase_complete.next_phase must be 'select-hw' when analyze succeeds")
    if result in {"partial", "failed"} and next_phase is not None:
        errors.append("phase_complete.next_phase must be null when result is partial or failed")

    errors.extend(validate_checkpoint(payload.get("checkpoint"), required=(result == "partial")))

    manifest_content = payload.get("manifest_content")
    normalized_manifest_content: dict[str, Any] | None = None
    if not isinstance(manifest_content, dict):
        errors.append("phase_complete.manifest_content must be an object")
    else:
        manifest_copy = copy.deepcopy(manifest_content)
        manifest_errors = validate_and_fill(manifest_copy)
        if manifest_errors:
            errors.extend(f"manifest_content: {item}" for item in manifest_errors)
        else:
            semantic_errors, semantic_warnings = validate_semantics(manifest_copy)
            errors.extend(f"manifest_content: {item}" for item in semantic_errors)
            warnings.extend(f"manifest_content: {item}" for item in semantic_warnings)
            normalized_manifest_content = normalize_manifest_for_compare(manifest_copy)

    artifact_errors, artifact_warnings = validate_artifacts(payload.get("artifacts"), artifact_root)
    errors.extend(artifact_errors)
    warnings.extend(artifact_warnings)

    if not isinstance(payload.get("warnings"), list):
        errors.append("phase_complete.warnings must be an array")
    if not isinstance(payload.get("errors"), list):
        errors.append("phase_complete.errors must be an array")
    errors.extend(validate_structured_errors(payload.get("structured_errors")))

    if compare_manifest_path and normalized_manifest_content is not None:
        try:
            with open(compare_manifest_path, "r", encoding="utf-8") as f:
                compare_manifest = json.load(f)
        except Exception as exc:
            errors.append(f"compare manifest load failed: {exc}")
        else:
            compare_copy = copy.deepcopy(compare_manifest)
            compare_errors = validate_and_fill(compare_copy)
            if compare_errors:
                errors.extend(f"compare_manifest: {item}" for item in compare_errors)
            else:
                compare_normalized = normalize_manifest_for_compare(compare_copy)
                if compare_normalized != normalized_manifest_content:
                    errors.append("phase_complete.manifest_content core fields do not match compare manifest")

    return errors, warnings


def maybe_write_manifest(manifest: dict[str, Any], write_path: str | None, project_dir: str | None) -> str | None:
    target = write_path
    if not target and project_dir:
        target = os.path.join(project_dir, "project-manifest.json")
    if not target:
        return None

    directory = os.path.dirname(target)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return target


def output_and_exit(payload: dict[str, Any], code: int) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(code)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate upy-analyze V0 manifest or phase_complete")
    parser.add_argument("--input", default=None, help="input JSON file path")
    parser.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    parser.add_argument("--write-path", default=None, help="optional normalized manifest output path")
    parser.add_argument("--project-dir", default=None, help="legacy output dir; writes project-manifest.json when --write-path is absent")
    parser.add_argument("--validate-phase-complete", action="store_true", help="validate full phase_complete envelope")
    parser.add_argument("--compare-manifest", default=None, help="manifest file to compare against payload.manifest_content core fields")
    parser.add_argument("--artifact-root", default=None, help="root dir used to verify file_list artifact paths")
    args = parser.parse_args()

    try:
        data = load_input(args)
    except Exception as exc:
        output_and_exit(
            {
                "status": "fail",
                "errors": [f"input load failed: {exc}"],
                "warnings": [],
                "manifest": None,
                "written_path": None,
            },
            1,
        )

    if args.validate_phase_complete:
        errors, warnings = validate_phase_complete(
            data,
            compare_manifest_path=args.compare_manifest,
            artifact_root=args.artifact_root,
        )
        output_and_exit(
            {
                "status": "fail" if errors else "ok",
                "errors": errors,
                "warnings": warnings,
            },
            1 if errors else 0,
        )

    errors = validate_and_fill(data)
    if errors:
        output_and_exit(
            {
                "status": "fail",
                "errors": errors,
                "warnings": [],
                "manifest": None,
                "written_path": None,
            },
            1,
        )

    semantic_errors, semantic_warnings = validate_semantics(data)
    if semantic_errors:
        output_and_exit(
            {
                "status": "fail",
                "errors": semantic_errors,
                "warnings": semantic_warnings,
                "manifest": None,
                "written_path": None,
            },
            1,
        )

    manifest = build_manifest(data)

    try:
        written_path = maybe_write_manifest(manifest, args.write_path, args.project_dir)
    except Exception as exc:
        output_and_exit(
            {
                "status": "fail",
                "errors": [f"write failed: {exc}"],
                "warnings": semantic_warnings,
                "manifest": manifest,
                "written_path": None,
            },
            1,
        )

    output_and_exit(
        {
            "status": "ok",
            "errors": [],
            "warnings": semantic_warnings,
            "manifest": manifest,
            "written_path": written_path,
        },
        0,
    )


if __name__ == "__main__":
    main()
