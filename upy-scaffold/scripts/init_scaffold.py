#!/usr/bin/env python3
"""upy-scaffold 项目骨架生成脚本。

读取 project-manifest.json（phase: select-hw），生成完整的 firmware/ 项目骨架。

用法：
  python init_scaffold.py --project-dir G:/ai_project/test --mode timer
  python init_scaffold.py --project-dir G:/ai_project/test --mode async
  python init_scaffold.py --project-dir G:/ai_project/test --mode thread
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

# ── Template directory (relative to this script) ──
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
PROJECT_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "templates")

# ── Known MCU default pin mappings (fallback if pinout doesn't specify) ──
MCU_DEFAULTS = {
    "ESP32": {
        "I2C": {0: {"SDA": 21, "SCL": 22}},
        "FIXED": {},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [6, 7, 8, 9, 10, 11],
        "BOOT_SENSITIVE": [0, 2, 5, 12, 15],
        "INPUT_ONLY": [34, 35, 36, 37, 38, 39],
    },
    "ESP32-S3": {
        "I2C": {0: {"SDA": 8, "SCL": 9}},
        "FIXED": {},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [0, 3, 45, 46],
        "INPUT_ONLY": [],
    },
    "ESP32-C3": {
        "I2C": {0: {"SDA": 8, "SCL": 9}},
        "FIXED": {},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [2, 8, 9],
        "INPUT_ONLY": [],
    },
    "ESP32-S2": {
        "I2C": {0: {"SDA": 8, "SCL": 9}},
        "FIXED": {},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [0, 45, 46],
        "INPUT_ONLY": [],
    },
    "ESP32-C6": {
        "I2C": {0: {"SDA": 19, "SCL": 20}},
        "FIXED": {},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [8, 9],
        "INPUT_ONLY": [],
    },
    "ESP8266": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": 2},
        "UART_BAUD": 115200, "I2C_FREQ": 100000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [0, 1, 2, 15],
        "INPUT_ONLY": [],
    },
    "Pico": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": 25},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [],
        "INPUT_ONLY": [],
    },
    "Pico W": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": "WL_GPIO0"},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [],
        "INPUT_ONLY": [],
    },
    "Pico 2": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": 25},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [],
        "INPUT_ONLY": [],
    },
    "Pico 2 W": {
        "I2C": {0: {"SDA": 4, "SCL": 5}},
        "FIXED": {"LED": "WL_GPIO0"},
        "UART_BAUD": 115200, "I2C_FREQ": 400000,
        "FLASH_PINS": [],
        "BOOT_SENSITIVE": [],
        "INPUT_ONLY": [],
    },
}


def parse_gpio(gpio_str: str) -> int:
    """Parse GPIO string like 'GPIO21' or 'GP4' to integer."""
    m = re.search(r'(\d+)', str(gpio_str))
    return int(m.group(1)) if m else None


def scheduler_timer_id_for_model(model) -> int:
    """Return a port-safe Timer id for the Scheduler entrypoint."""
    upper = str(model or "").upper().replace("_", "-")
    if "PICO" in upper or "RP2" in upper or "RP2040" in upper or "RP2350" in upper:
        return -1
    if "ZEPHYR" in upper:
        return -1
    return 0


# Common Chinese-to-English device name mappings for variable naming
_CN_NAME_MAP = {
    "有源蜂鸣器": "buzzer",
    "无源蜂鸣器": "buzzer",
    "蜂鸣器": "buzzer",
    "温湿度传感器": "temp_hum_sensor",
    "气压传感器": "pressure_sensor",
    "显示屏": "display",
    "按键": "button",
    "按钮": "button",
    "继电器": "relay",
    "红外传感器": "ir_sensor",
    "电机": "motor",
    "舵机": "servo",
    "指示灯": "led",
    "面包板": "breadboard",
    "杜邦线": "dupont_wire",
}


def safe_var_name(name: str) -> str:
    """Convert a device name to a safe Python identifier."""
    # Check known Chinese names first
    for cn, en in _CN_NAME_MAP.items():
        if cn in name:
            return en
    # Remove non-ASCII and non-alphanumeric chars
    ascii_name = name.encode("ascii", errors="ignore").decode("ascii")
    ascii_name = re.sub(r'[^a-zA-Z0-9_]', '_', ascii_name)
    ascii_name = re.sub(r'_+', '_', ascii_name).strip('_').lower()
    return ascii_name or "device"


def load_manifest(project_dir: str) -> dict:
    path = os.path.join(project_dir, "project-manifest.json")
    if not os.path.exists(path):
        print("[ERROR] project-manifest.json not found: {}".format(path), file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_mcu_defaults(mcu_model: str) -> dict:
    return MCU_DEFAULTS.get(mcu_model, MCU_DEFAULTS.get("ESP32", {}))


# ═══════════════════════════════════════════════════════════════
#  Generators
# ═══════════════════════════════════════════════════════════════

def generate_board_py(manifest: dict) -> str:
    mcu = manifest.get("mcu", {})
    model = mcu.get("model", "ESP32")
    board_id = model.lower().replace(" ", "_").replace("-", "_")
    defaults = get_mcu_defaults(model)

    # Extract I2C pins from pinout
    i2c_pins = {}
    other_pins = {}
    for p in manifest.get("pinout", []):
        gpio = parse_gpio(p.get("gpio", ""))
        if gpio is None:
            continue
        pin_name = p.get("pin_name", "")
        dev = p.get("device", "")
        if "SDA" in pin_name:
            bus = p.get("bus", "I2C0")
            bus_idx = int(bus[-1]) if bus[-1].isdigit() else 0
            if bus_idx not in i2c_pins:
                i2c_pins[bus_idx] = {}
            i2c_pins[bus_idx]["SDA"] = gpio
        elif "SCL" in pin_name:
            bus = p.get("bus", "I2C0")
            bus_idx = int(bus[-1]) if bus[-1].isdigit() else 0
            if bus_idx not in i2c_pins:
                i2c_pins[bus_idx] = {}
            i2c_pins[bus_idx]["SCL"] = gpio
        else:
            other_pins[dev] = gpio

    # Fallback to MCU defaults if no pinout data
    if not i2c_pins:
        i2c_pins = defaults.get("I2C", {0: {"SDA": 21, "SCL": 22}})

    lines = []
    lines.append("# Python env   : MicroPython v1.23.0")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("# @Generated : upy-scaffold {}".format(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    lines.append("# @File    : board.py")
    lines.append("# @Description : Board-level pin mapping for {}".format(model))
    lines.append("# @License : MIT")
    lines.append("")
    lines.append("# Interface type constants")
    lines.append("I2C0 = 0")
    if len(i2c_pins) > 1:
        lines.append("I2C1 = 1")
    lines.append("")
    lines.append("BOARDS = {")
    lines.append('    "{}": {{'.format(board_id))
    lines.append('        "NAME": "{}",'.format(model))
    lines.append("")
    lines.append('        "FIXED_PINS": {')
    for name, pin in defaults.get("FIXED", {}).items():
        lines.append('            "{}": {},'.format(name, repr(pin)))
    lines.append("        },")
    lines.append("")
    lines.append('        "INTERFACES": {')
    lines.append('            "I2C": {')
    for idx, pins in sorted(i2c_pins.items()):
        lines.append("                {}: {{".format(idx))
        if "SDA" in pins:
            lines.append('                    "SDA": {},'.format(pins["SDA"]))
        if "SCL" in pins:
            lines.append('                    "SCL": {},'.format(pins["SCL"]))
        lines.append("                },")
    lines.append("            },")
    lines.append("        },")
    lines.append("")
    lines.append('        "DEFAULTS": {')
    lines.append('            "I2C_FREQ": {},'.format(defaults.get("I2C_FREQ", 400000)))
    lines.append('            "UART_BAUD": {},'.format(defaults.get("UART_BAUD", 115200)))
    lines.append("        },")
    lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append('ACTIVE_BOARD = "{}"'.format(board_id))
    lines.append("_config = BOARDS.get(ACTIVE_BOARD, {})")
    lines.append("")
    lines.append("")
    lines.append("# ── Query functions ──")
    lines.append("")
    lines.append("")
    lines.append("def get_config():")
    lines.append("    return _config")
    lines.append("")
    lines.append("")
    lines.append("def list_boards():")
    lines.append("    return list(BOARDS.keys())")
    lines.append("")
    lines.append("")
    lines.append("def set_active_board(name):")
    lines.append("    global ACTIVE_BOARD, _config")
    lines.append("    if name in BOARDS:")
    lines.append("        ACTIVE_BOARD = name")
    lines.append("        _config = BOARDS[name]")
    lines.append("        return True")
    lines.append("    return False")
    lines.append("")
    lines.append("")
    lines.append("def get_fixed_pin(name):")
    lines.append('    return _config.get("FIXED_PINS", {}).get(name)')
    lines.append("")
    lines.append("")
    lines.append("def get_i2c_pins(i2c_id):")
    lines.append('    i2c = _config.get("INTERFACES", {}).get("I2C", {})')
    lines.append("    if i2c_id in i2c:")
    lines.append('        return i2c[i2c_id].get("SDA"), i2c[i2c_id].get("SCL")')
    lines.append("    return None, None")
    lines.append("")
    lines.append("")
    lines.append("def get_default_config(name):")
    lines.append('    return _config.get("DEFAULTS", {}).get(name)')
    lines.append("")

    # Boot-sensitive pin warnings
    sensitive = defaults.get("BOOT_SENSITIVE", [])
    if sensitive:
        lines.append("# Boot/sensitive pins: {}".format(sensitive))
    flash_pins = defaults.get("FLASH_PINS", [])
    if flash_pins:
        lines.append("# Flash/PSRAM pins: {}".format(flash_pins))

    return "\n".join(lines)


def generate_conf_py(manifest: dict) -> str:
    reqs = manifest.get("requirements", {})
    mcu = manifest.get("mcu", {})
    model = mcu.get("model", "ESP32")

    sample_rate = reqs.get("sample_rate", "normal_1hz")
    interval_ms = {"normal_1hz": 1000, "high_100hz_plus": 10, "low_minute": 60000}.get(sample_rate, 1000)

    lines = []
    lines.append("# Python env   : MicroPython v1.23.0")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("# @Generated : upy-scaffold {}".format(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    lines.append("# @File    : conf.py")
    lines.append("# @Description : Firmware static configuration constants")
    lines.append("# @License : MIT")
    lines.append("")
    lines.append("# ── Firmware identity ──")
    lines.append('FW_VERSION = "0.1.0"')
    lines.append('BOARD_NAME = "{}"'.format(model))
    lines.append('PROJECT_NAME = "{}"'.format(manifest.get("project_name", "untitled")))
    lines.append("")
    lines.append("# ── Sampling ──")
    lines.append("SAMPLE_INTERVAL_MS = {}".format(interval_ms))
    lines.append("")
    lines.append("# ── Paths ──")
    lines.append('LOG_DIR = "/log"')
    lines.append('LOG_LEVEL = "INFO"')
    lines.append('LOG_FILES_MAX = 4')
    lines.append('LOG_LINES_PER_FILE = 150')
    lines.append("")

    return "\n".join(lines)


def generate_boot_py(manifest: dict) -> str:
    lines = []
    lines.append("# Python env   : MicroPython v1.23.0")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("# @Generated : upy-scaffold {}".format(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    lines.append("# @File    : boot.py")
    lines.append("# @Description : Early boot initialization (emergency buffer)")
    lines.append("# @License : MIT")
    lines.append("")
    lines.append("import micropython")
    lines.append("")
    lines.append("# Allocate emergency exception buffer for ISR errors")
    lines.append("micropython.alloc_emergency_exception_buf(100)")
    lines.append("")
    return "\n".join(lines)


def generate_main_py_timer(manifest: dict) -> str:
    """Generate main.py for Timer tick scheduler mode."""
    devices = manifest.get("devices", [])
    mcu = manifest.get("mcu", {})
    model = mcu.get("model") or mcu.get("display_name") or mcu.get("board") or ""
    timer_id = scheduler_timer_id_for_model(model)
    pinout = manifest.get("pinout", [])

    lines = []
    lines.append("# Python env   : MicroPython v1.23.0")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("# @Generated : upy-scaffold (mode: timer)")
    lines.append("# @File    : main.py")
    lines.append("# @Description : Application entry — assemble hardware, register tasks, start scheduler.")
    lines.append("# @License : MIT")
    lines.append("")
    lines.append("from machine import Pin, I2C")
    lines.append("import conf")
    lines.append("from lib.scheduler.timer_sched import Scheduler")
    lines.append("from lib.logger import info")
    lines.append("from lib.logger import install_rotating")
    lines.append("from tasks.maintenance import maintenance_tick")
    lines.append("")
    lines.append("# ── Logger setup ──")
    lines.append("# Redirect to rotating log files on device")
    lines.append("install_rotating('/log', max_files=4, lines_per_file=150)")
    lines.append("info('{} booting...'.format(conf.PROJECT_NAME))")
    lines.append("")
    lines.append("# ── Create hardware instances ──")

    # Extract I2C pins
    i2c_bus = None
    sda_pin, scl_pin = None, None
    for p in pinout:
        gpio = parse_gpio(p.get("gpio", ""))
        pn = p.get("pin_name", "")
        if "SDA" in pn:
            sda_pin = gpio
        elif "SCL" in pn:
            scl_pin = gpio

    if sda_pin and scl_pin:
        lines.append("i2c = I2C(0, scl=Pin({}), sda=Pin({}), freq=400000)".format(scl_pin, sda_pin))
    else:
        lines.append("# TODO: create I2C / SPI / UART instances based on pinout")

    # GPIO devices
    for p in pinout:
        gpio = parse_gpio(p.get("gpio", ""))
        pn = p.get("pin_name", "")
        if "SDA" not in pn and "SCL" not in pn and gpio is not None:
            dev = safe_var_name(p.get("device", "unknown"))
            lines.append("{}_pin = Pin({}, Pin.OUT)".format(dev, gpio))

    lines.append("")
    lines.append("# ── Register tasks ──")
    lines.append("sc = Scheduler(timer_id={}, tick_ms=100, idle_cb=maintenance_tick)".format(timer_id))
    lines.append("# TODO: upy-generate registers tasks here")
    lines.append("")
    lines.append("# ── Start ──")
    lines.append('print("[OK] {} starting scheduler".format(conf.PROJECT_NAME))')
    lines.append("sc.start()")
    lines.append("")

    return "\n".join(lines)


def generate_main_py_async(manifest: dict) -> str:
    """Generate main.py for uasyncio mode."""
    devices = manifest.get("devices", [])
    pinout = manifest.get("pinout", [])

    lines = []
    lines.append("# Python env   : MicroPython v1.23.0")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("# @Generated : upy-scaffold (mode: asyncio)")
    lines.append("# @File    : main.py")
    lines.append("# @Description : Application entry — uasyncio-based async tasks.")
    lines.append("# @License : MIT")
    lines.append("")
    lines.append("import uasyncio as asyncio")
    lines.append("from machine import Pin, I2C")
    lines.append("import conf")
    lines.append("from lib.logger import info")
    lines.append("from lib.logger import install_rotating")
    lines.append("from tasks.maintenance import maintenance_tick")
    lines.append("")

    sda_pin = scl_pin = None
    for p in pinout:
        gpio = parse_gpio(p.get("gpio", ""))
        pn = p.get("pin_name", "")
        if "SDA" in pn:
            sda_pin = gpio
        elif "SCL" in pn:
            scl_pin = gpio

    lines.append("# ── Logger setup ──")
    lines.append("install_rotating('/log', max_files=4, lines_per_file=150)")
    lines.append("")
    lines.append("# ── Create hardware instances ──")
    if sda_pin and scl_pin:
        lines.append("i2c = I2C(0, scl=Pin({}), sda=Pin({}), freq=400000)".format(scl_pin, sda_pin))
    else:
        lines.append("# TODO: create I2C / SPI / UART instances based on pinout")

    for p in pinout:
        gpio = parse_gpio(p.get("gpio", ""))
        pn = p.get("pin_name", "")
        if "SDA" not in pn and "SCL" not in pn and gpio is not None:
            dev = safe_var_name(p.get("device", "unknown"))
            lines.append("{}_pin = Pin({}, Pin.OUT)".format(dev, gpio))

    lines.append("")
    lines.append("async def main():")
    lines.append("    info('{} booting (asyncio)...'.format(conf.PROJECT_NAME))")
    lines.append("    # TODO: upy-generate creates async tasks here")
    lines.append("")
    lines.append("    while True:")
    lines.append("        maintenance_tick()")
    lines.append("        await asyncio.sleep_ms(100)")
    lines.append("")
    lines.append('print("[OK] {} starting asyncio".format(conf.PROJECT_NAME))')
    lines.append("asyncio.run(main())")
    lines.append("")

    return "\n".join(lines)


def generate_main_py_thread(manifest: dict) -> str:
    """Generate main.py for _thread mode."""
    devices = manifest.get("devices", [])
    pinout = manifest.get("pinout", [])

    lines = []
    lines.append("# Python env   : MicroPython v1.23.0")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("# @Generated : upy-scaffold (mode: thread)")
    lines.append("# @File    : main.py")
    lines.append("# @Description : Application entry — _thread-based parallel tasks.")
    lines.append("# @License : MIT")
    lines.append("")
    lines.append("import _thread")
    lines.append("import time")
    lines.append("from machine import Pin, I2C")
    lines.append("import conf")
    lines.append("from lib.logger import info")
    lines.append("from lib.logger import install_rotating")
    lines.append("from tasks.maintenance import maintenance_tick")
    lines.append("")

    sda_pin = scl_pin = None
    for p in pinout:
        gpio = parse_gpio(p.get("gpio", ""))
        pn = p.get("pin_name", "")
        if "SDA" in pn:
            sda_pin = gpio
        elif "SCL" in pn:
            scl_pin = gpio

    lines.append("# ── Logger setup ──")
    lines.append("install_rotating('/log', max_files=4, lines_per_file=150)")
    lines.append("")
    lines.append("# ── Create hardware instances ──")
    if sda_pin and scl_pin:
        lines.append("i2c = I2C(0, scl=Pin({}), sda=Pin({}), freq=400000)".format(scl_pin, sda_pin))
    else:
        lines.append("# TODO: create I2C / SPI / UART instances based on pinout")

    for p in pinout:
        gpio = parse_gpio(p.get("gpio", ""))
        pn = p.get("pin_name", "")
        if "SDA" not in pn and "SCL" not in pn and gpio is not None:
            dev = safe_var_name(p.get("device", "unknown"))
            lines.append("{}_pin = Pin({}, Pin.OUT)".format(dev, gpio))

    lines.append("")
    lines.append("# ── Start threads ──")
    lines.append("info('{} booting (thread)...'.format(conf.PROJECT_NAME))")
    lines.append("# TODO: upy-generate starts threads here")
    lines.append("")
    lines.append("# Main thread: maintenance loop")
    lines.append("while True:")
    lines.append("    maintenance_tick()")
    lines.append("    time.sleep_ms(100)")
    lines.append("")

    return "\n".join(lines)


def generate_readme_md(manifest: dict, mode: str) -> str:
    mcu = manifest.get("mcu", {})
    project_name = manifest.get("project_name", "untitled")
    reqs = manifest.get("requirements", {})
    bom = manifest.get("bom", [])

    lines = []
    lines.append("# {}".format(project_name))
    lines.append("")
    lines.append("> Generated by upy-scaffold | mode: {} | {}".format(
        mode, datetime.now(timezone.utc).strftime("%Y-%m-%d")))
    lines.append("")
    lines.append("## Hardware")
    lines.append("- MCU: {} ({})".format(mcu.get("model", "?"), mcu.get("board", "?")))
    lines.append("- Firmware: {}".format(mcu.get("firmware_url", "N/A")))
    lines.append("")
    lines.append("## BOM")
    lines.append("| # | Name | Model | Qty | Price (yuan) |")
    lines.append("|---|------|-------|-----|-------------|")
    for i, item in enumerate(bom):
        lines.append("| {} | {} | {} | {} | {} |".format(
            i + 1, item.get("name", "?"), item.get("model", "?"),
            item.get("quantity", 1), item.get("unit_price_yuan", "?")))
    total = sum(item.get("unit_price_yuan", 0) * item.get("quantity", 1) for item in bom)
    lines.append("")
    lines.append("**Total: {} yuan**".format(total))
    lines.append("")
    lines.append("## Pinout")
    lines.append("| Device | Pin | GPIO | Bus | I2C Addr |")
    lines.append("|--------|-----|------|-----|----------|")
    for p in manifest.get("pinout", []):
        lines.append("| {} | {} | {} | {} | {} |".format(
            p.get("device", "?"), p.get("pin_name", "?"),
            p.get("gpio", "?"), p.get("bus", ""), p.get("i2c_addr", "")))
    lines.append("")
    lines.append("## Scheduler Mode")
    lines.append("`{}`".format(mode))
    lines.append("")
    lines.append("## Quick Start")
    lines.append("```bash")
    lines.append("# Upload to device")
    lines.append("mpremote fs cp -r firmware/ :/")
    lines.append("mpremote reset")
    lines.append("")
    lines.append("# Read logs")
    lines.append("python tools/read_device_log.py --port COMx")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def generate_dot_flake8(project_dir: str):
    """Generate .flake8 config to suppress MicroPython-specific false positives."""
    content = """[flake8]
