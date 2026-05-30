#!/usr/bin/env python3
"""
upy-select-hw 的 manifest 更新脚本。

读取已有 project-manifest.json，合并 MCU 选型、引脚分配、BOM 结果，
更新 phase 和时间戳。

用法：
  python update_manifest.py --project-dir G:/ai_project/test --input llm_output.json
  python update_manifest.py --project-dir G:/ai_project/test < llm_output.json
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone

# ── 已知 MPY 固件支持的型号 ──

KNOWN_FIRMWARE = {
    "ESP32": "ESP32_GENERIC",
    "ESP32-S3": "ESP32_GENERIC_S3",
    "ESP32-C3": "ESP32_GENERIC_C3",
    "ESP32-S2": "ESP32_GENERIC_S2",
    "ESP32-C6": "ESP32_GENERIC_C6",
    "ESP8266": "ESP8266_GENERIC",
    "Pico": "RPI_PICO",
    "Pico W": "RPI_PICO_W",
    "Pico 2": "RPI_PICO2",
    "Pico 2 W": "RPI_PICO2_W",
    "STM32F4DISC": "STM32F4DISC",
    "STM32F7DISC": "STM32F7DISC",
    "PYBV11": "PYBV11",
    "TEENSY40": "TEENSY40",
    "TEENSY41": "TEENSY41",
    "ARDUINO_NANO_RP2040_CONNECT": "ARDUINO_NANO_RP2040_CONNECT",
    "ARDUINO_NANO_ESP32": "ARDUINO_NANO_ESP32",
    "M5STACK_ATOM": "M5STACK_ATOM",
    "XIAO_ESP32C3": "XIAO_ESP32C3",
    "XIAO_RP2040": "XIAO_RP2040",
    "WIO_TERMINAL": "WIO_TERMINAL",
}


def load_input(args: argparse.Namespace) -> dict:
    """加载 LLM 输出。"""
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return json.load(sys.stdin)


def load_manifest(project_dir: str) -> dict:
    """读取已有 manifest。"""
    path = os.path.join(project_dir, "project-manifest.json")
    if not os.path.exists(path):
        print(f"[ERROR] project-manifest.json not found in {project_dir}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_and_fill(data: dict, manifest: dict) -> list[str]:
    """校验 LLM 输出并与现有 manifest 合并。"""
    errors = []

    # ── mcu 校验 ──
    mcu = data.get("mcu")
    if not mcu:
        errors.append("缺少必填字段: mcu")
    else:
        if "model" not in mcu or not mcu["model"]:
            errors.append("mcu.model 为必填")

        model = mcu.get("model", "")
        board_name = mcu.get("board", KNOWN_FIRMWARE.get(model, ""))
        if board_name:
            mcu["board"] = board_name
            if "firmware_url" not in mcu or not mcu["firmware_url"]:
                mcu["firmware_url"] = f"https://micropython.org/download/{board_name}/"

    # ── pinout 校验 ──
    pinout = data.get("pinout", [])
    if not isinstance(pinout, list):
        errors.append("pinout 必须是数组")
    else:
        # 共享总线引脚（I2C SDA/SCL, SPI MOSI/MISO/SCK）可被多器件共用，不算冲突
        shared_ok_pins = {"SDA", "SCL", "MOSI", "MISO", "SCK", "CS"}
        assigned_gpios = {}  # gpio -> first device
        for i, p in enumerate(pinout):
            prefix = f"pinout[{i}]"
            gpio = p.get("gpio", "")
            pin_role = p.get("pin_name", "")
            if gpio:
                # 共享总线引脚允许重复
                is_shared = any(s in pin_role for s in shared_ok_pins)
                if gpio in assigned_gpios and not is_shared:
                    errors.append(
                        f"{prefix} GPIO {gpio} conflict with {assigned_gpios[gpio]}"
                    )
                elif gpio not in assigned_gpios:
                    assigned_gpios[gpio] = p.get("device", f"pinout[{i}]")
            if "device" not in p:
                errors.append(f"{prefix}.device 为必填")
            if "pin_name" not in p:
                errors.append(f"{prefix}.pin_name 为必填")

    # ── bom 校验 ──
    bom = data.get("bom", [])
    if not isinstance(bom, list):
        errors.append("bom 必须是数组")
    else:
        for i, item in enumerate(bom):
            if "name" not in item:
                errors.append(f"bom[{i}].name 为必填")
            if "quantity" not in item:
                errors.append(f"bom[{i}].quantity 为必填")

    return errors


def merge_manifest(manifest: dict, data: dict) -> dict:
    """合并新数据到 manifest。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest["phase"] = "select-hw"
    manifest["updated_at"] = now
    manifest["mcu"] = data["mcu"]
    manifest["pinout"] = data.get("pinout", [])
    manifest["bom"] = data.get("bom", [])

    # 计算 I2C 总线地址冲突
    i2c_buses = {}
    for p in manifest["pinout"]:
        bus = p.get("bus", p.get("pin_name", ""))
        addr = p.get("i2c_addr")
        if addr:
            if bus not in i2c_buses:
                i2c_buses[bus] = {}
            if addr in i2c_buses[bus]:
                print(f"[WARNING] I2C address conflict: {addr} on bus {bus} shared by multiple devices", file=sys.stderr)
            i2c_buses[bus][addr] = p["device"]

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="更新 project-manifest.json（upy-select-hw Phase 2 输出）"
    )
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument("--input", default=None, help="LLM 输出的 JSON 文件（不指定则从 stdin 读取）")
    args = parser.parse_args()

    # 1. 加载已有 manifest
    manifest = load_manifest(args.project_dir)
    if manifest.get("phase") != "analyze":
        print(f"[WARNING] manifest phase is '{manifest.get('phase')}', expected 'analyze'", file=sys.stderr)

    # 2. 加载 LLM 输出
    try:
        data = load_input(args)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"[ERROR] 输入加载失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. 校验
    errors = validate_and_fill(data, manifest)
    if errors:
        print(f"[ERROR] Validation failed ({len(errors)} items):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # 4. 合并
    manifest = merge_manifest(manifest, data)

    # 5. 写入
    manifest_path = os.path.join(args.project_dir, "project-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[OK] {manifest_path}")
    print(f"      phase: select-hw")
    print(f"      mcu: {manifest['mcu']['model']}")

    fw = manifest["mcu"].get("firmware_url", "N/A")
    if fw != "N/A":
        print(f"      firmware: {fw}")

    pin_count = len(manifest.get("pinout", []))
    bom_count = len(manifest.get("bom", []))
    print(f"      pinout: {pin_count} pins assigned")
    print(f"      bom: {bom_count} items")

    total = sum(item.get("unit_price_yuan", 0) * item.get("quantity", 1)
                for item in manifest.get("bom", []))
    budget = manifest.get("requirements", {}).get("budget_yuan", "unknown")
    print(f"      estimated total: {total:.0f} yuan (budget: {budget})")


if __name__ == "__main__":
    main()
