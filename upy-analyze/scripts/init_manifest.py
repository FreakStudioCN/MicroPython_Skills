#!/usr/bin/env python3
"""
upy-analyze 的 manifest 初始化脚本。

将 LLM 输出的结构化 JSON 校验并写入项目目录下的 project-manifest.json。
所有枚举值、必填字段、类型均遵循 schemas/project-manifest.schema.json。

用法：
  python init_manifest.py --project-dir G:/ai_project/test --input llm_output.json
  python init_manifest.py --project-dir G:/ai_project/test < llm_output.json
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone
from typing import Any

# ── Schema 中的枚举值定义 ────────────────────────────────

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

VALID_DRIVER_SOURCES = ["upypi", "awesome-micropython", "github", "local", "cold-driver", "none"]

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


def load_input(args: argparse.Namespace) -> dict:
    """加载 LLM 输出的 JSON，从文件或 stdin。"""
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        print("[init_manifest] Reading JSON from stdin...", file=sys.stderr)
        return json.load(sys.stdin)


def validate_and_fill(data: dict) -> list[str]:
    """校验并填充默认值。返回错误列表，空列表表示通过。"""
    errors = []

    # ── 顶层必填 ──
    if "project_name" not in data or not data["project_name"]:
        errors.append("缺少必填字段: project_name")
    if "requirements" not in data:
        errors.append("缺少必填字段: requirements")
    if "devices" not in data or not isinstance(data["devices"], list):
        errors.append("缺少必填字段: devices (必须是数组)")
    elif len(data["devices"]) == 0:
        errors.append("devices 数组不能为空")

    if errors:
        return errors

    # ── requirements 校验 + 填充默认值 ──
    req = data["requirements"]
    if "description" not in req or not req["description"]:
        errors.append("requirements.description 为必填")

    for field, default in REQUIREMENTS_DEFAULTS.items():
        if field not in req or req[field] is None:
            req[field] = default
            continue

        val = req[field]
        if field in VALID_ENUMS:
            if val not in VALID_ENUMS[field]:
                errors.append(
                    f"requirements.{field} 无效值 '{val}'，有效值: {VALID_ENUMS[field]}"
                )
        elif field == "output":
            if not isinstance(val, list):
                errors.append(f"requirements.output 必须是数组")
            else:
                for v in val:
                    if v not in VALID_OUTPUT_TYPES:
                        errors.append(
                            f"requirements.output 无效值 '{v}'，有效值: {VALID_OUTPUT_TYPES}"
                        )
        elif field == "special_requirements":
            if not isinstance(val, list):
                errors.append(f"requirements.special_requirements 必须是数组")
            else:
                for v in val:
                    if v not in VALID_SPECIAL_REQS:
                        errors.append(
                            f"requirements.special_requirements 无效值 '{v}'，有效值: {VALID_SPECIAL_REQS}"
                        )
        elif field == "existing_hardware":
            if not isinstance(val, list):
                errors.append(f"requirements.existing_hardware 必须是数组")

    # ── devices 校验 ──
    for i, dev in enumerate(data["devices"]):
        prefix = f"devices[{i}]"
        for field in ["name", "type", "interface"]:
            if field not in dev or not dev[field]:
                errors.append(f"{prefix} 缺少必填字段: {field}")

        if "interface" in dev and dev["interface"] not in VALID_DEVICE_INTERFACES:
            errors.append(
                f"{prefix}.interface 无效值 '{dev['interface']}'，"
                f"有效值: {VALID_DEVICE_INTERFACES}"
            )

        if "i2c_addr" in dev and dev["i2c_addr"]:
            if not isinstance(dev["i2c_addr"], list):
                errors.append(f"{prefix}.i2c_addr 必须是数组")
            else:
                for addr in dev["i2c_addr"]:
                    if not isinstance(addr, str) or not addr.startswith("0x"):
                        errors.append(f"{prefix}.i2c_addr '{addr}' 格式错误，需要 0x 前缀")

        if "driver" in dev and dev["driver"]:
            src = dev["driver"].get("source")
            if src and src not in VALID_DRIVER_SOURCES:
                errors.append(
                    f"{prefix}.driver.source 无效值 '{src}'，有效值: {VALID_DRIVER_SOURCES}"
                )

        if "quantity" not in dev:
            dev["quantity"] = 1

    return errors


def build_manifest(data: dict) -> dict:
    """构建完整的 manifest，补充元数据字段。"""
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


def main():
    parser = argparse.ArgumentParser(
        description="初始化 project-manifest.json（upy-analyze Phase 1 输出）"
    )
    parser.add_argument("--project-dir", required=True, help="项目目录路径")
    parser.add_argument("--input", default=None, help="LLM 输出的 JSON 文件（不指定则从 stdin 读取）")
    args = parser.parse_args()

    # 1. 加载输入
    try:
        data = load_input(args)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"[ERROR] 文件不存在: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. 校验 + 填充默认值
    errors = validate_and_fill(data)
    if errors:
        print(f"[ERROR] 校验失败 ({len(errors)} 项):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # 3. 构建 manifest
    manifest = build_manifest(data)

    # 4. 创建项目目录
    project_dir = args.project_dir
    os.makedirs(project_dir, exist_ok=True)

    # 5. 写入
    manifest_path = os.path.join(project_dir, "project-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[OK] {manifest_path}")

    # 6. 打印摘要
    print(f"      phase: analyze")
    print(f"      project: {manifest['project_name']}")
    no_driver = [d["name"] for d in manifest["devices"]
                 if not d.get("driver") or d["driver"].get("source") in ("none", None)]
    has_driver = [d["name"] for d in manifest["devices"]
                  if d.get("driver") and d["driver"].get("source") not in ("none", None)]
    print(f"      devices: {len(manifest['devices'])} total")
    print(f"        with driver: {len(has_driver)} ({', '.join(has_driver) if has_driver else 'none'})")
    print(f"        no driver:  {len(no_driver)} ({', '.join(no_driver) if no_driver else 'none'})")
    if no_driver:
        print(f"      WARNING: devices without driver will trigger upy-gen-driver")


if __name__ == "__main__":
    main()
