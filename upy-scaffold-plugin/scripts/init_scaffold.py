#!/usr/bin/env python3
"""Render upy-scaffold file_operation payloads.

The plugin workflow keeps filesystem writes on the plugin side. This script
reads a select-hw manifest and writes a JSON description of directories and
files to stdout. It never writes the target project directory.

Examples:
  python init_scaffold.py --mode timer --manifest - < project-manifest.json
  python init_scaffold.py --mode async --manifest manifest.json --modules logger,flash_device
  python init_scaffold.py --mode incremental --new-devices '[{"name":"DHT22"}]'
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parent
TEMPLATES_DIR = SKILL_ROOT / "templates"
FIRMWARE_TEMPLATES_DIR = TEMPLATES_DIR / "firmware"
TOOLCHAIN_SPEC_DIR = REPO_ROOT / "upy-project-gen-toolchain-spec"
UPY_GENERATE_PLUGIN_DIR = REPO_ROOT / "upy-generate-plugin"
UPY_GENERATE_DIR = REPO_ROOT / "upy-generate"
UPY_WIRING_PLUGIN_DIR = REPO_ROOT / "upy-wiring-plugin"
UPY_WIRING_DIR = REPO_ROOT / "upy-wiring"
UPY_DIAGRAM_PLUGIN_DIR = REPO_ROOT / "upy-diagram-plugin"
UPY_DIAGRAM_DIR = REPO_ROOT / "upy-diagram"
UPY_GEN_DRIVER_PLUGIN_DIR = REPO_ROOT / "upy-gen-driver-plugin"
UPY_GEN_DRIVER_DIR = REPO_ROOT / "upy-gen-driver"
UPY_AUTOFIX_PLUGIN_DIR = REPO_ROOT / "upy-autofix-plugin"
UPY_AUTOFIX_DIR = REPO_ROOT / "upy-autofix"

DEFAULT_MODULES = {"logger", "time_helper", "maintenance", "flash_device", "log_tools"}

MODULE_ALIASES = {
    "module_logger": "logger",
    "logger": "logger",
    "logging": "logger",
    "module_flash": "flash_device",
    "flash": "flash_device",
    "flash_device": "flash_device",
    "deploy": "flash_device",
    "module_time_helper": "time_helper",
    "time_helper": "time_helper",
    "timer_helper": "time_helper",
    "module_maintenance": "maintenance",
    "maintenance": "maintenance",
    "module_log_tools": "log_tools",
    "log_tools": "log_tools",
    "read_device_log": "log_tools",
}

MCU_DEFAULTS = {
    "ESP32-C6": {
        "I2C": {0: {"SDA": 19, "SCL": 20}},
        "FIXED": {},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [8, 9],
        "INPUT_ONLY": [],
    },
    "ESP32-C3": {
        "I2C": {0: {"SDA": 8, "SCL": 9}},
        "FIXED": {},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [2, 8, 9],
        "INPUT_ONLY": [],
    },
    "ESP32-S3": {
        "I2C": {0: {"SDA": 8, "SCL": 9}},
        "FIXED": {},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [0, 3, 45, 46],
        "INPUT_ONLY": [],
    },
    "ESP32-S2": {
        "I2C": {0: {"SDA": 8, "SCL": 9}},
        "FIXED": {},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [0, 45, 46],
        "INPUT_ONLY": [],
    },
    "ESP32": {
        "I2C": {0: {"SDA": 21, "SCL": 22}},
        "FIXED": {},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [6, 7, 8, 9, 10, 11],
        "BOOT_SENSITIVE": [0, 2, 5, 12, 15],
        "INPUT_ONLY": [34, 35, 36, 37, 38, 39],
    },
    "ESP8266": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": 2},
        "UART_BAUD": 115200,
        "I2C_FREQ": 100000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [0, 1, 2, 15],
        "INPUT_ONLY": [],
    },
    "PICO 2 W": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": "WL_GPIO0"},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [],
        "INPUT_ONLY": [],
    },
    "PICO W": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": "WL_GPIO0"},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [],
        "INPUT_ONLY": [],
    },
    "PICO 2": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": 25},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [],
        "INPUT_ONLY": [],
    },
    "PICO": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": 25},
        "UART_BAUD": 115200,
        "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [],
        "INPUT_ONLY": [],
    },
}

CN_NAME_MAP = {
    "有源蜂鸣器": "buzzer",
    "无源蜂鸣器": "buzzer",
    "蜂鸣器": "buzzer",
    "温湿度传感器": "temp_hum_sensor",
    "温度传感器": "temperature_sensor",
    "湿度传感器": "humidity_sensor",
    "气压传感器": "pressure_sensor",
    "显示屏": "display",
    "屏幕": "display",
    "按键": "button",
    "按钮": "button",
    "继电器": "relay",
    "红外传感器": "ir_sensor",
    "人体传感器": "pir_sensor",
    "电机": "motor",
    "舵机": "servo",
    "指示灯": "led",
    "触摸传感器": "touch_sensor",
    "麦克风": "microphone",
    "功放": "amplifier",
}


def fallback_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    fixed = os.environ.get("UPY_WORKFLOW_UTC_NOW", "").strip()
    if fixed:
        return fixed
    helper = TOOLCHAIN_SPEC_DIR / "scripts" / "workflow_time.py"
    if helper.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(helper), "--json"],
                text=True,
                capture_output=True,
                encoding="utf-8",
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                payload = json.loads(result.stdout)
                value = payload.get("utc")
                if isinstance(value, str) and value:
                    return value
        except Exception:
            pass
    return fallback_utc_now()


def parse_gpio(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    text = str(value).strip().upper()
    if text.isdigit():
        return int(text)
    if text.startswith("GPIO") or text.startswith("GP"):
        match = re.search(r"(\d+)", text)
        if match:
            return int(match.group(1))
    return None


def bus_index(value: Any) -> int:
    match = re.search(r"(\d+)$", str(value or "0"))
    return int(match.group(1)) if match else 0


def safe_var_name(name: Any) -> str:
    text = str(name or "device")
    for cn, en in CN_NAME_MAP.items():
        if cn in text:
            return en
    ascii_name = text.encode("ascii", errors="ignore").decode("ascii")
    ascii_name = re.sub(r"[^a-zA-Z0-9_]", "_", ascii_name)
    ascii_name = re.sub(r"_+", "_", ascii_name).strip("_").lower()
    return ascii_name or "device"


def unique_name(base: str, used: Set[str]) -> str:
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def py_literal(value: Any, *, indent: int = 0) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=4)
    if indent <= 0:
        return text
    return text.replace("\n", "\n" + (" " * indent))


def strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def json_loads_or_file(value: str, default: Any) -> Any:
    if value is None or value == "":
        return default
    stripped = value.strip()
    if stripped == "":
        return default
    if stripped[0] in "[{":
        return json.loads(stripped)
    path = Path(stripped)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    if "," in stripped:
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return stripped


def load_manifest(value: str) -> Dict[str, Any]:
    if value == "-":
        stdin_buffer = getattr(sys.stdin, "buffer", None)
        if stdin_buffer is not None:
            text = stdin_buffer.read().decode("utf-8-sig")
        else:
            text = sys.stdin.read()
        if not text.strip():
            return {}
        return json.loads(text)
    path = Path(value)
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def clean_unicode(value: Any) -> Any:
    if isinstance(value, str):
        return value.encode("utf-8", errors="ignore").decode("utf-8")
    if isinstance(value, list):
        return [clean_unicode(item) for item in value]
    if isinstance(value, dict):
        return {clean_unicode(key): clean_unicode(item) for key, item in value.items()}
    return value


def merge_firmware_flash(manifest: Dict[str, Any], firmware: Any) -> Dict[str, Any]:
    result = deepcopy(manifest)
    if isinstance(firmware, dict):
        merged = deepcopy(result.get("firmware_flash")) if isinstance(result.get("firmware_flash"), dict) else {}
        merged.update(deepcopy(firmware))
        result["firmware_flash"] = merged
    return result


def unwrap_manifest(value: Dict[str, Any]) -> Dict[str, Any]:
    """Accept manifest_content directly, or unwrap common protocol envelopes."""
    if not isinstance(value, dict):
        raise ValueError("manifest input must be a JSON object")
    if "schema_version" in value and ("mcu" in value or "devices" in value):
        return value

    payload = value.get("payload")
    if isinstance(payload, dict):
        manifest_content = payload.get("manifest_content")
        if isinstance(manifest_content, dict):
            return merge_firmware_flash(manifest_content, payload.get("firmware"))
        manifest = payload.get("manifest")
        if isinstance(manifest, dict):
            return merge_firmware_flash(manifest, payload.get("firmware"))
        source_phase_complete = payload.get("source_phase_complete")
        if isinstance(source_phase_complete, dict):
            return merge_firmware_flash(unwrap_manifest(source_phase_complete), payload.get("firmware"))

    manifest_content = value.get("manifest_content")
    if isinstance(manifest_content, dict):
        return merge_firmware_flash(manifest_content, value.get("firmware"))
    manifest = value.get("manifest")
    if isinstance(manifest, dict):
        return merge_firmware_flash(manifest, value.get("firmware"))
    return merge_firmware_flash(value, value.get("firmware"))


def normalize_modules(value: str) -> Set[str]:
    if value is None or value.strip() == "":
        return set(DEFAULT_MODULES)
    raw = json_loads_or_file(value, [])
    if isinstance(raw, str):
        raw_items = [raw]
    else:
        raw_items = list(raw)
    if any(str(item).strip().lower() in {"all", "*"} for item in raw_items):
        return set(DEFAULT_MODULES)
    if any(str(item).strip().lower() in {"none", "minimal"} for item in raw_items):
        return set()
    modules: Set[str] = set()
    for item in raw_items:
        key = str(item).strip().lower().replace("-", "_")
        if key.startswith("mode_"):
            continue
        normalized = MODULE_ALIASES.get(key)
        if normalized:
            modules.add(normalized)
    return modules


def normalize_path(path: str) -> str:
    cleaned = str(path).replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        raise ValueError(f"path must be relative: {path}")
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError(f"path must not contain '..': {path}")
    if not parts:
        raise ValueError("path must not be empty")
    return "/".join(parts)


def file_payload(path: str, content: str, encoding: str = "utf-8") -> Dict[str, str]:
    return {"path": normalize_path(path), "content": strip_bom(content), "encoding": encoding}


def read_text(path: Path) -> str:
    return strip_bom(path.read_text(encoding="utf-8-sig"))


def protocol_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def optional_resource_warning(dest: str, candidates: Sequence[Path]) -> Dict[str, Any]:
    return {
        "code": "OPTIONAL_RESOURCE_MISSING",
        "severity": "warning",
        "blocking": False,
        "resource": normalize_path(dest),
        "source_candidates": [protocol_path(path) for path in candidates],
    }


def add_copy(files: List[Dict[str, str]], src: Path, dest: str, warnings: List[Any]) -> None:
    if src.exists():
        files.append(file_payload(dest, read_text(src)))
    else:
        warnings.append(optional_resource_warning(dest, [src]))


def add_template_copy(
    files: List[Dict[str, str]],
    src: Path,
    dest: str,
    warnings: List[Any],
    variables: Dict[str, str],
) -> None:
    if src.exists():
        files.append(file_payload(dest, Template(read_text(src)).safe_substitute(variables)))
    else:
        warnings.append(optional_resource_warning(dest, [src]))


def render_template(name: str, variables: Dict[str, str]) -> str:
    path = FIRMWARE_TEMPLATES_DIR / name
    template = Template(read_text(path))
    return template.safe_substitute(variables)


def get_mcu_defaults(model: str) -> Dict[str, Any]:
    upper = str(model or "").upper()
    for key, defaults in MCU_DEFAULTS.items():
        if key in upper:
            return defaults
    return MCU_DEFAULTS["ESP32"]


def extract_i2c_pins(manifest: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[int, Dict[str, int]]:
    buses: Dict[int, Dict[str, int]] = {}
    for item in manifest.get("pinout", []) or []:
        gpio = parse_gpio(item.get("gpio"))
        if gpio is None:
            continue
        pin_name = str(item.get("pin_name", "")).upper()
        if "SDA" not in pin_name and "SCL" not in pin_name:
            continue
        idx = bus_index(item.get("bus", "0"))
        buses.setdefault(idx, {})
        if "SDA" in pin_name:
            buses[idx]["SDA"] = gpio
        if "SCL" in pin_name:
            buses[idx]["SCL"] = gpio
    if not buses:
        return deepcopy(defaults.get("I2C", {0: {"SDA": 21, "SCL": 22}}))
    return buses


def i2c_pins_block(i2c_pins: Dict[int, Dict[str, int]]) -> str:
    lines: List[str] = []
    for idx, pins in sorted(i2c_pins.items()):
        lines.append(f"                {idx}: {{")
        if "SDA" in pins:
            lines.append(f'                    "SDA": {pins["SDA"]},')
        if "SCL" in pins:
            lines.append(f'                    "SCL": {pins["SCL"]},')
        lines.append("                },")
    return "\n".join(lines) if lines else "                # No I2C pins declared"


def fixed_pins_block(defaults: Dict[str, Any]) -> str:
    fixed = defaults.get("FIXED", {})
    if not fixed:
        return "            # No fixed pins declared"
    return "\n".join(f'            "{name}": {pin!r},' for name, pin in fixed.items())


def extract_gpio_inits(manifest: Dict[str, Any]) -> str:
    lines: List[str] = []
    used: Set[str] = set()
    for item in manifest.get("pinout", []) or []:
        gpio = parse_gpio(item.get("gpio"))
        if gpio is None:
            continue
        pin_type = str(item.get("type", "")).lower()
        interface = str(item.get("interface", "")).lower()
        pin_name = str(item.get("pin_name", "")).lower()
        if not (pin_type.startswith("gpio") or interface == "gpio"):
            continue
        if "out" in pin_type or pin_name in {"out", "do", "data", "din", "gain", "sd"}:
            direction = "Pin.OUT"
        elif "in" in pin_type:
            direction = "Pin.IN"
        else:
            direction = "Pin.OUT"
        base = safe_var_name(f"{item.get('device', 'device')}_{item.get('pin_name', 'pin')}_pin")
        var_name = unique_name(base, used)
        lines.append(f"{var_name} = Pin({gpio}, {direction})")
        lines.append(f"_ = {var_name}")
    return "\n".join(lines) if lines else "# No standalone GPIO pins declared"


def extract_i2c_inits(i2c_pins: Dict[int, Dict[str, int]], defaults: Dict[str, Any]) -> str:
    lines: List[str] = []
    freq = defaults.get("I2C_FREQ", 400000)
    for idx, pins in sorted(i2c_pins.items()):
        sda = pins.get("SDA")
        scl = pins.get("SCL")
        if sda is None or scl is None:
            lines.append(f"# I2C{idx} incomplete: {pins}")
            continue
        lines.append(f"i2c{idx} = I2C({idx}, scl=Pin({scl}), sda=Pin({sda}), freq={freq})")
        lines.append(f"_ = i2c{idx}.scan()")
    return "\n".join(lines) if lines else "# No I2C bus declared"


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else "" for line in text.splitlines())


def sample_interval_ms(manifest: Dict[str, Any]) -> int:
    sample_rate = str((manifest.get("requirements") or {}).get("sample_rate", "normal_1hz"))
    mapping = {
        "normal_1hz": 1000,
        "high_100hz_plus": 10,
        "low_minute": 60000,
        "triggered": 100,
    }
    return mapping.get(sample_rate, 1000)


def bom_table_rows(manifest: Dict[str, Any]) -> str:
    rows: List[str] = []
    for index, item in enumerate(manifest.get("bom", []) or [], start=1):
        rows.append(
            "| {} | {} | {} | {} | {} |".format(
                index,
                item.get("name", "?"),
                item.get("model", "?"),
                item.get("quantity", 1),
                item.get("unit_price_yuan", "?"),
            )
        )
    return "\n".join(rows) if rows else "| - | No BOM data | - | - | - |"


def pinout_table_rows(manifest: Dict[str, Any]) -> str:
    rows: List[str] = []
    for item in manifest.get("pinout", []) or []:
        rows.append(
            "| {} | {} | {} | {} | {} |".format(
                item.get("device", "?"),
                item.get("pin_name", "?"),
                item.get("gpio", "?"),
                item.get("bus", ""),
                item.get("i2c_addr", ""),
            )
        )
    return "\n".join(rows) if rows else "| - | No pinout data | - | - | - |"


def total_price(manifest: Dict[str, Any]) -> Any:
    if "estimated_total_yuan" in manifest:
        return manifest.get("estimated_total_yuan")
    total = 0
    has_price = False
    for item in manifest.get("bom", []) or []:
        price = item.get("unit_price_yuan")
        qty = item.get("quantity", 1)
        if isinstance(price, (int, float)) and isinstance(qty, (int, float)):
            total += price * qty
            has_price = True
    return total if has_price else "N/A"


def logger_blocks(modules: Set[str]) -> Dict[str, str]:
    if "logger" not in modules:
        return {
            "LOGGER_IMPORTS": "",
            "LOGGER_HELPERS_BLOCK": (
                "def _log_info(message):\n"
                "    print(message)\n"
                "\n"
                "\n"
                "def _log_exception(exc, message):\n"
                "    print(message)\n"
                "    sys.print_exception(exc)"
            ),
            "LOGGER_SETUP_BLOCK": "# Logger module not selected",
            "LOG_BOOT_BLOCK": '_log_info("[OK] {} booting".format(conf.PROJECT_NAME))',
            "ASYNC_LOG_BOOT_BLOCK": '_log_info("[OK] {} booting (asyncio)".format(conf.PROJECT_NAME))',
            "THREAD_LOG_BOOT_BLOCK": '_log_info("[OK] {} booting (thread)".format(conf.PROJECT_NAME))',
        }
    return {
        "LOGGER_IMPORTS": "from lib.logger import exception, info\nfrom lib.logger import install_rotating",
        "LOGGER_HELPERS_BLOCK": (
            "def _uptime_ms():\n"
            "    return time.ticks_ms()\n"
            "\n"
            "\n"
            "def _log_info(message):\n"
            "    stamped = \"[t={}ms] {}\".format(_uptime_ms(), message)\n"
            "    print(stamped)\n"
            "    info(stamped)\n"
            "\n"
            "\n"
            "def _log_exception(exc, message):\n"
            "    stamped = \"[t={}ms] {}\".format(_uptime_ms(), message)\n"
            "    print(stamped)\n"
            "    sys.print_exception(exc)\n"
            "    exception(exc, stamped)"
        ),
        "LOGGER_SETUP_BLOCK": "install_rotating(conf.LOG_DIR, max_files=conf.LOG_FILES_MAX, lines_per_file=conf.LOG_LINES_PER_FILE)",
        "LOG_BOOT_BLOCK": '_log_info("{} booting".format(conf.PROJECT_NAME))',
        "ASYNC_LOG_BOOT_BLOCK": '_log_info("{} booting (asyncio)".format(conf.PROJECT_NAME))',
        "THREAD_LOG_BOOT_BLOCK": '_log_info("{} booting (thread)".format(conf.PROJECT_NAME))',
    }


def maintenance_blocks(modules: Set[str]) -> Dict[str, str]:
    if "maintenance" not in modules:
        return {
            "MAINTENANCE_IMPORT": "",
            "MAINTENANCE_TIMER_ARG": "",
            "MAINTENANCE_ASYNC_BLOCK": "        # Maintenance module not selected",
            "MAINTENANCE_THREAD_BLOCK": "        # Maintenance module not selected",
        }
    return {
        "MAINTENANCE_IMPORT": "from tasks.maintenance import maintenance_tick",
        "MAINTENANCE_TIMER_ARG": ", idle_cb=maintenance_tick",
        "MAINTENANCE_ASYNC_BLOCK": "        maintenance_tick()",
        "MAINTENANCE_THREAD_BLOCK": "        maintenance_tick()",
    }


def scheduler_timer_id_for_model(model: Any) -> int:
    """Return a port-safe Timer id for the scaffold Scheduler entrypoint."""
    upper = str(model or "").upper().replace("_", "-")
    if "PICO" in upper or "RP2" in upper or "RP2040" in upper or "RP2350" in upper:
        return -1
    if "ZEPHYR" in upper:
        return -1
    return 0


def micropython_version_label(manifest: Dict[str, Any]) -> str:
    candidates = []
    firmware_flash = manifest.get("firmware_flash")
    if isinstance(firmware_flash, dict):
        candidates.extend([firmware_flash.get("latest_version"), firmware_flash.get("version")])
    firmware = manifest.get("firmware")
    if isinstance(firmware, dict):
        candidates.extend([firmware.get("latest_version"), firmware.get("version")])
    mcu = manifest.get("mcu")
    if isinstance(mcu, dict):
        candidates.extend([mcu.get("firmware_version"), mcu.get("micropython_version")])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            version = candidate.strip()
            if version.lower().startswith("micropython"):
                return version
            return f"MicroPython {version}"
    return "MicroPython"


def template_variables(manifest: Dict[str, Any], mode: str, modules: Set[str]) -> Dict[str, str]:
    mcu = manifest.get("mcu") or {}
    model = mcu.get("model") or mcu.get("mcu") or "ESP32"
    board_id = mcu.get("board_id") or str(model).lower().replace(" ", "_").replace("-", "_")
    defaults = get_mcu_defaults(model)
    i2c_pins = extract_i2c_pins(manifest, defaults)
    scheduler_init_args = f"timer_id={scheduler_timer_id_for_model(model)}, tick_ms=100"
    if "maintenance" in modules:
        scheduler_init_args += ", idle_cb=maintenance_tick"
    variables = {
        "GENERATED_AT": utc_now(),
        "MICROPYTHON_VERSION_LABEL": micropython_version_label(manifest),
        "PROJECT_NAME": str(manifest.get("project_name", "untitled")),
        "PROJECT_NAME_LITERAL": json.dumps(str(manifest.get("project_name", "untitled")), ensure_ascii=False),
        "MODE": mode,
        "MCU_MODEL": str(model),
        "MCU_BOARD": str(mcu.get("display_name") or mcu.get("board") or mcu.get("board_id") or model),
        "BOARD_ID": str(board_id),
        "FIRMWARE_URL": str(mcu.get("firmware_url", "N/A")),
        "FW_VERSION": "0.1.0",
        "SAMPLE_INTERVAL_MS": str(sample_interval_ms(manifest)),
        "LOG_DIR": "/log",
        "LOG_LEVEL": "INFO",
        "I2C_FREQ": str(defaults.get("I2C_FREQ", 400000)),
        "UART_BAUD": str(defaults.get("UART_BAUD", 115200)),
        "I2C_PINS_BLOCK": i2c_pins_block(i2c_pins),
        "FIXED_PINS_BLOCK": fixed_pins_block(defaults),
        "BOOT_SENSITIVE_LIST": py_literal(defaults.get("BOOT_SENSITIVE", []), indent=26),
        "FLASH_PINS_LIST": py_literal(defaults.get("FLASH_PINS", []), indent=22),
        "INPUT_ONLY_LIST": py_literal(defaults.get("INPUT_ONLY", []), indent=21),
        "PINOUT_LIST": py_literal(manifest.get("pinout", []) or [], indent=18),
        "I2C_INIT_BLOCK": extract_i2c_inits(i2c_pins, defaults),
        "GPIO_INIT_BLOCK": extract_gpio_inits(manifest),
        "I2C_INIT_BLOCK_IN_MAIN": indent_block(extract_i2c_inits(i2c_pins, defaults), 4),
        "GPIO_INIT_BLOCK_IN_MAIN": indent_block(extract_gpio_inits(manifest), 4),
        "SCHEDULER_INIT_ARGS": scheduler_init_args,
        "BOM_TABLE_ROWS": bom_table_rows(manifest),
        "PINOUT_TABLE_ROWS": pinout_table_rows(manifest),
        "TOTAL_PRICE": str(total_price(manifest)),
    }
    variables.update(logger_blocks(modules))
    variables.update(maintenance_blocks(modules))
    return variables


def driver_stub(device: Dict[str, Any]) -> str:
    name = device.get("name", "device")
    driver = device.get("driver") or {}
    return "\n".join(
        [
            f"# {name} driver stub",
            f"# Source: {driver.get('source', 'unknown')}",
            f"# Install: {driver.get('install_cmd', 'N/A')}",
            "# TODO: upy-generate-plugin fills this package with device driver glue.",
            "",
        ]
    )


def should_generate_driver_stub(device: Dict[str, Any]) -> bool:
    source = str((device.get("driver") or {}).get("source", "unknown")).lower()
    return source != "none"


def generate_driver_files(
    devices: Sequence[Dict[str, Any]],
    *,
    include_placeholder: bool = True,
    force_stubs: bool = False,
) -> List[Dict[str, str]]:
    files: List[Dict[str, str]] = []
    used: Set[str] = set()
    for device in devices:
        if not isinstance(device, dict):
            continue
        if not force_stubs and not should_generate_driver_stub(device):
            continue
        base = safe_var_name(device.get("name", "device"))
        name = unique_name(base, used)
        files.append(file_payload(f"firmware/drivers/{name}_driver/__init__.py", driver_stub(device)))
    if include_placeholder and not files:
        files.append(file_payload("firmware/drivers/.gitkeep", ""))
    return files


def generate_flake8() -> str:
    return """[flake8]
