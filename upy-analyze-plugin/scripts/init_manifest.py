#!/usr/bin/env python3
"""
upy-analyze-plugin 的 manifest 校验与规范化脚本。
"""

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional


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
    "serial", "display_oled", "display_lcd", "display_eink",
    "buzzer", "led", "led_rgb", "cloud_mqtt", "cloud_http",
    "local_file", "relay", "motor", "servo",
]

VALID_SPECIAL_REQS = [
    "watchdog", "ota_update", "deep_sleep", "encryption",
    "button_control", "voice_control", "battery_monitor", "error_led", "none",
]

VALID_DEVICE_INTERFACES = [
    "I2C", "SPI", "UART", "GPIO", "PWM", "ADC", "I2S", "1-Wire", "CAN", "USB", "WiFi", "BLE",
]

VALID_DRIVER_SOURCES = [
    "builtin_runtime", "micropython_lib", "upypi", "awesome-micropython",
    "github", "local", "cold-driver", "none",
]
VALID_DEVICE_SOURCES = ["user_specified", "system_recommended"]
REAL_DRIVER_SOURCES = ["micropython_lib", "upypi", "awesome-micropython", "github", "local"]
READY_DRIVER_SEARCH_SOURCES = {"upypi", "awesome-micropython", "github"}
VALID_DRIVER_SEARCH_PROVIDERS = [
    "upy-pkg-guide",
    "pkg_guide_adapter",
    "builtin_runtime_classifier",
    "micropython_lib_classifier",
]
VALID_DRIVER_SEARCH_MODES = ["real", "mock"]
PHASE_COMPLETE_RESULTS = ["success", "failed", "partial"]
ARTIFACT_TYPES = ["table", "file_tree", "markdown", "html", "code_diff", "file_list"]
NEXT_PHASE_ON_SUCCESS = "select-hw"
NEXT_SKILL_ON_SUCCESS = "/upy-select-hw-plugin"

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
API_REFERENCE_FIELDS = ("api_ref", "api_reference", "api_summary")
API_EVIDENCE_FIELDS = (
    "docs_url",
    "doc_url",
    "documentation_url",
    "readme_url",
    "readme",
    "examples_url",
    "example_url",
    "examples",
    "source_url",
)

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


