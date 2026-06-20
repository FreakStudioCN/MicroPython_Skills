#!/usr/bin/env python3
"""
Local adapter for the upy-pkg-guide handoff.

The real plugin/server flow should invoke the upy-pkg-guide skill for concrete
device drivers. This adapter keeps local runner tests deterministic while
preserving that boundary: llm_analyze produces device drafts, and this layer
fills driver facts.
"""

from __future__ import annotations

from typing import Any, Optional


BUILTIN_INTERFACE_MODULE_MAP = {
    "ADC": "machine.ADC",
    "GPIO": "machine.Pin",
    "PWM": "machine.PWM",
    "I2S": "machine.I2S",
    "WiFi": "network",
    "BLE": "bluetooth",
}

BUILTIN_GPIO_DEVICE_TYPES = {
    "button",
    "buzzer",
    "relay",
    "led",
    "led_rgb",
    "touch_sensor",
}

MOCK_DRIVER_INDEX = {
    "sht30": {
        "source": "upypi",
        "package_name": "sht30-driver",
        "install_cmd": "mpremote mip install sht30-driver",
        "version": "0.1.0",
        "api_ref": {
            "init": "SHT30(i2c)",
            "read": "sensor.measure()",
        },
        "notes": "mock pkg-guide result for local runner",
    },
    "ssd1306": {
        "source": "upypi",
        "package_name": "ssd1306",
        "install_cmd": "mpremote mip install ssd1306",
        "version": "latest",
        "api_ref": {
            "init": "SSD1306_I2C(width, height, i2c)",
            "draw": "display.text(...); display.show()",
        },
        "notes": "mock pkg-guide result for local runner",
    },
    "bh1750": {
        "source": "upypi",
        "package_name": "bh1750-driver",
        "install_cmd": "mpremote mip install bh1750-driver",
        "version": "0.1.0",
        "api_ref": {
            "init": "BH1750(i2c)",
            "read": "sensor.luminance()",
        },
        "notes": "mock pkg-guide result for local runner",
    },
    "hdc1080": {
        "source": "upypi",
        "package_name": "hdc1080-driver",
        "install_cmd": "mpremote mip install hdc1080-driver",
        "version": "0.1.0",
        "api_ref": {
            "init": "HDC1080(i2c)",
            "read": "sensor.read()",
        },
        "notes": "mock pkg-guide result for local runner",
    },
    "aht20": {
        "source": "upypi",
        "package_name": "aht20-driver",
        "install_cmd": "mpremote mip install aht20-driver",
        "version": "0.1.0",
        "api_ref": {
            "init": "AHT20(i2c)",
            "read": "sensor.measurements",
        },
        "notes": "mock pkg-guide result for local runner",
    },
    "mse 土壤温湿度传感器": {
        "source": "upypi",
        "package_name": "mse-modbus-driver",
        "install_cmd": "mpremote mip install mse-modbus-driver",
        "version": "0.1.0",
        "api_ref": {
            "init": "MSEModbus(uart)",
            "read": "sensor.read()",
        },
        "notes": "mock pkg-guide result for local runner",
    },
}


def builtin_driver_for(device: dict[str, Any]) -> Optional[dict[str, Any]]:
    interface = device.get("interface")
    device_type = str(device.get("type", "")).lower()

    if interface in {"ADC", "I2S", "WiFi", "BLE"}:
        module = BUILTIN_INTERFACE_MODULE_MAP[interface]
    elif interface in {"GPIO", "PWM"} and device_type in BUILTIN_GPIO_DEVICE_TYPES:
        module = BUILTIN_INTERFACE_MODULE_MAP.get(interface, "machine.Pin")
    else:
        return None

    return {
        "source": "builtin_runtime",
        "module": module,
        "notes": f"MicroPython runtime provides {module}; no external driver package required",
    }


def micropython_lib_driver_for(device: dict[str, Any]) -> Optional[dict[str, Any]]:
    name = str(device.get("name", "")).lower()
    device_type = str(device.get("type", "")).lower()
    if name == "aioble" or device_type == "ble_stack":
        return {
            "source": "micropython_lib",
            "package_name": "aioble",
            "install_cmd": "mpremote mip install aioble",
            "repo_url": "https://github.com/micropython/micropython-lib",
            "version": "latest",
            "notes": "official MicroPython BLE helper package",
        }
    return None


def mock_upy_pkg_guide(device: dict[str, Any]) -> dict[str, Any]:
    name = str(device.get("name", "")).lower()
    for key, driver in MOCK_DRIVER_INDEX.items():
        if key in name:
            return dict(driver)
    return {
        "source": "none",
        "notes": "mock pkg-guide found no MicroPython driver",
    }


def resolve_driver(device: dict[str, Any]) -> dict[str, Any]:
    builtin_driver = builtin_driver_for(device)
    if builtin_driver is not None:
        return builtin_driver

    lib_driver = micropython_lib_driver_for(device)
    if lib_driver is not None:
        return lib_driver

    return mock_upy_pkg_guide(device)
