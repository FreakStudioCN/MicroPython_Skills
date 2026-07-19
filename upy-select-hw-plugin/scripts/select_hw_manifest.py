#!/usr/bin/env python3
"""
Validate and normalize upy-select-hw-plugin draft manifests.

This script is a validator/normalizer. It does not write project files unless
--write-path is explicitly provided.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "1.0"
PHASE = "select-hw"
NEXT_PHASE = "upy-flash-mpy-firmware-plugin"
SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parent
DEFAULT_BOARD_ROOT = REPO_ROOT / "upy-analyze-plugin" / "boards"

MESSAGE_TYPES = {
    "start_phase",
    "status_update",
    "approval_request",
    "approval_response",
    "script_run",
    "script_result",
    "file_operation",
    "file_result",
    "device_command",
    "device_result",
    "phase_complete",
}

RESULTS = {"success", "failed", "partial"}
ARTIFACT_TYPES = {"table", "file_tree", "markdown", "html", "code_diff", "file_list"}
FILE_STATUSES = {"created", "updated", "unchanged", "skipped", "error"}
ARTIFACT_ROOT_MODES = {"cwd", "session_root"}
STRUCTURED_SEVERITIES = {"info", "warning", "error", "fatal"}
STRUCTURED_CODES = {
    "invalid_upstream_manifest",
    "missing_required_field",
    "invalid_enum",
    "board_not_found",
    "firmware_unknown",
    "missing_pin_layout",
    "pin_conflict",
    "i2c_address_conflict",
    "permission_denied",
    "script_failed",
    "timeout",
    "phase_complete_invalid",
    "board_definition_not_found",
    "board_definition_invalid",
    "restricted_gpio_used",
    "default_bus_pin_deviation",
    "pin_review_required",
    "pin_review_rejected",
    "pin_decision_invalid",
    "onboard_peripheral_pin_used",
    "onboard_peripheral_reused",
    "user_wiring_invalid",
    "occupied_pin_conflict",
    "artifact_missing",
    "absolute_path_in_artifact",
}
FLASH_TOOLS = {"esptool.py", "uf2-drag-drop", "dfu-util", "teensy-loader", "unknown"}
PIN_TYPES = {
    "power_3v3",
    "power_5v",
    "gnd",
    "i2c_data",
    "i2c_clock",
    "spi_mosi",
    "spi_miso",
    "spi_sck",
    "spi_cs",
    "uart_tx",
    "uart_rx",
    "gpio_out",
    "gpio_in",
    "gpio_in_pullup",
    "adc",
    "pwm",
    "i2s_bck",
    "i2s_ws",
    "i2s_data_in",
    "i2s_data_out",
    "wifi_internal",
    "reserved",
}
PIN_SOURCES = {
    "default_bus",
    "auto_assigned",
    "user_wiring",
    "onboard_peripheral",
    "power",
}
PIN_DECISION_TYPES = {
    "use_default_bus",
    "auto_assign_free_gpio",
    "remap_default_conflict",
    "avoid_restricted_gpio",
    "avoid_onboard_occupied",
    "reuse_onboard_peripheral",
    "fixed_power_tie",
    "user_wiring",
    "manual_review_required",
}
PIN_DECISION_SOURCES = {
    "board_default",
    "auto_assigned",
    "user_wiring",
    "onboard_peripheral",
    "fixed_power",
}
PIN_DEVIATION_REASON_CODES = {
    "restricted_gpio",
    "default_bus_conflict",
    "onboard_occupied",
    "not_exposed",
    "user_requested",
    "fixed_power_tie",
    "insufficient_board_data",
}
PIN_DEVIATION_VALIDATOR_ACTIONS = {"error", "warning", "manual_review"}
PIN_REVIEW_SOURCES = {"approval_response", "plugin_ui_confirmed", "user_confirmed"}
PIN_REVIEW_MAX_PHASE_AGE = timedelta(hours=2)

VALID_DRIVER_SOURCES = {
    "builtin_runtime",
    "micropython_lib",
    "upypi",
    "awesome-micropython",
    "github",
    "local",
    "cold-driver",
    "none",
}
DRIVER_STATUS_COLD_REQUIRED = "cold_driver_required"
DRIVER_STATUS_READY = "ready"
VALID_DRIVER_STATUSES = {
    DRIVER_STATUS_COLD_REQUIRED,
    DRIVER_STATUS_READY,
    "pending_validation",
    "failed",
    "unverified",
}
VALID_DEVICE_INTERFACES = {
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
}
PINOUT_SYSTEM_DEVICES = {
    "power",
    "gnd",
    "ground",
    "3v3",
    "5v",
    "vcc",
    "vdd",
    "usb",
    "battery",
    "board",
    "mcu",
    "mainboard",
    "主控板",
    "开发板",
    "电源",
    "地",
}
BOM_SUPPORT_ITEM_KEYWORDS = {
    "wire",
    "jumper",
    "cable",
    "breadboard",
    "resistor",
    "capacitor",
    "header",
    "connector",
    "screw",
    "case",
    "enclosure",
    "battery holder",
    "usb cable",
    "power supply",
    "voltage regulator",
    "杜邦线",
    "导线",
    "线缆",
    "面包板",
    "电阻",
    "电容",
    "排针",
    "接线端子",
    "螺丝",
    "外壳",
    "电池盒",
    "usb线",
    "usb 线",
    "电源模块",
    "稳压模块",
    "转接板",
}


def normalize_driver_status(driver: dict[str, Any], prefix: str, warnings: list[str], errors: list[str]) -> None:
    source = driver.get("source")
    status = driver.get("status")

    if status not in (None, "") and status not in VALID_DRIVER_STATUSES:
        if source == "cold-driver":
            warnings.append(
                f"{prefix}.driver.status invalid value '{status}' for source='cold-driver'; "
                f"normalized to '{DRIVER_STATUS_COLD_REQUIRED}'"
            )
            driver["status"] = DRIVER_STATUS_COLD_REQUIRED
        else:
            errors.append(
                f"{prefix}.driver.status invalid value '{status}', valid values: {sorted(VALID_DRIVER_STATUSES)}"
            )
        return

    if source != "cold-driver":
        if status == DRIVER_STATUS_COLD_REQUIRED:
            warnings.append(
                f"{prefix}.driver.status is '{DRIVER_STATUS_COLD_REQUIRED}' but source is '{source}'; keeping source unchanged"
            )
        return

    if status in (None, ""):
        driver["status"] = DRIVER_STATUS_COLD_REQUIRED
        warnings.append(f"{prefix} uses cold-driver; downstream gen-driver is required")
        return

    if status == DRIVER_STATUS_READY:
        if not driver.get("path") or not driver.get("hardware_marker"):
            driver["status"] = DRIVER_STATUS_COLD_REQUIRED
            warnings.append(
                f"{prefix}.driver.status is ready but hardware proof is missing; "
                f"normalized to '{DRIVER_STATUS_COLD_REQUIRED}'"
            )
        else:
            warnings.append(f"{prefix}.driver.source remains cold-driver as provenance; preserving hardware-ready status")
        return

    warnings.append(f"{prefix} uses cold-driver; preserving durable gate status '{status}'")


BOM_CONTROLLER_KEYWORDS = {
    "board",
    "devkit",
    "development board",
    "mcu",
    "controller",
    "主控",
    "开发板",
    "控制板",
}
BOM_FUNCTIONAL_HARDWARE_KEYWORDS = {
    "sensor",
    "display",
    "oled",
    "lcd",
    "eink",
    "microphone",
    "mic",
    "speaker",
    "amplifier",
    "amp",
    "camera",
    "relay",
    "motor",
    "servo",
    "buzzer",
    "led",
    "neopixel",
    "ws2812",
    "gps",
    "imu",
    "accelerometer",
    "gyro",
    "touch",
    "button",
    "传感器",
    "显示",
    "屏",
    "麦克风",
    "咪头",
    "喇叭",
    "功放",
    "摄像头",
    "继电器",
    "电机",
    "舵机",
    "蜂鸣器",
    "灯",
    "按键",
    "触摸",
}
BOM_DEVICE_MATCH_FIELDS = (
    "device",
    "device_name",
    "source_device",
    "upstream_device",
    "for_device",
    "name",
    "model",
    "selected_model",
    "module",
    "part",
)
BOM_LINK_TEMPLATE_FIELDS = (
    "product_url",
    "shop_url",
    "datasheet_url",
    "supplier",
    "sku",
)
BOM_LINK_INDEX_TEMPLATE = SKILL_DIR / "references" / "bom_item_link_index.template.json"
ONBOARD_DRIVER_MAP_PATH = SKILL_DIR / "references" / "onboard_driver_map.json"

ONBOARD_DRIVERLESS_TYPES = {
    "battery_connector",
    "psram",
    "usb_uart",
}
ONBOARD_BUILTIN_TYPES = {
    "button": "machine.Pin",
    "led": "machine.Pin",
    "rgb_led": "neopixel",
    "touch": "machine.TouchPad",
    "wifi_module": "network",
}
ONBOARD_DRIVER_REQUIRED_TYPES = {
    "audio_codec",
    "camera",
    "display",
    "environment_sensor",
    "ethernet",
    "imu",
    "microphone",
    "power_mgmt",
    "radio_lora",
    "secure_element",
    "speaker",
    "storage",
}
ONBOARD_TYPE_INTERFACE_DEFAULTS = {
    "button": "GPIO",
    "led": "GPIO",
    "rgb_led": "GPIO",
    "touch": "GPIO",
    "display": "I2C",
    "environment_sensor": "I2C",
    "imu": "I2C",
    "power_mgmt": "I2C",
    "secure_element": "I2C",
    "ethernet": "SPI",
    "radio_lora": "SPI",
    "storage": "SPI",
    "microphone": "I2S",
    "speaker": "I2S",
    "audio_codec": "I2S",
}
ONBOARD_REQUIREMENT_KEYWORDS = {
    "display": {"display", "screen", "oled", "lcd", "eink", "epaper", "显示", "屏幕", "墨水屏"},
    "imu": {"imu", "accelerometer", "gyro", "motion", "gesture", "姿态", "加速度", "陀螺"},
    "microphone": {"microphone", "mic", "voice", "audio input", "麦克风", "语音", "录音"},
    "speaker": {"speaker", "audio output", "play audio", "喇叭", "扬声器", "播放声音"},
    "camera": {"camera", "vision", "image", "摄像头", "相机", "图像"},
    "storage": {"sd", "sdcard", "storage", "log file", "local_file", "存储", "日志", "文件"},
    "radio_lora": {"lora"},
    "ethernet": {"ethernet", "以太网"},
    "power_mgmt": {"battery", "battery_monitor", "fuel gauge", "电池", "电量"},
    "button": {"button", "key", "按键", "按钮"},
    "led": {"led", "light", "灯"},
    "rgb_led": {"rgb", "neopixel", "ws2812", "彩灯"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{field} must be a non-empty ISO-8601 timestamp")
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        errors.append(f"{field} must be a valid ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include timezone, preferably Z")
        return None
    return parsed.astimezone(timezone.utc)


def load_input(args: argparse.Namespace) -> dict[str, Any]:
    if args.stdin:
        return json.load(sys.stdin)
    if args.input:
        with open(args.input, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    raise ValueError("must provide --stdin or --input")


def emit_json(payload: dict[str, Any], exit_code: int) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(exit_code)


def require_object(value: Any, field: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return None
    return value


def require_list(value: Any, field: str, errors: list[str]) -> list[Any] | None:
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return None
    return value


def normalized_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    for char in (" ", "-", "_", "/", "\\", "(", ")", "[", "]"):
        text = text.replace(char, "")
    return text


def text_contains_any(value: str, keywords: set[str]) -> bool:
    lowered = value.lower()
    compact = normalized_label(value)
    return any(keyword.lower() in lowered or normalized_label(keyword) in compact for keyword in keywords)


def device_match_tokens(devices: Any) -> tuple[set[str], list[str]]:
    tokens: set[str] = set()
    display_names: list[str] = []
    if not isinstance(devices, list):
        return tokens, display_names
    for device in devices:
        if not isinstance(device, dict):
            continue
        name = device.get("name")
        if name:
            display_names.append(str(name))
        for field in ("name", "model", "selected_model"):
            value = device.get(field)
            if value:
                tokens.add(normalized_label(value))
        aliases = device.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if alias:
                    tokens.add(normalized_label(alias))
    return tokens, display_names


def matches_device_token(value: Any, tokens: set[str]) -> bool:
    token = normalized_label(value)
    return bool(token and token in tokens)


def is_system_pinout_device(value: Any) -> bool:
    return normalized_label(value) in {normalized_label(item) for item in PINOUT_SYSTEM_DEVICES}


def bom_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("name", "model", "category", "type", "notes"):
        value = item.get(field)
        if value not in (None, ""):
            parts.append(str(value))
    return " ".join(parts)


def bom_matches_upstream_device(item: dict[str, Any], tokens: set[str]) -> bool:
    for field in BOM_DEVICE_MATCH_FIELDS:
        value = item.get(field)
        if matches_device_token(value, tokens):
            return True
    return False


def bom_is_support_item(item: dict[str, Any]) -> bool:
    return text_contains_any(bom_text(item), BOM_SUPPORT_ITEM_KEYWORDS)


def bom_is_controller(item: dict[str, Any], selected_board: Any, mcu: Any) -> bool:
    text = bom_text(item)
    if text_contains_any(text, BOM_CONTROLLER_KEYWORDS):
        return True
    selected_values: list[Any] = []
    if isinstance(selected_board, dict):
        selected_values.extend(
            selected_board.get(field) for field in ("id", "display_name", "mcu", "chip_family")
        )
        firmware = selected_board.get("firmware")
        if isinstance(firmware, dict):
            selected_values.extend(firmware.get(field) for field in ("board_name", "port"))
    if isinstance(mcu, dict):
        selected_values.extend(mcu.get(field) for field in ("model", "board_id", "display_name", "chip_family"))
    item_values = [item.get(field) for field in ("name", "model", "device", "part")]
    selected_tokens = {normalized_label(value) for value in selected_values if value not in (None, "")}
    return any(normalized_label(value) in selected_tokens for value in item_values if value not in (None, ""))


def bom_is_functional_hardware(item: dict[str, Any]) -> bool:
    return text_contains_any(bom_text(item), BOM_FUNCTIONAL_HARDWARE_KEYWORDS)


def load_bom_link_fields() -> tuple[str, ...]:
    try:
        with open(BOM_LINK_INDEX_TEMPLATE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return BOM_LINK_TEMPLATE_FIELDS
    fields = data.get("link_fields") if isinstance(data, dict) else None
    if not isinstance(fields, list):
        return BOM_LINK_TEMPLATE_FIELDS
    normalized = tuple(field for field in fields if isinstance(field, str) and field)
    return normalized or BOM_LINK_TEMPLATE_FIELDS


def normalize_bom_items(bom: Any) -> list[Any]:
    if not isinstance(bom, list):
        return []
    link_fields = load_bom_link_fields()
    normalized: list[Any] = []
    for raw in bom:
        if not isinstance(raw, dict):
            normalized.append(copy.deepcopy(raw))
            continue
        item = copy.deepcopy(raw)
        for field in link_fields:
            item.setdefault(field, "")
        normalized.append(item)
    return normalized


def load_onboard_driver_map() -> dict[str, Any]:
    try:
        with open(ONBOARD_DRIVER_MAP_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def map_lookup_by_model(driver_map: dict[str, Any], model: Any) -> dict[str, Any]:
    model_key = normalized_label(model)
    if not model_key:
        return {}
    raw_models = driver_map.get("models")
    if not isinstance(raw_models, dict):
        return {}
    for key, value in raw_models.items():
        if normalized_label(key) == model_key and isinstance(value, dict):
            return value
    return {}


def infer_onboard_interface(peripheral: dict[str, Any], mapping: dict[str, Any] | None = None) -> str | None:
    if isinstance(mapping, dict):
        mapped_interface = mapping.get("interface")
        if mapped_interface in VALID_DEVICE_INTERFACES:
            return str(mapped_interface)

    interface = peripheral.get("interface")
    if interface in VALID_DEVICE_INTERFACES:
        return str(interface)

    pins = peripheral.get("occupied_pins")
    pin_names = {normalized_label(name) for name in pins} if isinstance(pins, dict) else set()
    if pin_names.intersection({"sda", "scl", "i2cdata", "i2cclock"}):
        return "I2C"
    if pin_names.intersection({"mosi", "miso", "sck", "clk", "cs", "spi"}):
        return "SPI"
    if pin_names.intersection({"tx", "rx", "uarttx", "uartrx"}):
        return "UART"
    if pin_names.intersection({"bck", "ws", "din", "dout", "data", "i2sbck", "i2sws"}):
        return "I2S"
    if pins:
        return "GPIO"

    ptype = str(peripheral.get("type") or "").strip().lower()
    return ONBOARD_TYPE_INTERFACE_DEFAULTS.get(ptype)


def onboard_builtin_driver(module: str) -> dict[str, Any]:
    return {
        "source": "builtin_runtime",
        "module": module,
        "search_provider": "builtin_runtime_classifier",
        "search_required": False,
    }


def onboard_cold_driver(peripheral: dict[str, Any]) -> dict[str, Any]:
    model = str(peripheral.get("model") or peripheral.get("name") or peripheral.get("type") or "onboard_peripheral")
    driver_id = normalized_label(model).replace("-", "_") or "onboard_peripheral"
    return {
        "source": "cold-driver",
        "status": DRIVER_STATUS_COLD_REQUIRED,
        "driver_id": driver_id,
        "query": f"{model} MicroPython driver",
        "notes": "No verified onboard driver mapping is available; run upy-gen-driver-plugin before generate.",
    }


def onboard_driver_for(peripheral: dict[str, Any], driver_map: dict[str, Any]) -> dict[str, Any]:
    existing = peripheral.get("driver")
    if isinstance(existing, dict) and existing.get("source"):
        return copy.deepcopy(existing)

    mapping = map_lookup_by_model(driver_map, peripheral.get("model"))
    mapped_driver = mapping.get("driver") if isinstance(mapping, dict) else None
    if isinstance(mapped_driver, dict) and mapped_driver.get("source"):
        return copy.deepcopy(mapped_driver)

    ptype = str(peripheral.get("type") or "").strip().lower()
    if ptype in ONBOARD_BUILTIN_TYPES:
        return onboard_builtin_driver(ONBOARD_BUILTIN_TYPES[ptype])
    if ptype in ONBOARD_DRIVERLESS_TYPES:
        return {"source": "none"}
    if ptype in ONBOARD_DRIVER_REQUIRED_TYPES:
        return onboard_cold_driver(peripheral)
    return {"source": "none"}


def onboard_i2c_addresses(peripheral: dict[str, Any], mapping: dict[str, Any]) -> list[str]:
    candidates = []
    for key in ("i2c_addr", "i2c_addrs", "addresses", "known_addresses"):
        value = peripheral.get(key)
        if value is None and isinstance(mapping, dict):
            value = mapping.get(key)
        if isinstance(value, list):
            candidates.extend(str(item) for item in value)
        elif isinstance(value, str):
            candidates.append(value)
    normalized: list[str] = []
    for value in candidates:
        text = value.strip()
        if not text:
            continue
        if text.lower().startswith("0x") and len(text) == 4:
            normalized.append("0x" + text[2:].upper())
    return sorted(set(normalized))


def peripheral_ref(board: dict[str, Any], peripheral: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "board_id": board.get("id") or board.get("board_id"),
        "index": index,
        "name": peripheral.get("name", ""),
        "type": peripheral.get("type", ""),
        "model": peripheral.get("model", ""),
        "occupied_pins": copy.deepcopy(peripheral.get("occupied_pins", {})),
        "always_used": bool(peripheral.get("always_used")),
        "verification": peripheral.get("verification", ""),
        "pin_evidence": peripheral.get("pin_evidence", ""),
    }


def append_note(existing: Any, note: str) -> str:
    if isinstance(existing, str) and existing.strip():
        if note in existing:
            return existing
        return f"{existing.rstrip()} {note}"
    return note


def device_driver_is_replaceable(driver: Any) -> bool:
    if not isinstance(driver, dict):
        return True
    source = str(driver.get("source") or "").strip()
    status = str(driver.get("status") or driver.get("driver_status") or "").strip()
    return source in {"", "none", "manual", "cold-driver"} or status == DRIVER_STATUS_COLD_REQUIRED


def device_matches_peripheral(device: dict[str, Any], peripheral: dict[str, Any]) -> bool:
    device_tokens = set()
    for field in ("name", "model", "selected_model", "type"):
        value = device.get(field)
        if value:
            device_tokens.add(normalized_label(value))
    aliases = device.get("aliases")
    if isinstance(aliases, list):
        device_tokens.update(normalized_label(value) for value in aliases if value)

    peripheral_tokens = set()
    for field in ("name", "model", "type"):
        value = peripheral.get(field)
        if value:
            peripheral_tokens.add(normalized_label(value))

    if device_tokens.intersection(peripheral_tokens):
        return True

    device_type = normalized_label(device.get("type"))
    peripheral_type = normalized_label(peripheral.get("type"))
    if device_type and peripheral_type and device_type == peripheral_type:
        return True
    if device_type == "led" and peripheral_type == "rgbled":
        return True
    if device_type in {"speaker", "microphone"} and peripheral_type == "audiocodec":
        return True
    return False


def enrich_device_from_peripheral(
    device: dict[str, Any],
    board: dict[str, Any],
    peripheral: dict[str, Any],
    index: int,
    driver_map: dict[str, Any],
) -> bool:
    changed = False
    if device.get("physical_source") != "board_onboard":
        device["physical_source"] = "board_onboard"
        changed = True
    ref = peripheral_ref(board, peripheral, index)
    if device.get("onboard_peripheral_ref") != ref:
        device["onboard_peripheral_ref"] = ref
        changed = True

    model = peripheral.get("model")
    if model and not device.get("model"):
        device["model"] = model
        changed = True

    mapping = map_lookup_by_model(driver_map, model)
    interface = infer_onboard_interface(peripheral, mapping)
    if interface and not device.get("interface"):
        device["interface"] = interface
        changed = True

    if interface == "I2C" and not device.get("i2c_addr"):
        addresses = onboard_i2c_addresses(peripheral, mapping)
        if addresses:
            device["i2c_addr"] = addresses
            changed = True

    mapped_driver = onboard_driver_for(peripheral, driver_map)
    if mapped_driver and device_driver_is_replaceable(device.get("driver")):
        device["driver"] = mapped_driver
        changed = True

    note = "Physical device is the selected board's onboard peripheral; do not add it to external BOM."
    if not ref.get("occupied_pins"):
        note += " Onboard pin mapping is not verified; it must not be treated as a hard pin constraint."
    updated_note = append_note(device.get("notes"), note)
    if updated_note != device.get("notes"):
        device["notes"] = updated_note
        changed = True
    return changed


def requirement_requested_onboard_types(requirements: dict[str, Any]) -> set[str]:
    requested: set[str] = set()
    output = requirements.get("output")
    if isinstance(output, list):
        for item in output:
            text = str(item).lower()
            if text.startswith("display_"):
                requested.add("display")
            if text == "led":
                requested.add("led")
            if text == "led_rgb":
                requested.add("rgb_led")
            if text == "local_file":
                requested.add("storage")

    network = str(requirements.get("network") or "").lower()
    if network == "lora":
        requested.add("radio_lora")
    if network == "ethernet":
        requested.add("ethernet")

    special = requirements.get("special_requirements")
    if isinstance(special, list):
        lowered = {str(item).lower() for item in special}
        if "voice_control" in lowered:
            requested.update({"microphone", "audio_codec", "speaker"})
        if "battery_monitor" in lowered:
            requested.add("power_mgmt")
        if "button_control" in lowered:
            requested.add("button")
        if "error_led" in lowered:
            requested.add("led")

    text_parts: list[str] = []
    for key in ("description", "description_en", "scene", "network"):
        value = requirements.get(key)
        if value not in (None, ""):
            text_parts.append(str(value))
    for key in ("output", "special_requirements", "existing_hardware"):
        value = requirements.get(key)
        if isinstance(value, list):
            text_parts.extend(str(item) for item in value)
    text = " ".join(text_parts).lower()
    compact = normalized_label(text)
    for ptype, keywords in ONBOARD_REQUIREMENT_KEYWORDS.items():
        if any(keyword.lower() in text or normalized_label(keyword) in compact for keyword in keywords):
            requested.add(ptype)
    return requested


def create_device_from_peripheral(
    board: dict[str, Any],
    peripheral: dict[str, Any],
    index: int,
    driver_map: dict[str, Any],
) -> dict[str, Any] | None:
    ptype = str(peripheral.get("type") or "").strip().lower()
    if not ptype:
        return None
    mapping = map_lookup_by_model(driver_map, peripheral.get("model"))
    interface = infer_onboard_interface(peripheral, mapping)
    if interface not in VALID_DEVICE_INTERFACES:
        return None
    name = str(peripheral.get("model") or peripheral.get("name") or ptype)
    device = {
        "name": name,
        "type": ptype,
        "interface": interface,
        "source": "system_recommended",
        "quantity": 1,
        "physical_source": "board_onboard",
        "onboard_peripheral_ref": peripheral_ref(board, peripheral, index),
        "driver": onboard_driver_for(peripheral, driver_map),
        "notes": "Auto-added from selected board onboard_peripherals because the user requirement can use it.",
    }
    if peripheral.get("model"):
        device["model"] = peripheral.get("model")
    if interface == "I2C":
        addresses = onboard_i2c_addresses(peripheral, mapping)
        if addresses:
            device["i2c_addr"] = addresses
    if not device["onboard_peripheral_ref"]["occupied_pins"]:
        device["notes"] = append_note(
            device["notes"],
            "Onboard pin mapping is not verified; it must not be treated as a hard pin constraint.",
        )
    return device


def merge_onboard_devices_into_upstream(
    upstream_manifest: Any,
    board: dict[str, Any] | None,
    warnings: list[str],
) -> dict[str, Any]:
    upstream = copy.deepcopy(upstream_manifest) if isinstance(upstream_manifest, dict) else {}
    if not isinstance(board, dict):
        return upstream

    peripherals = board.get("onboard_peripherals")
    if not isinstance(peripherals, list) or not peripherals:
        return upstream

    devices = upstream.get("devices")
    if not isinstance(devices, list):
        return upstream

    driver_map = load_onboard_driver_map()
    used_peripherals: set[int] = set()
    enriched = 0
    added = 0

    for device in devices:
        if not isinstance(device, dict):
            continue
        for index, peripheral in enumerate(peripherals):
            if index in used_peripherals or not isinstance(peripheral, dict):
                continue
            if device_matches_peripheral(device, peripheral):
                if enrich_device_from_peripheral(device, board, peripheral, index, driver_map):
                    enriched += 1
                used_peripherals.add(index)
                break

    requirements = upstream.get("requirements") if isinstance(upstream.get("requirements"), dict) else {}
    requested_types = requirement_requested_onboard_types(requirements)
    existing_types = {str(device.get("type") or "").strip().lower() for device in devices if isinstance(device, dict)}
    for index, peripheral in enumerate(peripherals):
        if index in used_peripherals or not isinstance(peripheral, dict):
            continue
        ptype = str(peripheral.get("type") or "").strip().lower()
        if ptype not in requested_types:
            continue
        if ptype in existing_types:
            continue
        device = create_device_from_peripheral(board, peripheral, index, driver_map)
        if device is None:
            warnings.append(
                f"board onboard peripheral '{peripheral.get('name') or ptype}' matched requirements but lacks a valid interface; not added to devices"
            )
            continue
        devices.append(device)
        existing_types.add(ptype)
        used_peripherals.add(index)
        added += 1

    if enriched or added:
        upstream["devices"] = devices
        upstream["board_onboard_device_resolution"] = {
            "board_id": board.get("id") or board.get("board_id"),
            "physical_source_field": "physical_source",
            "onboard_device_count_enriched": enriched,
            "onboard_device_count_added": added,
            "rule": "devices[].source keeps user_specified/system_recommended; physical_source=board_onboard records board integration",
        }
        warnings.append(f"board onboard device resolution enriched {enriched} device(s), added {added} device(s)")
    return upstream


def validate_device_consistency(
    upstream_manifest: Any,
    plan: dict[str, Any],
    selected_board: Any,
    errors: list[str],
    warnings: list[str],
) -> None:
    upstream = upstream_manifest if isinstance(upstream_manifest, dict) else {}
    tokens, display_names = device_match_tokens(upstream.get("devices"))
    known = ", ".join(display_names) if display_names else "<none>"

    pinout = plan.get("pinout")
    if isinstance(pinout, list):
        for index, raw in enumerate(pinout):
            if not isinstance(raw, dict):
                continue
            device = raw.get("device")
            if is_system_pinout_device(device) or matches_device_token(device, tokens):
                continue
            errors.append(
                f"hardware_plan.pinout[{index}].device '{device}' is not in upstream_manifest.devices; "
                f"select-hw must not introduce new hardware devices. Known devices: {known}"
            )

    bom = plan.get("bom")
    mcu = plan.get("mcu")
    if isinstance(bom, list):
        for index, raw in enumerate(bom):
            if not isinstance(raw, dict):
                continue
            if (
                bom_matches_upstream_device(raw, tokens)
                or bom_is_support_item(raw)
                or bom_is_controller(raw, selected_board, mcu)
            ):
                continue
            if bom_is_functional_hardware(raw):
                errors.append(
                    f"hardware_plan.bom[{index}] '{raw.get('name') or raw.get('model')}' looks like functional hardware "
                    "but does not map to upstream_manifest.devices; add/replace devices in analyze before select-hw success"
                )
            elif text_contains_any(bom_text(raw), {"module", "模块"}):
                warnings.append(
                    f"hardware_plan.bom[{index}] '{raw.get('name') or raw.get('model')}' is not mapped to an upstream device; "
                    "confirm it is only an accessory/support item"
                )


def validate_protocol_version(data: dict[str, Any], errors: list[str]) -> None:
    if data.get("protocol_version") != PROTOCOL_VERSION:
        errors.append(f"protocol_version must be '{PROTOCOL_VERSION}'")


def validate_upstream_manifest(manifest: Any, errors: list[str], warnings: list[str]) -> None:
    upstream = require_object(manifest, "upstream_manifest", errors)
    if upstream is None:
        return

    required = ["schema_version", "phase", "project_name", "requirements", "devices"]
    for field in required:
        if field not in upstream:
            errors.append(f"upstream_manifest.{field} is required")

    if upstream.get("phase") != "analyze":
        errors.append("upstream_manifest.phase must be 'analyze'")

    requirements = require_object(upstream.get("requirements"), "upstream_manifest.requirements", errors)
    devices = require_list(upstream.get("devices"), "upstream_manifest.devices", errors)
    if requirements is not None:
        for field in ["description", "existing_hardware", "mcu_specified"]:
            if field not in requirements:
                errors.append(f"upstream_manifest.requirements.{field} is required")
        if not isinstance(requirements.get("existing_hardware", []), list):
            errors.append("upstream_manifest.requirements.existing_hardware must be an array")
    if devices is not None:
        if not devices:
            errors.append("upstream_manifest.devices must not be empty")
        for index, device in enumerate(devices):
            prefix = f"upstream_manifest.devices[{index}]"
            item = require_object(device, prefix, errors)
            if item is None:
                continue
            for field in ["name", "type", "interface", "source", "driver"]:
                if field not in item:
                    errors.append(f"{prefix}.{field} is required")
            interface = item.get("interface")
            if interface not in VALID_DEVICE_INTERFACES:
                errors.append(
                    f"{prefix}.interface invalid value '{interface}', valid values: {sorted(VALID_DEVICE_INTERFACES)}"
                )
            driver = require_object(item.get("driver"), f"{prefix}.driver", errors)
            if driver is not None:
                source = driver.get("source")
                if source not in VALID_DRIVER_SOURCES:
                    errors.append(
                        f"{prefix}.driver.source invalid value '{source}', valid values: {sorted(VALID_DRIVER_SOURCES)}"
                    )
                normalize_driver_status(driver, prefix, warnings, errors)


def validate_mcu(mcu: Any, errors: list[str]) -> None:
    obj = require_object(mcu, "hardware_plan.mcu", errors)
    if obj is None:
        return
    required = [
        "model",
        "board_id",
        "display_name",
        "firmware_url",
        "firmware_board_name",
        "flash_tool",
    ]
    for field in required:
        if not obj.get(field):
            errors.append(f"hardware_plan.mcu.{field} is required")
    if obj.get("flash_tool") not in FLASH_TOOLS:
        errors.append(
            f"hardware_plan.mcu.flash_tool invalid value '{obj.get('flash_tool')}', valid values: {sorted(FLASH_TOOLS)}"
        )


def gpio_key(value: Any) -> str:
    text = str(value).strip().upper()
    if text.startswith("GPIO"):
        text = text[4:]
    return text


def load_board_definition(board_root: Path | None, board_id: str | None, errors: list[str]) -> dict[str, Any] | None:
    if not board_id:
        errors.append("hardware_plan.mcu.board_id is required for board definition validation")
        return None
    root = board_root or DEFAULT_BOARD_ROOT
    path = root / f"{board_id}.json"
    if not path.is_file():
        errors.append(f"board definition not found: {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            board = json.load(f)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"board definition load failed: {path}: {exc}")
        return None
    if not isinstance(board, dict):
        errors.append(f"board definition must be an object: {path}")
        return None
    if board.get("id") != board_id:
        errors.append(f"board definition id '{board.get('id')}' does not match board_id '{board_id}'")
    if not isinstance(board.get("pin_layout"), dict):
        errors.append(f"board definition {board_id} must include pin_layout")
    return board


def validate_selected_board_against_definition(
    selected_board: dict[str, Any] | None,
    mcu: dict[str, Any] | None,
    board: dict[str, Any] | None,
    errors: list[str],
) -> None:
    if selected_board is None or mcu is None or board is None:
        return
    if selected_board.get("id") and selected_board.get("id") != board.get("id"):
        errors.append(f"selected_board.id '{selected_board.get('id')}' does not match board definition '{board.get('id')}'")
    firmware = board.get("firmware", {})
    selected_firmware = selected_board.get("firmware", {})
    if firmware.get("board_name") and selected_firmware.get("board_name") != firmware.get("board_name"):
        errors.append("selected_board.firmware.board_name does not match board definition")
    if firmware.get("url") and selected_firmware.get("url") != firmware.get("url"):
        errors.append("selected_board.firmware.url does not match board definition")
    if firmware.get("board_name") and mcu.get("firmware_board_name") != firmware.get("board_name"):
        errors.append("hardware_plan.mcu.firmware_board_name does not match board definition")
    if firmware.get("url") and mcu.get("firmware_url") != firmware.get("url"):
        errors.append("hardware_plan.mcu.firmware_url does not match board definition")


def restricted_pin_sets(board: dict[str, Any]) -> dict[str, set[str]]:
    restricted = board.get("pin_layout", {}).get("restricted_gpio", {})
    result: dict[str, set[str]] = {}
    if not isinstance(restricted, dict):
        return result
    for key, values in restricted.items():
        if isinstance(values, list):
            result[key] = {gpio_key(value) for value in values}
    return result


def onboard_occupied_pins(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    occupied: dict[str, dict[str, Any]] = {}
    peripherals = board.get("onboard_peripherals", [])
    if not isinstance(peripherals, list):
        return occupied
    for peripheral in peripherals:
        if not isinstance(peripheral, dict):
            continue
        pins = peripheral.get("occupied_pins", {})
        if not isinstance(pins, dict):
            continue
        for signal, gpio in pins.items():
            occupied[gpio_key(gpio)] = {
                "name": peripheral.get("name", "onboard_peripheral"),
                "type": peripheral.get("type"),
                "signal": signal,
                "always_used": bool(peripheral.get("always_used")),
            }
    return occupied


def pin_source(item: dict[str, Any]) -> str:
    source = item.get("source")
    if isinstance(source, str) and source:
        return source
    pin_type = item.get("type")
    if pin_type in {"power_3v3", "power_5v", "gnd"}:
        return "power"
    return "auto_assigned"


def validate_pin_source(item: dict[str, Any], prefix: str, errors: list[str]) -> None:
    source = item.get("source")
    if source is not None and source not in PIN_SOURCES:
        errors.append(f"{prefix}.source invalid value '{source}', valid values: {sorted(PIN_SOURCES)}")


def default_bus_expected_pins(board: dict[str, Any]) -> dict[tuple[str, str], str]:
    defaults = board.get("pin_layout", {}).get("default_bus_pins", {})
    expected: dict[tuple[str, str], str] = {}
    if not isinstance(defaults, dict):
        return expected
    signal_aliases = {
        "sda": {"i2c_data"},
        "scl": {"i2c_clock"},
        "mosi": {"spi_mosi"},
        "miso": {"spi_miso"},
        "clk": {"spi_sck", "i2s_bck"},
        "sck": {"spi_sck"},
        "cs": {"spi_cs"},
        "tx": {"uart_tx"},
        "rx": {"uart_rx"},
        "bck": {"i2s_bck"},
        "ws": {"i2s_ws"},
        "data_in": {"i2s_data_in"},
        "data_out": {"i2s_data_out"},
    }
    for bus, pins in defaults.items():
        if not isinstance(pins, dict):
            continue
        for signal, gpio in pins.items():
            for pin_type in signal_aliases.get(signal, set()):
                expected[(str(bus), pin_type)] = gpio_key(gpio)
    return expected


def has_reason(item: dict[str, Any]) -> bool:
    notes = item.get("notes")
    return isinstance(notes, str) and bool(notes.strip())


def expected_power_pin_type(gpio: Any) -> str | None:
    value = gpio_key(gpio)
    if value == "GND":
        return "gnd"
    if value == "3V3":
        return "power_3v3"
    if value == "5V":
        return "power_5v"
    return None


def validate_pinout_against_board(
    pinout: Any,
    board: dict[str, Any] | None,
    requirements: dict[str, Any] | None,
    errors: list[str],
    warnings: list[str],
    *,
    strict_board_pins: bool,
) -> None:
    if board is None:
        return
    items = require_list(pinout, "hardware_plan.pinout", errors)
    if items is None:
        return
    restricted = restricted_pin_sets(board)
    occupied = onboard_occupied_pins(board)
    defaults = default_bus_expected_pins(board)
    wifi_enabled = bool(requirements and requirements.get("network") == "wifi")
    adc2_digital_uses: dict[str, list[str]] = {}
    hard_forbidden = set()
    for key in ["flash_psram_occupied", "reserved", "internal_only"]:
        hard_forbidden.update(restricted.get(key, set()))

    for index, raw in enumerate(items):
        prefix = f"hardware_plan.pinout[{index}]"
        if not isinstance(raw, dict):
            continue
        validate_pin_source(raw, prefix, errors)
        pin_type = raw.get("type")
        gpio = gpio_key(raw.get("gpio", ""))
        if not gpio or gpio in {"3V3", "5V", "GND"}:
            continue

        source = pin_source(raw)
        if gpio in hard_forbidden:
            errors.append(f"{prefix}.gpio {gpio} is forbidden by board restricted_gpio")
        if gpio in restricted.get("usb_serial_pins", set()) and source != "user_wiring":
            errors.append(f"{prefix}.gpio {gpio} is a USB serial pin; require explicit user_wiring to use it")
        if gpio in restricted.get("strapping", set()) or gpio in restricted.get("boot", set()):
            message = f"{prefix}.gpio {gpio} is a boot/strapping pin and should be avoided"
            if strict_board_pins:
                errors.append(message)
            else:
                warnings.append(message)
            if not has_reason(raw):
                warnings.append(f"{prefix}.notes should explain boot/strapping pin usage")
        if gpio in restricted.get("input_only", set()) and pin_type not in {"gpio_in", "gpio_in_pullup", "adc", "i2s_data_in", "uart_rx"}:
            errors.append(f"{prefix}.gpio {gpio} is input-only but type is {pin_type}")
        if gpio in restricted.get("adc_only", set()) and pin_type != "adc":
            errors.append(f"{prefix}.gpio {gpio} is ADC-only but type is {pin_type}")
        if wifi_enabled and gpio in restricted.get("adc2_wifi_conflict", set()):
            if pin_type == "adc":
                errors.append(f"{prefix}.gpio {gpio} is ADC2/WiFi conflict pin while WiFi is enabled")
            else:
                adc2_digital_uses.setdefault(gpio, []).append(f"{raw.get('device', '?')}/{raw.get('pin_name', '?')}:{pin_type}")

        occupied_info = occupied.get(gpio)
        if occupied_info and source != "onboard_peripheral":
            if occupied_info.get("always_used"):
                errors.append(f"{prefix}.gpio {gpio} is occupied by onboard peripheral {occupied_info['name']}")
            elif source != "user_wiring":
                warnings.append(f"{prefix}.gpio {gpio} is occupied by onboard peripheral {occupied_info['name']}; explain release in notes")
                if not has_reason(raw):
                    warnings.append(f"{prefix}.notes should explain onboard peripheral pin reuse")
        if source == "onboard_peripheral" and not occupied_info:
            warnings.append(f"{prefix}.source onboard_peripheral but gpio {gpio} is not declared in board onboard_peripherals")

        bus = raw.get("bus")
        if isinstance(bus, str) and (bus, str(pin_type)) in defaults and source != "user_wiring":
            expected_gpio = defaults[(bus, str(pin_type))]
            if gpio != expected_gpio:
                message = f"{prefix}.gpio {gpio} deviates from board default {bus}/{pin_type}=GPIO{expected_gpio}"
                if strict_board_pins:
                    errors.append(message)
                else:
                    warnings.append(message)
                if not has_reason(raw):
                    warnings.append(f"{prefix}.notes should explain default bus pin deviation")

    if adc2_digital_uses:
        used = ", ".join(
            f"GPIO{gpio}({'; '.join(descriptions)})"
            for gpio, descriptions in sorted(
                adc2_digital_uses.items(),
                key=lambda item: int(item[0]) if item[0].isdigit() else item[0],
            )
        )
        warnings.append(
            "ADC2/WiFi conflict pins are used only as digital signals: "
            f"{used}; WiFi conflicts with ADC reads, not digital GPIO/I2C/I2S use"
        )


def is_shareable_pin(pin_type: str, pin_name: str) -> bool:
    if pin_type in {"power_3v3", "power_5v", "gnd", "wifi_internal", "reserved"}:
        return True
    if pin_type in {"i2c_data", "i2c_clock", "spi_mosi", "spi_miso", "spi_sck", "i2s_bck", "i2s_ws"}:
        return True
    return pin_name.upper() in {"SDA", "SCL", "MOSI", "MISO", "SCK", "BCK", "WS"}


def is_config_power_tie(pin_name: Any, assigned_gpio: Any) -> bool:
    name = str(pin_name).strip().upper().replace("-", "_")
    gpio = gpio_key(assigned_gpio)
    if gpio == "5V":
        return True
    supply_names = {"VCC", "VDD", "VDDIO", "VIN", "VBUS", "3V3", "5V", "GND", "GROUND"}
    if name in supply_names:
        return False
    config_tokens = {
        "ADDR",
        "ADDRESS",
        "BOOT",
        "CFG",
        "CONFIG",
        "CS",
        "EN",
        "ENABLE",
        "GAIN",
        "LR",
        "L/R",
        "MODE",
        "SEL",
        "SELECT",
        "SD",
        "SHDN",
        "SLEEP",
        "WAKE",
    }
    return name in config_tokens or any(token in name.split("_") for token in config_tokens)


def validate_pinout(pinout: Any, errors: list[str], warnings: list[str]) -> None:
    items = require_list(pinout, "hardware_plan.pinout", errors)
    if items is None:
        return
    if not items:
        errors.append("hardware_plan.pinout must not be empty")
        return

    gpio_owners: dict[str, str] = {}
    i2c_addresses: dict[tuple[str, str], str] = {}
    has_power = False
    has_gnd = False
    i2s_types = set()

    for index, raw in enumerate(items):
        prefix = f"hardware_plan.pinout[{index}]"
        item = require_object(raw, prefix, errors)
        if item is None:
            continue
        for field in ["device", "pin_name", "gpio", "type"]:
            if field not in item or item[field] in (None, ""):
                errors.append(f"{prefix}.{field} is required")

        pin_type = item.get("type")
        if pin_type not in PIN_TYPES:
            errors.append(f"{prefix}.type invalid value '{pin_type}', valid values: {sorted(PIN_TYPES)}")
            continue

        expected_power_type = expected_power_pin_type(item.get("gpio"))
        if expected_power_type is not None and pin_type != expected_power_type:
            errors.append(f"{prefix}.type must be {expected_power_type} when gpio is {item.get('gpio')}")

        if pin_type in {"power_3v3", "power_5v"}:
            has_power = True
        if pin_type == "gnd":
            has_gnd = True
        if pin_type.startswith("i2s_"):
            i2s_types.add(pin_type)

        gpio = str(item.get("gpio", ""))
        pin_name = str(item.get("pin_name", ""))
        if gpio and not is_shareable_pin(pin_type, pin_name):
            if gpio in gpio_owners:
                errors.append(f"{prefix}.gpio {gpio} conflicts with {gpio_owners[gpio]}")
            else:
                gpio_owners[gpio] = item.get("device", prefix)

        if pin_type in {"i2c_data", "i2c_clock"} and item.get("i2c_addr"):
            bus = str(item.get("bus", "i2c0"))
            addr = str(item.get("i2c_addr"))
            key = (bus, addr)
            owner = item.get("device", prefix)
            if key in i2c_addresses and i2c_addresses[key] != owner:
                errors.append(f"{prefix}.i2c_addr {addr} conflicts on {bus} with {i2c_addresses[key]}")
            i2c_addresses[key] = owner

    if not has_power:
        errors.append("hardware_plan.pinout must include at least one power pin")
    if not has_gnd:
        errors.append("hardware_plan.pinout must include at least one ground pin")
    if i2s_types and not {"i2s_bck", "i2s_ws"}.issubset(i2s_types):
        warnings.append("I2S pinout should include both i2s_bck and i2s_ws")


def validate_bom(bom: Any, errors: list[str]) -> float:
    items = require_list(bom, "hardware_plan.bom", errors)
    total = 0.0
    if items is None:
        return total
    if not items:
        errors.append("hardware_plan.bom must not be empty")
        return total
    for index, raw in enumerate(items):
        prefix = f"hardware_plan.bom[{index}]"
        item = require_object(raw, prefix, errors)
        if item is None:
            continue
        for field in ["name", "model", "quantity", "unit_price_yuan"]:
            if field not in item or item[field] in (None, ""):
                errors.append(f"{prefix}.{field} is required")
        try:
            quantity = float(item.get("quantity", 0))
            unit_price = float(item.get("unit_price_yuan", 0))
        except (TypeError, ValueError):
            errors.append(f"{prefix}.quantity and unit_price_yuan must be numeric")
            continue
        if quantity <= 0:
            errors.append(f"{prefix}.quantity must be positive")
        if unit_price < 0:
            errors.append(f"{prefix}.unit_price_yuan must not be negative")
        total += quantity * unit_price
    return total


def pinout_decision_keys(pinout: Any) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    if not isinstance(pinout, list):
        return keys
    for item in pinout:
        if not isinstance(item, dict):
            continue
        keys.add(
            (
                str(item.get("device", "")),
                str(item.get("pin_name", "")),
                gpio_key(item.get("gpio", "")),
            )
        )
    return keys


def board_occupied_pin_values(board: dict[str, Any] | None) -> set[str]:
    if board is None:
        return set()
    return set(onboard_occupied_pins(board))


def validate_pin_decisions(
    decisions: Any,
    pinout: Any,
    board: dict[str, Any] | None,
    errors: list[str],
    warnings: list[str],
) -> None:
    items = require_list(decisions, "hardware_plan.pin_decisions", errors)
    if items is None:
        return

    pinout_keys = pinout_decision_keys(pinout)
    occupied_values = board_occupied_pin_values(board)
    seen: set[tuple[str, str, str]] = set()

    for index, raw in enumerate(items):
        prefix = f"hardware_plan.pin_decisions[{index}]"
        item = require_object(raw, prefix, errors)
        if item is None:
            continue

        for field in ["device", "pin_name", "assigned_gpio", "decision_type", "source", "evidence", "requires_user_review"]:
            if field not in item or item[field] in (None, ""):
                errors.append(f"{prefix}.{field} is required")

        decision_type = item.get("decision_type")
        source = item.get("source")
        if decision_type not in PIN_DECISION_TYPES:
            errors.append(
                f"{prefix}.decision_type invalid value '{decision_type}', valid values: {sorted(PIN_DECISION_TYPES)}"
            )
        if source not in PIN_DECISION_SOURCES:
            errors.append(f"{prefix}.source invalid value '{source}', valid values: {sorted(PIN_DECISION_SOURCES)}")
        if "requires_user_review" in item and not isinstance(item["requires_user_review"], bool):
            errors.append(f"{prefix}.requires_user_review must be a boolean")
        evidence = require_object(item.get("evidence"), f"{prefix}.evidence", errors)
        if evidence is not None and not (evidence.get("path") or evidence.get("note")):
            errors.append(f"{prefix}.evidence must include path or note")

        key = (str(item.get("device", "")), str(item.get("pin_name", "")), gpio_key(item.get("assigned_gpio", "")))
        if key in seen:
            errors.append(f"{prefix} duplicates decision for {key}")
        seen.add(key)
        if pinout_keys and key not in pinout_keys:
            errors.append(f"{prefix} does not match any hardware_plan.pinout item")

        if decision_type == "fixed_power_tie" and source != "fixed_power":
            errors.append(f"{prefix}.source must be fixed_power when decision_type=fixed_power_tie")
        if source == "fixed_power" and decision_type != "fixed_power_tie":
            errors.append(f"{prefix}.decision_type must be fixed_power_tie when source=fixed_power")

        deviation = item.get("deviation")
        if deviation is not None:
            dev = require_object(deviation, f"{prefix}.deviation", errors)
            if dev is not None:
                for field in ["from_gpio", "to_gpio", "reason_code", "evidence_path", "evidence_value", "validator_action"]:
                    if field not in dev or dev[field] in (None, ""):
                        errors.append(f"{prefix}.deviation.{field} is required")
                reason_code = dev.get("reason_code")
                if reason_code not in PIN_DEVIATION_REASON_CODES:
                    errors.append(
                        f"{prefix}.deviation.reason_code invalid value '{reason_code}', "
                        f"valid values: {sorted(PIN_DEVIATION_REASON_CODES)}"
                    )
                validator_action = dev.get("validator_action")
                if validator_action not in PIN_DEVIATION_VALIDATOR_ACTIONS:
                    errors.append(
                        f"{prefix}.deviation.validator_action invalid value '{validator_action}', "
                        f"valid values: {sorted(PIN_DEVIATION_VALIDATOR_ACTIONS)}"
                    )
                if reason_code == "onboard_occupied":
                    evidence_path = str(dev.get("evidence_path", ""))
                    evidence_value = gpio_key(dev.get("evidence_value", ""))
                    from_gpio = gpio_key(dev.get("from_gpio", ""))
                    if "onboard_peripherals" not in evidence_path or "occupied_pins" not in evidence_path:
                        errors.append(f"{prefix}.deviation.evidence_path must point to onboard_peripherals[].occupied_pins")
                    if evidence_value != from_gpio:
                        errors.append(f"{prefix}.deviation.evidence_value must match from_gpio for onboard_occupied")
                    if board is not None and from_gpio not in occupied_values:
                        errors.append(f"{prefix}.deviation.from_gpio is not declared in board onboard_peripherals")

        if decision_type == "fixed_power_tie" and is_config_power_tie(item.get("pin_name"), item.get("assigned_gpio")):
            prompt = item.get("review_prompt")
            if item.get("requires_user_review") is True and not isinstance(prompt, str):
                warnings.append(f"{prefix}.review_prompt is recommended for reviewed fixed_power_tie")


def validate_pin_review(
    value: Any,
    errors: list[str],
    *,
    require_confirmed: bool,
    phase_timestamp: datetime | None = None,
) -> None:
    review = require_object(value, "hardware_plan.pin_review", errors)
    if review is None:
        return
    if review.get("approval_id") != "pin_plan_review":
        errors.append("hardware_plan.pin_review.approval_id must be 'pin_plan_review'")
    if "confirmed" not in review or not isinstance(review.get("confirmed"), bool):
        errors.append("hardware_plan.pin_review.confirmed must be a boolean")
    if require_confirmed and review.get("confirmed") is not True:
        errors.append("hardware_plan.pin_review.confirmed must be true when result=success")
    if review.get("source") not in PIN_REVIEW_SOURCES:
        errors.append(
            f"hardware_plan.pin_review.source invalid value '{review.get('source')}', "
            f"valid values: {sorted(PIN_REVIEW_SOURCES)}"
        )
    if review.get("confirmed"):
        for field in ["confirmed_by", "confirmed_at"]:
            if not review.get(field):
                errors.append(f"hardware_plan.pin_review.{field} is required when confirmed=true")
        confirmed_at = parse_utc_timestamp(
            review.get("confirmed_at"),
            "hardware_plan.pin_review.confirmed_at",
            errors,
        )
        if phase_timestamp is not None and confirmed_at is not None:
            if confirmed_at > phase_timestamp:
                errors.append("hardware_plan.pin_review.confirmed_at must not be later than phase_complete.timestamp")
            if phase_timestamp - confirmed_at > PIN_REVIEW_MAX_PHASE_AGE:
                errors.append("hardware_plan.pin_review.confirmed_at is too old for this phase_complete")
            if confirmed_at.time() == datetime.min.time():
                errors.append("hardware_plan.pin_review.confirmed_at must be the actual approval time, not a date-only placeholder")


def normalize_manifest(draft: dict[str, Any], effective_upstream: dict[str, Any] | None = None) -> dict[str, Any]:
    upstream = copy.deepcopy(effective_upstream if effective_upstream is not None else draft["upstream_manifest"])
    plan = copy.deepcopy(draft["hardware_plan"])
    mcu = copy.deepcopy(plan["mcu"])
    estimated_total = plan.get("estimated_total_yuan")
    if estimated_total is None:
        estimated_total = sum(
            float(item.get("quantity", 1)) * float(item.get("unit_price_yuan", 0))
            for item in plan.get("bom", [])
        )

    manifest = {
        "schema_version": upstream.get("schema_version", "1.0"),
        "phase": PHASE,
        "created_at": upstream.get("created_at", utc_now()),
        "updated_at": utc_now(),
        "project_name": upstream["project_name"],
        "requirements": upstream["requirements"],
        "devices": upstream["devices"],
        "mcu": mcu,
        "hardware_selection": {
            "source_phase": draft.get("source_phase", "analyze"),
            "selected_board": copy.deepcopy(draft.get("selected_board", {})),
            "board_confirmed": True,
            "firmware_checked": True,
            "price_source": "llm_common_knowledge_v0",
        },
        "pinout": copy.deepcopy(plan.get("pinout", [])),
        "pin_decisions": copy.deepcopy(plan.get("pin_decisions", [])),
        "pin_review": copy.deepcopy(plan.get("pin_review", {})),
        "bom": normalize_bom_items(plan.get("bom", [])),
        "estimated_total_yuan": estimated_total,
        "final_status": "hardware_selected",
    }
    if upstream.get("board_onboard_device_resolution"):
        manifest["board_onboard_device_resolution"] = copy.deepcopy(upstream["board_onboard_device_resolution"])
    return manifest


def validate_draft(
    draft: dict[str, Any],
    board_root: Path | None = None,
    *,
    strict_board_pins: bool = False,
    require_pin_review_confirmed: bool = True,
    phase_timestamp: datetime | None = None,
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    errors: list[str] = []
    warnings: list[str] = []
    validate_protocol_version(draft, errors)

    if not draft.get("session_id"):
        errors.append("session_id is required")
    if draft.get("source_phase") != "analyze":
        errors.append("source_phase must be 'analyze'")

    validate_upstream_manifest(draft.get("upstream_manifest"), errors, warnings)
    selected_board = require_object(draft.get("selected_board"), "selected_board", errors)
    if selected_board is not None:
        for field in ["id", "display_name", "mcu", "firmware"]:
            if field not in selected_board:
                errors.append(f"selected_board.{field} is required")
        firmware = require_object(selected_board.get("firmware"), "selected_board.firmware", errors)
        if firmware is not None:
            for field in ["url", "board_name"]:
                if not firmware.get(field):
                    errors.append(f"selected_board.firmware.{field} is required")

    plan = require_object(draft.get("hardware_plan"), "hardware_plan", errors)
    board_definition = None
    mcu_obj = plan.get("mcu") if isinstance(plan, dict) and isinstance(plan.get("mcu"), dict) else None
    if mcu_obj is not None:
        board_definition = load_board_definition(board_root, mcu_obj.get("board_id"), errors)
        validate_selected_board_against_definition(selected_board, mcu_obj, board_definition, errors)
    effective_upstream = draft.get("upstream_manifest")
    if isinstance(effective_upstream, dict):
        effective_upstream = merge_onboard_devices_into_upstream(effective_upstream, board_definition, warnings)

    if plan is not None:
        validate_mcu(plan.get("mcu"), errors)
        validate_pinout(plan.get("pinout"), errors, warnings)
        requirements = effective_upstream.get("requirements") if isinstance(effective_upstream, dict) else {}
        if not isinstance(requirements, dict):
            requirements = {}
        validate_pinout_against_board(
            plan.get("pinout"),
            board_definition,
            requirements,
            errors,
            warnings,
            strict_board_pins=strict_board_pins,
        )
        validate_pin_decisions(
            plan.get("pin_decisions"),
            plan.get("pinout"),
            board_definition,
            errors,
            warnings,
        )
        validate_pin_review(
            plan.get("pin_review"),
            errors,
            require_confirmed=require_pin_review_confirmed,
            phase_timestamp=phase_timestamp,
        )
        validate_device_consistency(effective_upstream, plan, selected_board, errors, warnings)
        total = validate_bom(plan.get("bom"), errors)
        declared_total = plan.get("estimated_total_yuan")
        if declared_total is None:
            warnings.append("hardware_plan.estimated_total_yuan missing; computed from BOM")
        else:
            try:
                declared = float(declared_total)
                if abs(declared - total) > 0.01:
                    warnings.append(f"estimated_total_yuan {declared:g} differs from computed BOM total {total:g}")
            except (TypeError, ValueError):
                errors.append("hardware_plan.estimated_total_yuan must be numeric")

    if errors:
        return errors, warnings, None
    return errors, warnings, normalize_manifest(draft, effective_upstream if isinstance(effective_upstream, dict) else None)


def phase_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.get("payload")
    if isinstance(payload, dict):
        return payload
    return data


def validate_structured_errors(value: Any, errors: list[str]) -> None:
    items = require_list(value, "phase_complete.structured_errors", errors)
    if items is None:
        return
    for index, raw in enumerate(items):
        prefix = f"phase_complete.structured_errors[{index}]"
        item = require_object(raw, prefix, errors)
        if item is None:
            continue
        for field in ["code", "message", "severity", "recoverable", "retryable", "source"]:
            if field not in item:
                errors.append(f"{prefix}.{field} is required")
        if item.get("severity") not in STRUCTURED_SEVERITIES:
            errors.append(f"{prefix}.severity invalid value '{item.get('severity')}', valid values: {sorted(STRUCTURED_SEVERITIES)}")
        if item.get("code") not in STRUCTURED_CODES:
            errors.append(f"{prefix}.code invalid value '{item.get('code')}', valid values: {sorted(STRUCTURED_CODES)}")
        for field in ["recoverable", "retryable"]:
            if field in item and not isinstance(item[field], bool):
                errors.append(f"{prefix}.{field} must be a boolean")


def validate_runtime_context(value: Any, errors: list[str], session_id: str | None) -> dict[str, Any] | None:
    context = require_object(value, "phase_complete.runtime_context", errors)
    if context is None:
        return None
    mode = context.get("artifact_root_mode")
    if mode not in ARTIFACT_ROOT_MODES:
        errors.append(
            f"phase_complete.runtime_context.artifact_root_mode invalid value '{mode}', "
            f"valid values: {sorted(ARTIFACT_ROOT_MODES)}"
        )
    artifact_root = context.get("artifact_root")
    if not isinstance(artifact_root, str) or not artifact_root:
        errors.append("phase_complete.runtime_context.artifact_root is required")
    session_root = context.get("session_root")
    if not isinstance(session_root, str) or not session_root:
        errors.append("phase_complete.runtime_context.session_root is required")
    elif Path(session_root).is_absolute() or ".." in Path(session_root).parts:
        errors.append("phase_complete.runtime_context.session_root must be relative")
    if mode == "cwd":
        expected = f"sessions/{session_id}" if session_id else None
        if expected and session_root != expected:
            errors.append(f"phase_complete.runtime_context.session_root must be '{expected}' when artifact_root_mode=cwd")
    resource_root = context.get("resource_root")
    if not isinstance(resource_root, str) or not resource_root:
        errors.append("phase_complete.runtime_context.resource_root is required")
    return context


def is_session_relative_artifact(rel_path: str, session_root: str) -> bool:
    parts = Path(rel_path).parts
    session_parts = Path(session_root).parts
    return len(parts) > len(session_parts) and tuple(parts[: len(session_parts)]) == tuple(session_parts)


def validate_artifacts(
    value: Any,
    errors: list[str],
    artifact_root: Path | None,
    runtime_context: dict[str, Any] | None,
) -> None:
    artifacts = require_list(value, "phase_complete.artifacts", errors)
    if artifacts is None:
        return
    mode = runtime_context.get("artifact_root_mode") if isinstance(runtime_context, dict) else None
    session_root = runtime_context.get("session_root") if isinstance(runtime_context, dict) else None
    for index, raw in enumerate(artifacts):
        prefix = f"phase_complete.artifacts[{index}]"
        artifact = require_object(raw, prefix, errors)
        if artifact is None:
            continue
        artifact_type = artifact.get("type")
        if artifact_type not in ARTIFACT_TYPES:
            errors.append(f"{prefix}.type invalid value '{artifact_type}', valid values: {sorted(ARTIFACT_TYPES)}")
            continue
        if artifact_type == "table":
            if not isinstance(artifact.get("headers"), list):
                errors.append(f"{prefix}.headers must be an array")
            if not isinstance(artifact.get("rows"), list):
                errors.append(f"{prefix}.rows must be an array")
        if artifact_type == "file_list":
            files = require_list(artifact.get("files"), f"{prefix}.files", errors)
            if files is None:
                continue
            for file_index, raw_file in enumerate(files):
                file_prefix = f"{prefix}.files[{file_index}]"
                file_item = require_object(raw_file, file_prefix, errors)
                if file_item is None:
                    continue
                rel_path = file_item.get("path")
                if not isinstance(rel_path, str) or not rel_path:
                    errors.append(f"{file_prefix}.path is required")
                    continue
                if Path(rel_path).is_absolute() or ".." in Path(rel_path).parts:
                    errors.append(f"{file_prefix}.path must be relative and stay inside artifact root")
                elif mode == "cwd" and isinstance(session_root, str):
                    if not is_session_relative_artifact(rel_path, session_root):
                        errors.append(f"{file_prefix}.path must be under {session_root}/ when artifact_root_mode=cwd")
                elif mode == "session_root" and len(Path(rel_path).parts) != 1:
                    errors.append(f"{file_prefix}.path must be a bare filename when artifact_root_mode=session_root")
                status = file_item.get("status")
                if status not in FILE_STATUSES:
                    errors.append(f"{file_prefix}.status invalid value '{status}', valid values: {sorted(FILE_STATUSES)}")
                if artifact_root is not None and not (artifact_root / rel_path).is_file():
                    errors.append(f"{file_prefix}.path declares missing artifact file: {rel_path}")


def artifact_file_paths(value: Any) -> set[str]:
    paths: set[str] = set()
    if not isinstance(value, list):
        return paths
    for artifact in value:
        if not isinstance(artifact, dict) or artifact.get("type") != "file_list":
            continue
        files = artifact.get("files", [])
        if not isinstance(files, list):
            continue
        for item in files:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                paths.add(item["path"])
    return paths


def validate_expected_artifacts(value: Any, expected: list[str], errors: list[str]) -> None:
    declared = artifact_file_paths(value)
    for path in expected:
        if path not in declared:
            errors.append(f"phase_complete.artifacts missing expected file: {path}")


def core_manifest(value: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "schema_version",
        "phase",
        "project_name",
        "requirements",
        "devices",
        "mcu",
        "pinout",
        "pin_decisions",
        "pin_review",
        "bom",
        "estimated_total_yuan",
        "final_status",
    ]
    return {key: value.get(key) for key in keys}


def validate_phase_complete(
    data: dict[str, Any],
    compare_manifest: dict[str, Any] | None,
    artifact_root: Path | None,
    board_root: Path | None = None,
    expected_artifacts: list[str] | None = None,
    *,
    strict_board_pins: bool = False,
    enforce_pin_review_timing: bool = True,
    require_runtime_context: bool = True,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if "payload" in data:
        validate_protocol_version(data, errors)
        if data.get("type") != "phase_complete":
            errors.append("message type must be phase_complete")
        if data.get("phase") != PHASE:
            errors.append(f"top-level phase must be '{PHASE}'")
        if not data.get("msg_id"):
            errors.append("msg_id is required")
        if not data.get("session_id"):
            errors.append("session_id is required")
        if not data.get("timestamp"):
            errors.append("timestamp is required")
        if data.get("type") not in MESSAGE_TYPES:
            errors.append(f"type invalid value '{data.get('type')}', valid values: {sorted(MESSAGE_TYPES)}")
    phase_timestamp = parse_utc_timestamp(data.get("timestamp"), "timestamp", errors) if "payload" in data else None
    review_phase_timestamp = phase_timestamp if enforce_pin_review_timing else None

    payload = phase_payload(data)
    if payload.get("phase") != PHASE:
        errors.append(f"payload.phase must be '{PHASE}'")
    result = payload.get("result")
    if result not in RESULTS:
        errors.append(f"payload.result invalid value '{result}', valid values: {sorted(RESULTS)}")
    if not payload.get("summary"):
        errors.append("payload.summary is required")
    next_phase = payload.get("next_phase")
    if result == "success" and next_phase != NEXT_PHASE:
        errors.append(f"payload.next_phase must be '{NEXT_PHASE}' when result=success")
    if result == "partial":
        if next_phase is not None:
            errors.append("payload.next_phase must be null when result=partial")
        if not isinstance(payload.get("checkpoint"), dict):
            errors.append("payload.checkpoint is required when result=partial")
    if result == "failed" and next_phase is not None:
        errors.append("payload.next_phase must be null when result=failed")

    runtime_context = None
    if require_runtime_context:
        runtime_context = validate_runtime_context(
            payload.get("runtime_context"),
            errors,
            data.get("session_id") if "payload" in data else None,
        )

    manifest = payload.get("manifest_content")
    if not isinstance(manifest, dict):
        errors.append("payload.manifest_content must be an object")
    else:
        if manifest.get("phase") != PHASE:
            errors.append(f"payload.manifest_content.phase must be '{PHASE}'")
        draft_like = {
            "protocol_version": PROTOCOL_VERSION,
            "session_id": data.get("session_id", "phase-complete-validation"),
            "source_phase": "analyze",
            "upstream_manifest": {
                "schema_version": manifest.get("schema_version"),
                "phase": "analyze",
                "project_name": manifest.get("project_name"),
                "requirements": manifest.get("requirements"),
                "devices": manifest.get("devices"),
            },
            "selected_board": manifest.get("hardware_selection", {}).get("selected_board", {}),
            "hardware_plan": {
                "mcu": manifest.get("mcu"),
                "pinout": manifest.get("pinout"),
                "pin_decisions": manifest.get("pin_decisions"),
                "pin_review": manifest.get("pin_review"),
                "bom": manifest.get("bom"),
                "estimated_total_yuan": manifest.get("estimated_total_yuan"),
            },
        }
        manifest_errors, manifest_warnings, normalized = validate_draft(
            draft_like,
            board_root,
            strict_board_pins=strict_board_pins,
            require_pin_review_confirmed=result == "success",
            phase_timestamp=review_phase_timestamp if result == "success" else None,
        )
        errors.extend(f"manifest_content: {item}" for item in manifest_errors)
        warnings.extend(f"manifest_content: {item}" for item in manifest_warnings)
        if compare_manifest is not None and core_manifest(compare_manifest) != core_manifest(manifest):
            errors.append("payload.manifest_content core fields differ from compare manifest")

    validate_artifacts(payload.get("artifacts"), errors, artifact_root, runtime_context)
    if expected_artifacts:
        validate_expected_artifacts(payload.get("artifacts"), expected_artifacts, errors)
    if not isinstance(payload.get("warnings"), list):
        errors.append("payload.warnings must be an array")
    if not isinstance(payload.get("errors"), list):
        errors.append("payload.errors must be an array")
    validate_structured_errors(payload.get("structured_errors"), errors)
    return errors, warnings


def validate_manifest_content(
    data: dict[str, Any],
    board_root: Path | None = None,
    *,
    strict_board_pins: bool = False,
) -> tuple[list[str], list[str]]:
    envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "msg_id": "manifest-content-validation",
        "session_id": "manifest-content-validation",
        "phase": PHASE,
        "timestamp": utc_now(),
        "type": "phase_complete",
        "payload": {
            "phase": PHASE,
            "result": "success",
            "summary": "manifest_content validation wrapper",
            "next_phase": NEXT_PHASE,
            "manifest_content": data,
            "artifacts": [],
            "warnings": [],
            "errors": [],
            "structured_errors": [],
        },
    }
    return validate_phase_complete(
        envelope,
        data,
        None,
        board_root,
        None,
        strict_board_pins=strict_board_pins,
        enforce_pin_review_timing=False,
        require_runtime_context=False,
    )


def maybe_write_manifest(manifest: dict[str, Any], write_path: str | None) -> str | None:
    if not write_path:
        return None
    path = Path(write_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and normalize select-hw manifest draft")
    parser.add_argument("--input", default=None, help="input JSON file path")
    parser.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    parser.add_argument("--write-path", default=None, help="optional output file path")
    parser.add_argument("--validate-phase-complete", action="store_true", help="validate a phase_complete message")
    parser.add_argument("--validate-manifest-content", action="store_true", help="validate normalized select-hw manifest_content")
    parser.add_argument("--compare-manifest", default=None, help="compare phase_complete manifest_content core fields with this manifest")
    parser.add_argument("--artifact-root", default=None, help="root directory for validating file_list artifact paths")
    parser.add_argument("--board-root", default=str(DEFAULT_BOARD_ROOT), help="board definition root directory")
    parser.add_argument("--strict-board-pins", action="store_true", help="treat risky board pin usage and default bus deviations as errors")
    parser.add_argument("--expected-artifact", action="append", default=[], help="expected file_list artifact path; may be repeated")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        data = load_input(args)
    except Exception as exc:  # noqa: BLE001
        emit_json(
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
        compare_manifest = None
        if args.compare_manifest:
            try:
                with open(args.compare_manifest, "r", encoding="utf-8-sig") as f:
                    compare_manifest = json.load(f)
            except Exception as exc:  # noqa: BLE001
                emit_json(
                    {
                        "status": "fail",
                        "errors": [f"compare manifest load failed: {exc}"],
                        "warnings": [],
                    },
                    1,
                )
        artifact_root = Path(args.artifact_root) if args.artifact_root else None
        board_root = Path(args.board_root) if args.board_root else None
        errors, warnings = validate_phase_complete(
            data,
            compare_manifest,
            artifact_root,
            board_root,
            args.expected_artifact,
            strict_board_pins=args.strict_board_pins,
        )
        emit_json(
            {
                "status": "fail" if errors else "ok",
                "errors": errors,
                "warnings": warnings,
            },
            1 if errors else 0,
        )

    if args.validate_manifest_content:
        board_root = Path(args.board_root) if args.board_root else None
        errors, warnings = validate_manifest_content(
            data,
            board_root,
            strict_board_pins=args.strict_board_pins,
        )
        emit_json(
            {
                "status": "fail" if errors else "ok",
                "errors": errors,
                "warnings": warnings,
            },
            1 if errors else 0,
        )

    board_root = Path(args.board_root) if args.board_root else None
    errors, warnings, manifest = validate_draft(
        data,
        board_root,
        strict_board_pins=args.strict_board_pins,
    )
    if errors:
        emit_json(
            {
                "status": "fail",
                "errors": errors,
                "warnings": warnings,
                "manifest": None,
                "written_path": None,
            },
            1,
        )

    assert manifest is not None
    try:
        written_path = maybe_write_manifest(manifest, args.write_path)
    except Exception as exc:  # noqa: BLE001
        emit_json(
            {
                "status": "fail",
                "errors": [f"write failed: {exc}"],
                "warnings": warnings,
                "manifest": manifest,
                "written_path": None,
            },
            1,
        )

    emit_json(
        {
            "status": "ok",
            "errors": [],
            "warnings": warnings,
            "manifest": manifest,
            "written_path": written_path,
        },
        0,
    )


if __name__ == "__main__":
    main()