max-line-length = 120
builtins =
    const
extend-ignore =
    W503
per-file-ignores =
    firmware/main_thread.py: F401
    firmware/lib/logger/__init__.py: F401
    firmware/lib/scheduler/__init__.py: F401

[pycodestyle]
max-line-length = 120
ignore = W503
"""


def generate_license() -> str:
    year = datetime.now(timezone.utc).year
    return f"""MIT License

Copyright (c) {year}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def add_module_files(
    files: List[Dict[str, str]],
    mode: str,
    modules: Set[str],
    warnings: List[Any],
    variables: Dict[str, str],
) -> None:
    if "logger" in modules:
        add_copy(files, TEMPLATES_DIR / "lib" / "logger" / "logging.py", "firmware/lib/logger/logging.py", warnings)
        add_copy(
            files,
            TEMPLATES_DIR / "lib" / "logger" / "rotating_logger.py",
            "firmware/lib/logger/rotating_logger.py",
            warnings,
        )
        add_copy(files, TEMPLATES_DIR / "lib" / "logger" / "__init__.py", "firmware/lib/logger/__init__.py", warnings)

    if "time_helper" in modules:
        add_copy(files, TEMPLATES_DIR / "lib" / "time_helper.py", "firmware/lib/time_helper.py", warnings)

    if mode == "timer":
        add_template_copy(
            files,
            TEMPLATES_DIR / "lib" / "scheduler" / "timer_sched.py",
            "firmware/lib/scheduler/timer_sched.py",
            warnings,
            variables,
        )
        files.append(file_payload("firmware/lib/scheduler/__init__.py", "# Scheduler package\nfrom .timer_sched import Scheduler\n"))

    if "maintenance" in modules:
        add_copy(files, TEMPLATES_DIR / "tasks" / "maintenance.py", "firmware/tasks/maintenance.py", warnings)
        files.append(file_payload("firmware/tasks/__init__.py", "# Tasks package\n"))

    if "flash_device" in modules:
        add_copy(files, TEMPLATES_DIR / "pc" / "flash_device.py", "tools/flash_device.py", warnings)

    if "log_tools" in modules:
        add_copy(files, TEMPLATES_DIR / "pc" / "read_device_log.py", "tools/read_device_log.py", warnings)
        add_copy(files, TEMPLATES_DIR / "pc" / "log_report.py", "tools/log_report.py", warnings)