def has_nonempty_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(str(key).strip() and has_nonempty_value(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_nonempty_value(item) for item in value)
    return value is not None


def has_structured_api_reference(driver: dict[str, Any]) -> bool:
    for field in API_REFERENCE_FIELDS:
        value = driver.get(field)
        if isinstance(value, (dict, list)) and has_nonempty_value(value):
            return True
    for container_name in ("metadata", "package_metadata", "package_info"):
        container = driver.get(container_name)
        if isinstance(container, dict) and has_structured_api_reference(container):
            return True
    return False


def has_api_reference(driver: dict[str, Any]) -> bool:
    if has_structured_api_reference(driver):
        return True
    for field in API_EVIDENCE_FIELDS:
        if has_nonempty_value(driver.get(field)):
            return True
    for container_name in ("metadata", "package_metadata", "package_info"):
        container = driver.get(container_name)
        if isinstance(container, dict) and has_api_reference(container):
            return True
    return False


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

    if "experience" in requirements and requirements.get("experience") is None:
        requirements["experience"] = REQUIREMENTS_DEFAULTS["experience"]

    if "output" in requirements and requirements.get("output") is None:
        requirements["output"] = REQUIREMENTS_DEFAULTS["output"]

    for field, default in REQUIREMENTS_DEFAULTS.items():
        if field not in requirements or requirements[field] is None:
            requirements[field] = default
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

        if device.get("interface") and device["interface"] not in VALID_DEVICE_INTERFACES:
            errors.append(
                f"{prefix}.interface invalid value '{device['interface']}', valid values: {VALID_DEVICE_INTERFACES}"
            )

        if device.get("source") and device["source"] not in VALID_DEVICE_SOURCES:
            errors.append(
                f"{prefix}.source invalid value '{device['source']}', valid values: {VALID_DEVICE_SOURCES}"
            )

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
                if source == "micropython_lib" and not has_api_reference(driver):
                    errors.append(
                        f"{prefix}.driver.api_ref/readme_url/examples/docs_url is required when driver.source=micropython_lib"
                    )

            search_provider = driver.get("search_provider")
            if search_provider is not None and search_provider not in VALID_DRIVER_SEARCH_PROVIDERS:
                errors.append(
                    f"{prefix}.driver.search_provider invalid value '{search_provider}', "
                    f"valid values: {VALID_DRIVER_SEARCH_PROVIDERS}"
                )

            search_mode = driver.get("search_mode")
            if search_mode is not None and search_mode not in VALID_DRIVER_SEARCH_MODES:
                errors.append(
                    f"{prefix}.driver.search_mode invalid value '{search_mode}', "
                    f"valid values: {VALID_DRIVER_SEARCH_MODES}"
                )

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
        search_provider = driver.get("search_provider")
        search_mode = driver.get("search_mode")

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

        if driver_source == "builtin_runtime":
            if search_provider and search_provider != "builtin_runtime_classifier":
                errors.append(
                    f"{prefix}.driver.search_provider must be builtin_runtime_classifier when driver.source=builtin_runtime"
                )
            if driver.get("search_required") is not False:
                errors.append(f"{prefix}.driver.search_required must be false when driver.source=builtin_runtime")

        if driver_source == "micropython_lib":
            if search_provider not in {"micropython_lib_classifier", "upy-pkg-guide"}:
                errors.append(
                    f"{prefix}.driver.search_provider must be micropython_lib_classifier or upy-pkg-guide when driver.source=micropython_lib"
                )

        if driver_source in READY_DRIVER_SEARCH_SOURCES:
            if not search_provider:
                errors.append(f"{prefix}.driver.search_provider is required when driver.source={driver_source}")
            elif search_provider not in {"upy-pkg-guide", "pkg_guide_adapter"}:
                errors.append(
                    f"{prefix}.driver.search_provider must be upy-pkg-guide or pkg_guide_adapter when driver.source={driver_source}"
                )
            if search_provider == "pkg_guide_adapter":
                if driver.get("mock") is not True:
                    errors.append(f"{prefix}.driver.mock must be true when search_provider=pkg_guide_adapter")
                if search_mode != "mock":
                    errors.append(f"{prefix}.driver.search_mode must be mock when search_provider=pkg_guide_adapter")
            elif search_provider == "upy-pkg-guide" and search_mode == "mock":
                errors.append(f"{prefix}.driver.search_mode cannot be mock when search_provider=upy-pkg-guide")

        if driver_source in {"none", "cold-driver"} and not builtin_expected:
            if not search_provider:
                errors.append(f"{prefix}.driver.search_provider is required when driver.source={driver_source}")
            elif search_provider not in {"upy-pkg-guide", "pkg_guide_adapter"}:
                errors.append(
                    f"{prefix}.driver.search_provider must be upy-pkg-guide or pkg_guide_adapter when driver.source={driver_source}"
                )
            if search_provider == "pkg_guide_adapter":
                if driver.get("mock") is not True:
                    errors.append(f"{prefix}.driver.mock must be true when search_provider=pkg_guide_adapter")
                if search_mode != "mock":
                    errors.append(f"{prefix}.driver.search_mode must be mock when search_provider=pkg_guide_adapter")

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
        if output == ["serial"] or output == ["serial"]:
            warnings.append("description suggests voice interaction, but requirements.output only contains serial; record audio/cloud limitations in warnings or notes")

    if any(keyword in description for keyword in ["云端", "联网", "llm", "api"]):
        if requirements.get("network") != "wifi":
            warnings.append("description suggests cloud/network use, but requirements.network is not wifi")

    if any(keyword in description for keyword in ["气体", "gas", "co2", "空气"]):
        if not any("gas" in item or "air" in item for item in device_types + device_names):
            warnings.append("description suggests gas/air sensing, but no gas/air-related device was found")

    return errors, warnings


def phase_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Accept either a full message envelope or a bare phase_complete payload."""
    if data.get("type") == "phase_complete":
        payload = data.get("payload")
        if isinstance(payload, dict):
            return payload
    return data


def validate_artifacts(artifacts: Any) -> list[str]:
    errors: list[str] = []

    if not isinstance(artifacts, list):
        errors.append("phase_complete.artifacts must be an array")
        return errors

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
                    if not isinstance(file_item, dict) or not file_item.get("path"):
                        errors.append(f"{prefix}.files[{file_index}] must be an object with path")
        elif artifact_type == "markdown":
            if not isinstance(artifact.get("content"), str):
                errors.append(f"{prefix}.content must be a string for markdown artifacts")

    return errors


def validate_phase_complete(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    payload = phase_payload(data)

    if payload.get("phase") != "analyze":
        errors.append("phase_complete.phase must be 'analyze'")

    result = payload.get("result")
    if result not in PHASE_COMPLETE_RESULTS:
        errors.append(f"phase_complete.result invalid value '{result}', valid values: {PHASE_COMPLETE_RESULTS}")

    if not payload.get("summary"):
        errors.append("phase_complete.summary is required")

    next_phase = payload.get("next_phase")
    if result == "success" and next_phase != NEXT_PHASE_ON_SUCCESS:
        errors.append("phase_complete.next_phase must be 'select-hw' when analyze succeeds")
    if result != "success" and next_phase is not None:
        warnings.append("phase_complete.next_phase is normally null when result is not success")

    next_skill = payload.get("next_skill")
    if result == "success" and next_skill != NEXT_SKILL_ON_SUCCESS:
        errors.append("phase_complete.next_skill must be '/upy-select-hw-plugin' when analyze succeeds")
    if result != "success" and next_skill is not None:
        warnings.append("phase_complete.next_skill is normally null when result is not success")

    manifest_content = payload.get("manifest_content")
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

    errors.extend(validate_artifacts(payload.get("artifacts")))

    if not isinstance(payload.get("warnings"), list):
        errors.append("phase_complete.warnings must be an array")
    if not isinstance(payload.get("errors"), list):
        errors.append("phase_complete.errors must be an array")

    return errors, warnings


def build_manifest(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": "1.0",
        "phase": "analyze",
        "created_at": now,
        "updated_at": now,
        "project_name": data["project_name"],
        "requirements": data["requirements"],
        "devices": data["devices"],
        "final_status": "pending",
    }


def maybe_write_manifest(manifest: dict[str, Any], write_path: Optional[str]) -> Optional[str]:
    if not write_path:
        return None
    os.makedirs(os.path.dirname(write_path), exist_ok=True)
    with open(write_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return write_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and normalize analyze manifest draft")
    parser.add_argument("--input", default=None, help="input JSON file path")
    parser.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    parser.add_argument("--write-path", default=None, help="optional output file path")
    parser.add_argument("--validate-phase-complete", action="store_true", help="validate a phase_complete payload or message")
    args = parser.parse_args()

    try:
        data = load_input(args)
    except Exception as exc:
        json.dump(
            {
                "status": "fail",
                "errors": [f"input load failed: {exc}"],
                "manifest": None,
                "written_path": None,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.exit(1)

    if args.validate_phase_complete:
        errors, warnings = validate_phase_complete(data)
        json.dump(
            {
                "status": "fail" if errors else "ok",
                "errors": errors,
                "warnings": warnings,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.exit(1 if errors else 0)

    errors = validate_and_fill(data)
    if errors:
        json.dump(
            {
                "status": "fail",
                "errors": errors,
                "manifest": None,
                "written_path": None,
                "warnings": [],
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.exit(1)

    semantic_errors, semantic_warnings = validate_semantics(data)
    if semantic_errors:
        json.dump(
            {
                "status": "fail",
                "errors": semantic_errors,
                "manifest": None,
                "written_path": None,
                "warnings": semantic_warnings,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.exit(1)

    manifest = build_manifest(data)

    try:
        written_path = maybe_write_manifest(manifest, args.write_path)
    except Exception as exc:
        json.dump(
            {
                "status": "fail",
                "errors": [f"write failed: {exc}"],
                "manifest": manifest,
                "written_path": None,
                "warnings": semantic_warnings,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.exit(1)

    json.dump(
        {
            "status": "ok",
            "errors": [],
            "manifest": manifest,
            "written_path": written_path,
            "warnings": semantic_warnings,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    main()