max-line-length = 120
extend-ignore =
    F821,
    F401,
per-file-ignores =
    firmware/lib/logger/logging.py: F821
    firmware/lib/scheduler/timer_sched.py: F821

[pycodestyle]
max-line-length = 120
ignore = E402, W503
"""
    path = os.path.join(project_dir, ".flake8")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] .flake8")


def copy_tree(src_dir: str, dst_dir: str):
    """Recursively copy directory tree."""
    for root, dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        dst = os.path.join(dst_dir, rel) if rel != "." else dst_dir
        os.makedirs(dst, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(dst, f))


def main():
    parser = argparse.ArgumentParser(description="Generate MicroPython project skeleton")
    parser.add_argument("--project-dir", required=True, help="Project directory path")
    parser.add_argument("--mode", default="timer", choices=["timer", "async", "thread"],
                        help="Scheduler mode (default: timer)")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    mode = args.mode

    # 1. Load manifest
    manifest = load_manifest(project_dir)
    if manifest.get("phase") not in ("select-hw", "scaffold"):
        print("[WARNING] manifest phase is '{}', expected 'select-hw'".format(
            manifest.get("phase")), file=sys.stderr)

    # 2. Create directory structure
    dirs = [
        "firmware/lib/scheduler",
        "firmware/lib/logger",
        "firmware/assets",
        "firmware/tasks",
        "firmware/drivers",
        "host",
        "test/device",
        "test/pc",
        "tools",
        "docs",
        "build/firmware",
        "build/mpy",
    ]
    for d in dirs:
        os.makedirs(os.path.join(project_dir, d), exist_ok=True)

    # 3. Generate board.py
    path = os.path.join(project_dir, "firmware", "board.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_board_py(manifest))
    print("[OK] firmware/board.py")

    # 4. Generate conf.py
    path = os.path.join(project_dir, "firmware", "conf.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_conf_py(manifest))
    print("[OK] firmware/conf.py")

    # 5. Generate boot.py
    path = os.path.join(project_dir, "firmware", "boot.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_boot_py(manifest))
    print("[OK] firmware/boot.py")

    # 6. Generate main.py (mode-specific)
    path = os.path.join(project_dir, "firmware", "main.py")
    generators = {
        "timer": generate_main_py_timer,
        "async": generate_main_py_async,
        "thread": generate_main_py_thread,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(generators[mode](manifest))
    print("[OK] firmware/main.py (mode: {})".format(mode))

    # 7. Copy logger
    src = os.path.join(TEMPLATES_DIR, "lib", "logger")
    dst = os.path.join(project_dir, "firmware", "lib", "logger")
    copy_tree(src, dst)
    print("[OK] firmware/lib/logger/ (3 files)")

    # 8. Copy time_helper.py
    src = os.path.join(TEMPLATES_DIR, "lib", "time_helper.py")
    dst = os.path.join(project_dir, "firmware", "lib", "time_helper.py")
    shutil.copy2(src, dst)
    print("[OK] firmware/lib/time_helper.py")

    # 9. Copy scheduler (timer mode only)
    if mode == "timer":
        src = os.path.join(TEMPLATES_DIR, "lib", "scheduler", "timer_sched.py")
        dst = os.path.join(project_dir, "firmware", "lib", "scheduler", "timer_sched.py")
        shutil.copy2(src, dst)
        # Write __init__.py for scheduler
        init_py = os.path.join(project_dir, "firmware", "lib", "scheduler", "__init__.py")
        with open(init_py, "w") as f:
            f.write("# Scheduler package\nfrom .timer_sched import Scheduler\n")
        print("[OK] firmware/lib/scheduler/ (timer mode)")

    # 10. Remove stale sensor_task.py (was generated by old scaffold, now upy-generate's job)
    stale_task = os.path.join(project_dir, "firmware", "tasks", "sensor_task.py")
    if os.path.exists(stale_task):
        os.remove(stale_task)

    # 11. Copy maintenance.py
    src = os.path.join(TEMPLATES_DIR, "tasks", "maintenance.py")
    dst = os.path.join(project_dir, "firmware", "tasks", "maintenance.py")
    shutil.copy2(src, dst)
    print("[OK] firmware/tasks/maintenance.py")

    # 12. Generate tasks/__init__.py
    path = os.path.join(project_dir, "firmware", "tasks", "__init__.py")
    with open(path, "w") as f:
        f.write("# Tasks package\n")
    print("[OK] firmware/tasks/__init__.py")

    # 13. Generate driver stubs per device
    devices = manifest.get("devices", [])
    for d in devices:
        name = safe_var_name(d.get("name", "unknown"))
        if d.get("driver", {}).get("source") != "none":
            drv_dir = os.path.join(project_dir, "firmware", "drivers", "{}_driver".format(name))
            os.makedirs(drv_dir, exist_ok=True)
            init_path = os.path.join(drv_dir, "__init__.py")
            with open(init_path, "w") as f:
                f.write("# {} driver stub\n".format(d.get("name", name)))
                f.write("# Source: {}\n".format(d.get("driver", {}).get("source", "unknown")))
                f.write("# Install: {}\n".format(d.get("driver", {}).get("install_cmd", "N/A")))
                f.write("# TODO: upy-generate fills this\n")
    print("[OK] firmware/drivers/ ({} stubs)".format(len(devices)))

    # 14. Copy PC tools
    src = os.path.join(TEMPLATES_DIR, "pc", "read_device_log.py")
    dst = os.path.join(project_dir, "tools", "read_device_log.py")
    shutil.copy2(src, dst)
    print("[OK] tools/read_device_log.py")

    src = os.path.join(TEMPLATES_DIR, "pc", "log_report.py")
    dst = os.path.join(project_dir, "tools", "log_report.py")
    shutil.copy2(src, dst)
    print("[OK] tools/log_report.py")

    src = os.path.join(TEMPLATES_DIR, "pc", "flash_device.py")
    dst = os.path.join(project_dir, "tools", "flash_device.py")
    shutil.copy2(src, dst)
    print("[OK] tools/flash_device.py")

    # 15. Generate README.md
    path = os.path.join(project_dir, "README.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_readme_md(manifest, mode))
    print("[OK] README.md")

    # 16. Generate LICENSE
    path = os.path.join(project_dir, "LICENSE")
    with open(path, "w") as f:
        f.write("MIT License\n\nCopyright (c) {}\n\n".format(datetime.now().year))
        f.write("Permission is hereby granted, free of charge, to any person obtaining a copy\n")
        f.write("of this software and associated documentation files (the \"Software\"), to deal\n")
        f.write("in the Software without restriction...\n")
    print("[OK] LICENSE")

    # 17. Generate .flake8 (suppress MPY-specific lint false positives)
    generate_dot_flake8(project_dir)

    # 18. Placeholders
    for d in ["docs", "host", "test/device", "test/pc"]:
        placeholder = os.path.join(project_dir, d, ".gitkeep")
        with open(placeholder, "w") as f:
            f.write("")
    print("[OK] docs/ host/ test/ (placeholders)")

    # 19. Update manifest phase
    manifest["phase"] = "scaffold"
    manifest["scaffold_mode"] = mode
    manifest["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest_path = os.path.join(project_dir, "project-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("[OK] project-manifest.json (phase: scaffold, mode: {})".format(mode))

    # 20. flake8 verification (includes pycodestyle E/W checks)
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "-m", "flake8", "firmware/", "tools/"],
            cwd=project_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            print("[LINT] flake8 issues:")
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    print("  {}".format(line))
            print("[WARN] Review .flake8 config or fix the above.", file=sys.stderr)
        else:
            print("[OK] flake8 — clean")
    except Exception:
        print("[WARN] flake8 not available, skipping lint check")

    # ── Summary ──
    print("")
    print("=" * 60)
    print("  upy-scaffold complete")
    print("  Project: {}".format(manifest.get("project_name", "?")))
    print("  MCU: {}".format(manifest["mcu"]["model"]))
    print("  Mode: {}".format(mode))
    print("  Files generated in {}".format(project_dir))
    print("=" * 60)


if __name__ == "__main__":
    main()