def add_upy_resource(
    files: List[Dict[str, str]],
    dest: str,
    candidates: Sequence[Path],
    warnings: List[str],
    *,
    required: bool,
) -> None:
    for src in candidates:
        if src.exists():
            files.append(file_payload(dest, read_text(src)))
            return
    if required:
        checked = ", ".join(str(path) for path in candidates)
        message = f"resource missing: {dest} (checked: {checked})"
        raise FileNotFoundError(message)
    warnings.append(optional_resource_warning(dest, candidates))


def add_upy_resources(files: List[Dict[str, str]], warnings: List[str]) -> None:
    resources = [
        {
            "dest": ".upy/schemas/project-manifest.schema.json",
            "required": True,
            "candidates": [TOOLCHAIN_SPEC_DIR / "project-manifest.schema.json"],
        },
        {
            "dest": ".upy/schemas/wiring.schema.json",
            "required": False,
            "candidates": [TOOLCHAIN_SPEC_DIR / "wiring.schema.json"],
        },
        {
            "dest": ".upy/schemas/diagram.schema.json",
            "required": False,
            "candidates": [TOOLCHAIN_SPEC_DIR / "diagram.schema.json"],
        },
        {
            "dest": ".upy/schemas/diagnostic_bundle.schema.json",
            "required": False,
            "candidates": [
                UPY_AUTOFIX_PLUGIN_DIR / "templates" / "diagnostic_bundle_schema.json",
                UPY_AUTOFIX_DIR / "templates" / "diagnostic_bundle_schema.json",
            ],
        },
        {
            "dest": ".upy/scripts/validate_json.py",
            "required": True,
            "candidates": [TOOLCHAIN_SPEC_DIR / "scripts" / "validate_json.py"],
        },
        {
            "dest": ".upy/scripts/download_drivers.py",
            "required": False,
            "candidates": [
                UPY_GENERATE_PLUGIN_DIR / "scripts" / "download_drivers.py",
                UPY_GENERATE_DIR / "scripts" / "download_drivers.py",
            ],
        },
        {
            "dest": ".upy/scripts/init_scaffold.py",
            "required": True,
            "candidates": [Path(__file__).resolve()],
        },
        {
            "dest": ".upy/scripts/render_wiring_local.py",
            "required": False,
            "candidates": [
                UPY_WIRING_PLUGIN_DIR / "scripts" / "render_wiring_local.py",
                UPY_WIRING_DIR / "scripts" / "render_wiring_local.py",
            ],
        },
        {
            "dest": ".upy/scripts/render_diagram_local.py",
            "required": False,
            "candidates": [
                UPY_DIAGRAM_PLUGIN_DIR / "scripts" / "render_diagram_local.py",
                UPY_DIAGRAM_DIR / "scripts" / "render_diagram_local.py",
            ],
        },
        {
            "dest": ".upy/scripts/extract_pdf.py",
            "required": False,
            "candidates": [
                UPY_GEN_DRIVER_PLUGIN_DIR / "scripts" / "extract_pdf.py",
                UPY_GEN_DRIVER_DIR / "scripts" / "extract_pdf.py",
            ],
        },
        {
            "dest": ".upy/scripts/convert_arduino.py",
            "required": False,
            "candidates": [
                UPY_GEN_DRIVER_PLUGIN_DIR / "scripts" / "convert_arduino.py",
                UPY_GEN_DRIVER_DIR / "scripts" / "convert_arduino.py",
            ],
        },
        {
            "dest": ".upy/scripts/flash_device.py",
            "required": False,
            "candidates": [TEMPLATES_DIR / "pc" / "flash_device.py"],
        },
        {
            "dest": ".upy/scripts/read_device_log.py",
            "required": False,
            "candidates": [TEMPLATES_DIR / "pc" / "read_device_log.py"],
        },
        {
            "dest": ".upy/scripts/run_on_device.py",
            "required": False,
            "candidates": [SKILL_ROOT / "scripts" / "run_on_device.py"],
        },
        {
            "dest": ".upy/scripts/hardware_sanity.py",
            "required": False,
            "candidates": [
                UPY_AUTOFIX_PLUGIN_DIR / "scripts" / "hardware_sanity.py",
                UPY_AUTOFIX_DIR / "scripts" / "hardware_sanity.py",
            ],
        },
        {
            "dest": ".upy/scripts/triage.py",
            "required": False,
            "candidates": [
                UPY_AUTOFIX_PLUGIN_DIR / "scripts" / "triage.py",
                UPY_AUTOFIX_DIR / "scripts" / "triage.py",
            ],
        },
        {
            "dest": ".upy/error_lib.json",
            "required": False,
            "candidates": [
                UPY_AUTOFIX_PLUGIN_DIR / "templates" / "error_lib.json",
                UPY_AUTOFIX_DIR / "templates" / "error_lib.json",
            ],
        },
    ]
    for resource in resources:
        add_upy_resource(
            files,
            resource["dest"],
            resource["candidates"],
            warnings,
            required=resource["required"],
        )


