#!/usr/bin/env python3
"""
LLM analyze interface layer for upy-analyze-plugin.

Current stage:
- defines the structured input/output contract
- defines prompt/schema/fallback behavior
- keeps the real model invocation point isolated for future replacement
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


VALID_INTERFACES = {
    "I2C", "SPI", "UART", "GPIO", "PWM", "ADC", "I2S", "1-Wire", "CAN", "USB", "WiFi", "BLE"
}

VALID_DEVICE_SOURCES = {"user_specified", "system_recommended"}
VALID_DRIVER_SOURCES = {
    "builtin_runtime",
    "micropython_lib",
    "upypi",
    "awesome-micropython",
    "github",
    "cold-driver",
    "none",
}


@dataclass
class AnalyzeResult:
    project_name: str
    requirements: Dict[str, Any]
    devices: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "requirements": self.requirements,
            "devices": self.devices,
        }


def get_output_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["project_name", "requirements", "devices"],
        "properties": {
            "project_name": {"type": "string"},
            "requirements": {
                "type": "object",
                "required": ["description"],
                "properties": {
                    "description": {"type": "string"},
                },
            },
            "devices": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "type", "interface", "source", "driver"],
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "interface": {"type": "string"},
                        "source": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "driver": {
                            "type": "object",
                            "required": ["source"],
                            "properties": {
                                "source": {"type": "string"},
                                "module": {"type": "string"},
                                "package_name": {"type": "string"},
                                "install_cmd": {"type": "string"},
                                "repo_url": {"type": "string"},
                                "version": {"type": "string"},
                                "notes": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def build_prompt_input(start_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_description": start_payload.get("user_description"),
        "pre_selected_board": start_payload.get("pre_selected_board"),
        "preferences": start_payload.get("preferences", {}),
        "existing_hardware": start_payload.get("existing_hardware", []),
    }


def build_system_prompt() -> str:
    return (
        "你是 upy-analyze-plugin 的 analyze 引擎。\n"
        "你的任务是把用户需求解析为结构化结果。\n"
        "你只负责：project_name、requirements.description、devices[] 草稿。\n"
        "你不负责：最终板卡选型、代码生成、引脚分配。\n"
        "用户明确提到的器件必须标记为 user_specified。\n"
        "你补出来的器件必须标记为 system_recommended。\n"
        "必须先区分两层：1) MicroPython 内置运行时/外设 API；2) 具体器件驱动包。\n"
        "若 GPIO / ADC / I2C / SPI / UART / I2S / WiFi / BLE 等能力可直接由 MicroPython 内置模块支持，应记录 builtin_runtime 这一层能力。\n"
        "但 builtin_runtime 不等于已经找到具体器件驱动包；对于具体传感器/模块，仍需继续判断是否存在现成驱动来源。\n"
        "若能力来自 micropython/micropython-lib（例如 aioble），使用 micropython_lib，而不是 builtin_runtime。\n"
        "micropython_lib 主要用于官方生态通用库/中间件，不是默认的传感器驱动主来源。\n"
        "具体器件驱动结果必须由后续 upy-pkg-guide 调用确认；此层不要伪造 upypi 包名或安装命令。\n"
        "不要把普通 Python PyPI 当成 MicroPython 驱动包主搜索入口。\n"
        "不要把固件内置能力写成 local，machine/network/bluetooth/neopixel 等能力应写成 builtin_runtime。\n"
        "对于像土壤湿度传感器这种大类器件，必须先区分实现族，例如 ADC / Modbus / I2C 等，再决定推荐方案。\n"
        "interface 只能使用: I2C, SPI, UART, GPIO, PWM, ADC, I2S, 1-Wire, CAN, USB, WiFi, BLE。\n"
        "driver.source 只能使用: builtin_runtime, micropython_lib, upypi, awesome-micropython, github, cold-driver, none。\n"
        "输出必须是 JSON，不要输出解释文字，不要输出 markdown。"
    )


def build_user_prompt(start_payload: Dict[str, Any]) -> str:
    payload = build_prompt_input(start_payload)
    schema = get_output_schema()
    return (
        "请根据以下 analyze 输入，输出结构化 JSON。\n\n"
        f"输入:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "输出要求:\n"
        "- 必须只输出 JSON\n"
        "- requirements 目前只强制输出 description\n"
        "- devices 至少 1 个\n"
        "- 如果用户没有明确指定型号，可以输出 system_recommended 的通用器件草稿\n"
        "- 不要假装已经完成完整驱动搜索；具体器件默认先给 driver.source=none，由后续 upy-pkg-guide 回填\n"
        "- 如果器件主要依赖 machine / network / bluetooth / neopixel 等内置模块，请记录 builtin_runtime 这一层能力\n"
        "- 如果能力来自 micropython/micropython-lib（例如 aioble），请使用 micropython_lib\n"
        "- 如果是具体传感器/屏幕/执行器驱动，不要直接写成 upypi；后续由 upy-pkg-guide 查询确认\n"
        "- 对于大类器件，先表达实现族，不要过早锁死单一型号\n\n"
        f"输出 schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )


def infer_project_name(description: str) -> str:
    if "植物" in description:
        return "植物助手"
    if "温湿度" in description:
        return "温湿度监测报警器"
    if "空气质量" in description:
        return "空气质量监测器"
    if "对话" in description or "语音" in description:
        return "语音交互装置"
    if "助手" in description:
        return "智能助手"
    return "MicroPython 项目"


def make_device(
    name: str,
    device_type: str,
    interface: str,
    source: str,
    driver_source: str,
    subtitle: str = "",
) -> Dict[str, Any]:
    driver: Dict[str, Any] = {"source": driver_source}
    if driver_source == "builtin_runtime":
        module_map = {
            "ADC": "machine.ADC",
            "GPIO": "machine.Pin",
            "I2S": "machine.I2S",
            "I2C": "machine.I2C",
            "SPI": "machine.SPI",
            "UART": "machine.UART",
            "WiFi": "network",
            "BLE": "bluetooth",
        }
        module = module_map.get(interface)
        if module:
            driver["module"] = module
            driver["notes"] = f"使用 MicroPython 内置 {module} 支持底层访问"
    elif driver_source == "micropython_lib":
        pkg_name = name.lower().replace(" ", "-")
        driver.update(
            {
                "package_name": pkg_name,
                "install_cmd": f"mpremote mip install {pkg_name}",
                "repo_url": "https://github.com/micropython/micropython-lib",
                "version": "latest",
                "api_ref": {
                    "import": f"import {pkg_name.replace('-', '_')}",
                    "usage": "Use documented MicroPython-lib package APIs; require package guide evidence before generating calls",
                },
            }
        )
    return {
        "name": name,
        "type": device_type,
        "interface": interface,
        "source": source,
        "driver": driver,
        "subtitle": subtitle,
    }


def fallback_rule_based_analyze(start_payload: Dict[str, Any]) -> AnalyzeResult:
    description = start_payload.get("user_description", "")
    desc_lower = description.lower()
    devices: List[Dict[str, Any]] = []

    def add(device: Dict[str, Any]) -> None:
        if any(item["name"] == device["name"] for item in devices):
            return
        devices.append(device)

    if any(word in description for word in ["土壤", "soil"]):
        if any(word in desc_lower for word in ["modbus", "rs485", "485", "mse"]):
            add(
                make_device(
                    "MSE 土壤温湿度传感器",
                    "soil_temperature_humidity_sensor",
                    "UART",
                    "system_recommended",
                    "none",
                    "RS485/Modbus 土壤温湿度一体传感器",
                )
            )
        elif any(word in description for word in ["模拟", "adc", "电容式"]):
            add(
                make_device(
                    "电容式土壤湿度传感器",
                    "soil_moisture_sensor",
                    "ADC",
                    "system_recommended",
                    "builtin_runtime",
                    "ADC 土壤湿度传感器",
                )
            )
        else:
            add(
                make_device(
                    "土壤湿度传感器",
                    "soil_moisture_sensor",
                    "ADC",
                    "system_recommended",
                    "builtin_runtime",
                    "默认推荐 ADC 土壤湿度方案，可在确认点改为 Modbus/I2C 方案",
                )
            )

    if any(word in description for word in ["温湿度", "湿度", "humidity", "temperature"]) and not any(
        word in description for word in ["土壤", "soil"]
    ):
        add(make_device("SHT30", "temperature_humidity_sensor", "I2C", "system_recommended", "none", "I2C 温湿度传感器"))

    if any(word in description for word in ["植物", "光照", "light"]):
        add(make_device("BH1750", "light_sensor", "I2C", "system_recommended", "none", "I2C 光照传感器"))

    if any(word in description for word in ["显示", "屏幕", "oled", "屏"]):
        add(make_device("SSD1306", "display", "I2C", "system_recommended", "none", "I2C OLED 显示屏"))

    if any(word in description for word in ["报警", "蜂鸣", "buzzer"]):
        add(make_device("蜂鸣器", "buzzer", "GPIO", "system_recommended", "builtin_runtime", "GPIO 执行器"))

    if any(word in description for word in ["触摸", "摸", "touch"]):
        add(make_device("触摸传感器", "touch_sensor", "GPIO", "system_recommended", "builtin_runtime", "GPIO 触摸输入"))

    if any(word in description for word in ["语音", "对话", "说话", "voice", "audio"]):
        add(make_device("I2S 麦克风", "microphone", "I2S", "system_recommended", "builtin_runtime", "I2S 语音输入，底层依赖 machine.I2S"))
        add(make_device("I2S 喇叭", "speaker", "I2S", "system_recommended", "builtin_runtime", "I2S 语音输出，底层依赖 machine.I2S"))

    if any(word in desc_lower for word in ["ble", "蓝牙", "bluetooth", "aioble"]):
        add(make_device("aioble", "ble_stack", "BLE", "system_recommended", "micropython_lib", "BLE 官方生态库"))

    if not devices:
        add(make_device("通用传感器", "generic_sensor", "I2C", "system_recommended", "none", "I2C 通用传感器"))

    for hardware in start_payload.get("existing_hardware", []):
        name = str(hardware).strip()
        if not name:
            continue
        add(make_device(name, "existing_hardware", "GPIO", "user_specified", "none", f"已有器件: {name}"))

    return AnalyzeResult(
        project_name=infer_project_name(description),
        requirements={"description": description},
        devices=devices,
    )


def parse_llm_json_output(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("empty llm output")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json from llm output: {exc}") from exc


def validate_llm_output(result: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not result.get("project_name"):
        errors.append("missing project_name")

    requirements = result.get("requirements")
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
    elif not requirements.get("description"):
        errors.append("requirements.description is required")

    devices = result.get("devices")
    if not isinstance(devices, list) or not devices:
        errors.append("devices must be a non-empty array")
        return errors

    for index, device in enumerate(devices):
        prefix = f"devices[{index}]"
        if not isinstance(device, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ["name", "type", "interface", "source", "driver"]:
            if field not in device or not device.get(field):
                errors.append(f"{prefix}.{field} is required")
        interface = device.get("interface")
        if interface and interface not in VALID_INTERFACES:
            errors.append(f"{prefix}.interface invalid: {interface}")
        source = device.get("source")
        if source and source not in VALID_DEVICE_SOURCES:
            errors.append(f"{prefix}.source invalid: {source}")
        driver = device.get("driver")
        if isinstance(driver, dict):
            driver_source = driver.get("source")
            if not driver_source:
                errors.append(f"{prefix}.driver.source is required")
            elif driver_source not in VALID_DRIVER_SOURCES:
                errors.append(f"{prefix}.driver.source invalid: {driver_source}")
        else:
            errors.append(f"{prefix}.driver must be an object")

    return errors


def call_real_model(_system_prompt: str, _user_prompt: str) -> Optional[str]:
    """
    Future real model hook.
    """
    return None


def analyze_with_llm_contract(start_payload: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(start_payload)

    raw_model_output = call_real_model(system_prompt, user_prompt)
    if raw_model_output is not None:
        result = parse_llm_json_output(raw_model_output)
    else:
        result = fallback_rule_based_analyze(start_payload).to_dict()

    errors = validate_llm_output(result)
    if errors:
        raise ValueError(f"llm analyze output invalid: {errors}")
    return result