def normalize_custom_files(value: str) -> List[str]:
    raw = json_loads_or_file(value, [])
    if isinstance(raw, str):
        raw_items = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        raw_items = [str(item).strip() for item in raw if str(item).strip()]
    paths: List[str] = []
    for item in raw_items:
        normalized = normalize_path(item)
        if normalized.endswith("/"):
            normalized = normalized.rstrip("/") + "/.gitkeep"
        elif "." not in Path(normalized).name:
            normalized = normalized.rstrip("/") + "/.gitkeep"
        paths.append(normalized)
    return paths


def custom_file_content(path: str) -> str:
    if path.endswith(".py"):
        return "# TODO: custom file requested during scaffold configuration.\n"
    if path.endswith(".md"):
        return "# TODO\n"
    return ""


def add_placeholder_files(files: List[Dict[str, str]]) -> None:
    for path in [
        "docs/.gitkeep",
        "host/.gitkeep",
        "test/device/.gitkeep",
        "test/pc/.gitkeep",
        "build/firmware/.gitkeep",
        "build/mpy/.gitkeep",
        "firmware/assets/.gitkeep",
    ]:
        files.append(file_payload(path, ""))


def generate_gitignore() -> str:
    return (
        "__pycache__/\n"
        "*.pyc\n"
        "*.pyo\n"
        "build/mpy/\n"
        "build/mpy/**\n"
    )


def updated_manifest(manifest: Dict[str, Any], mode: str, modules: Set[str], custom_files: Sequence[str]) -> Dict[str, Any]:
    result = deepcopy(manifest)
    result["phase"] = "scaffold"
    result["domain_phase"] = "scaffold"
    result["final_status"] = "scaffolded"
    result["scaffold_mode"] = mode
    result["scaffold_modules"] = sorted(modules)
    if custom_files:
        result["scaffold_custom_files"] = list(custom_files)
    result["scaffold"] = {
        "mode": mode,
        "modules": sorted(modules),
        "custom_files": list(custom_files),
    }
    result["updated_at"] = utc_now()
    return result


def manifest_file(manifest_content: Dict[str, Any]) -> Dict[str, str]:
    content = json.dumps(manifest_content, ensure_ascii=False, indent=2)
    return file_payload("project-manifest.json", content + "\n")


def generate_full(manifest: Dict[str, Any], mode: str, modules: Set[str], custom_files: Sequence[str], warnings: List[Any]) -> Dict[str, Any]:
    if not manifest:
        raise ValueError("full scaffold requires a manifest object")
    phase = manifest.get("phase")
    if phase not in ("select-hw", "upy-flash-mpy-firmware-plugin", "scaffold"):
        warnings.append(
            {
                "code": "UNEXPECTED_MANIFEST_PHASE",
                "severity": "warning",
                "blocking": False,
                "phase": phase,
                "expected": ["select-hw", "upy-flash-mpy-firmware-plugin", "scaffold"],
            }
        )

    variables = template_variables(manifest, mode, modules)
    files: List[Dict[str, str]] = [
        file_payload("firmware/board.py", render_template("board.py.tmpl", variables)),
        file_payload("firmware/conf.py", render_template("conf.py.tmpl", variables)),
        file_payload("firmware/boot.py", render_template("boot.py.tmpl", variables)),
        file_payload("firmware/main.py", render_template(f"main_{mode}.py.tmpl", variables)),
        file_payload("README.md", render_template("README.md.tmpl", variables)),
    ]

    manifest_content = updated_manifest(manifest, mode, modules, custom_files)
    files.append(manifest_file(manifest_content))
    add_module_files(files, mode, modules, warnings, variables)
    files.extend(generate_driver_files(manifest.get("devices", []) or []))
    add_placeholder_files(files)
    add_upy_resources(files, warnings)
    files.append(file_payload(".gitignore", generate_gitignore()))
    files.append(file_payload(".flake8", generate_flake8()))
    files.append(file_payload("LICENSE", generate_license()))
    for path in custom_files:
        files.append(file_payload(path, custom_file_content(path)))

    return build_output("scaffold", mode, files, warnings, manifest_content)


def parse_new_devices(value: str) -> List[Dict[str, Any]]:
    parsed = json_loads_or_file(value, [])
    if isinstance(parsed, dict):
        return [parsed]
    if not isinstance(parsed, list):
        raise ValueError("--new-devices must be a JSON object or array")
    devices: List[Dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("--new-devices entries must be objects")
        devices.append(item)
    return devices


def generate_incremental(manifest: Dict[str, Any], new_devices: Sequence[Dict[str, Any]], warnings: List[Any]) -> Dict[str, Any]:
    if not new_devices:
        raise ValueError("incremental mode requires --new-devices")
    files = generate_driver_files(new_devices, include_placeholder=False, force_stubs=True)
    manifest_content = deepcopy(manifest) if manifest else {"phase": "scaffold"}
    existing = manifest_content.setdefault("devices", [])
    existing_names = {str(item.get("name")) for item in existing if isinstance(item, dict)}
    for device in new_devices:
        if str(device.get("name")) not in existing_names:
            existing.append(deepcopy(device))
    manifest_content["phase"] = "scaffold"
    manifest_content["domain_phase"] = "scaffold"
    manifest_content["final_status"] = "scaffolded"
    manifest_content["incremental"] = True
    manifest_content["generate_scope"] = "new_devices_only"
    manifest_content["updated_at"] = utc_now()
    files.append(manifest_file(manifest_content))
    return build_output("scaffold", "incremental", files, warnings, manifest_content)


def directory_chain(path: str) -> Iterable[str]:
    parts = normalize_path(path).split("/")[:-1]
    for index in range(1, len(parts) + 1):
        yield "/".join(parts[:index])


def infer_directories(files: Sequence[Dict[str, str]]) -> List[str]:
    directories: Set[str] = set()
    for item in files:
        for directory in directory_chain(item["path"]):
            directories.add(directory)
    return sorted(directories)


def build_file_tree(files: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    for item in files:
        parts = item["path"].split("/")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = "file"
    return root


def build_status_updates(mode: str, files: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    if mode == "incremental":
        driver_count = sum(1 for item in files if item["path"].startswith("firmware/drivers/"))
        return [
            {
                "step_id": "incremental_stub",
                "message": f"正在为 {driver_count} 个新器件生成 driver stub...",
                "level": "info",
            },
            {
                "step_id": "incremental_done",
                "message": f"增量 driver stub 已生成：{driver_count} 个文件",
                "level": "success",
            },
        ]

    driver_count = sum(
        1 for item in files
        if item["path"].startswith("firmware/drivers/") and item["path"].endswith("__init__.py")
    )
    return [
        {"step_id": "scaffold_start", "message": "正在生成项目骨架...", "level": "info"},
        {"step_id": "render_board", "message": "正在渲染 board.py（引脚映射 + 查询函数）...", "level": "info"},
        {"step_id": "render_conf", "message": "正在渲染 conf.py / boot.py...", "level": "info"},
        {"step_id": "render_main", "message": f"正在渲染 main.py (mode: {mode})...", "level": "info"},
        {"step_id": "copy_lib", "message": "正在复制 lib/ 基础库...", "level": "info"},
        {"step_id": "gen_drivers", "message": f"正在生成 drivers/ stub ({driver_count} 个器件)...", "level": "info"},
        {"step_id": "copy_tools", "message": "正在复制 tools/ 部署工具...", "level": "info"},
        {"step_id": "scaffold_done", "message": f"骨架生成完成：{len(files)} 个文件", "level": "success"},
    ]


def build_artifacts(files: Sequence[Dict[str, str]], file_tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "type": "file_tree",
            "title": "项目结构",
            "tree": file_tree,
        },
        {
            "type": "file_list",
            "title": "待写入文件",
            "files": [
                {
                    "path": item["path"],
                    "status": "pending",
                    "encoding": item.get("encoding", "utf-8"),
                }
                for item in files
            ],
        },
    ]


def build_file_operations(files: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    operations: List[Dict[str, Any]] = []
    for index, item in enumerate(files, start=1):
        operations.append(
            {
                "type": "file_operation",
                "payload": {
                    "op_id": f"scaffold_fo_{index:03d}",
                    "op": "write",
                    "path": item["path"],
                    "content": item["content"],
                    "encoding": item.get("encoding", "utf-8"),
                },
            }
        )
    return operations


def build_output(
    phase: str,
    mode: str,
    files: Sequence[Dict[str, str]],
    warnings: Sequence[Any],
    manifest_content: Dict[str, Any],
) -> Dict[str, Any]:
    directories = infer_directories(files)
    file_tree = build_file_tree(files)
    artifacts = build_artifacts(files, file_tree)
    summary = f"Generated {len(files)} files, {len(directories)} directories"
    next_phase = "upy-generate-plugin"
    changed_files = [item["path"] for item in files]
    phase_complete_payload = {
        "phase": phase,
        "domain_phase": phase,
        "result": "success",
        "summary": summary,
        "next_phase": next_phase,
        "artifacts": artifacts,
        "warnings": list(warnings),
        "errors": [],
        "structured_errors": [],
        "manifest_content": manifest_content,
    }
    if mode == "incremental":
        phase_complete_payload.update(
            {
                "incremental": True,
                "generate_scope": "new_devices_only",
                "changed_files": changed_files,
            }
        )
    return {
        "phase": phase,
        "domain_phase": phase,
        "mode": mode,
        "scaffold_mode": mode if mode != "incremental" else manifest_content.get("scaffold_mode"),
        "directories": directories,
        "files": list(files),
        "file_operations": build_file_operations(files),
        "summary": summary,
        "status_updates": build_status_updates(mode, files),
        "artifacts": artifacts,
        "warnings": list(warnings),
        "errors": [],
        "structured_errors": [],
        "file_tree": file_tree,
        "manifest_content": manifest_content,
        "phase_complete_payload": phase_complete_payload,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render MicroPython project scaffold JSON")
    parser.add_argument("--mode", default="timer", choices=["timer", "async", "thread", "incremental"])
    parser.add_argument("--manifest", default="-", help="manifest JSON path, or '-' for stdin")
    parser.add_argument("--modules", default="all", help="JSON array or comma list of selected module ids")
    parser.add_argument("--custom-files", default="[]", help="JSON array or comma list of extra relative paths")
    parser.add_argument("--new-devices", default="[]", help="JSON array for incremental mode")
    parser.add_argument("--project-dir", default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    warnings: List[str] = []
    if args.project_dir:
        warnings.append("--project-dir is ignored in plugin mode; script only writes JSON to stdout")

    try:
        manifest = unwrap_manifest(clean_unicode(load_manifest(args.manifest)))
        if args.mode == "incremental":
            output = generate_incremental(manifest, parse_new_devices(args.new_devices), warnings)
        else:
            modules = normalize_modules(args.modules)
            custom_files = normalize_custom_files(args.custom_files)
            output = generate_full(manifest, args.mode, modules, custom_files, warnings)
    except Exception as exc:
        print(f"init_scaffold.py: {exc}", file=sys.stderr)
        return 2

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
