#!/usr/bin/env python3
"""Arduino/C++ 代码 API 映射 + 结构提取脚本。只做映射表查询和代码结构提取，不翻译代码。

用法:
  python convert_arduino.py --input sensor.ino --output sensor_mapping.json

输出 JSON:
{
  "source": "sensor.ino",
  "includes": ["Wire.h", "SPI.h"],
  "global_vars": [{"name": "ADDR", "value": "0x44"}],
  "functions": [{"name": "readSensor", "return_type": "float", "params": [], "line": 42}],
  "api_matches": [{"arduino": "Wire.beginTransmission(0x44)", "mpy_equiv": "i2c.writeto(0x44, buf)", "line": 48}],
  "has_setup_loop": true,
  "error": null
}
"""

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


# Arduino → MicroPython API 映射表
API_MAPPING: List[Tuple[str, str, str]] = [
    # (Arduino 正则, MicroPython 等价写法, 类别)
    # I2C / Wire
    (r"Wire\.begin\(\)", "i2c = I2C(0, scl=Pin(SCL), sda=Pin(SDA))", "I2C"),
    (r"Wire\.beginTransmission\((\w+)\)", "i2c.writeto(\\1, ...)", "I2C"),
    (r"Wire\.endTransmission\(\)", "(I2C write completes after writeto)", "I2C"),
    (r"Wire\.requestFrom\((\w+),\s*(\d+)\)", "data = i2c.readfrom(\\1, \\2)", "I2C"),
    (r"Wire\.write\((.+)\)", "i2c.writeto(addr, bytes([\\1]))", "I2C"),
    (r"Wire\.read\(\)", "i2c.readfrom(addr, 1)[0]", "I2C"),
    (r"Wire\.available\(\)", "(not needed — readfrom returns exact bytes)", "I2C"),
    (r"Wire\.setClock\((\d+)\)", "i2c = I2C(0, freq=\\1)", "I2C"),

    # SPI
    (r"SPI\.begin\(\)", "spi = SPI(0, baudrate=1000000, polarity=0, phase=0)", "SPI"),
    (r"SPI\.beginTransaction\((\w+)\)", "spi.init(baudrate=...)", "SPI"),
    (r"SPI\.transfer\((.+)\)", "spi.write(bytes([\\1])) / spi.read(1)", "SPI"),
    (r"SPI\.endTransaction\(\)", "(not needed — SPI completes after write/read)", "SPI"),

    # UART / Serial
    (r"Serial\.begin\((\d+)\)", "uart = UART(0, baudrate=\\1)", "UART"),
    (r"Serial\.print\((.+)\)", "uart.write(str(\\1))", "UART"),
    (r"Serial\.println\((.+)\)", "uart.write(str(\\1) + '\\r\\n')", "UART"),
    (r"Serial\.read\(\)", "uart.read(1)", "UART"),
    (r"Serial\.available\(\)", "uart.any()", "UART"),
    (r"Serial\.readBytes\((.+)\)", "uart.read(\\1)", "UART"),

    # GPIO / digital
    (r"pinMode\((\w+),\s*OUTPUT\)", "pin = Pin(\\1, Pin.OUT)", "GPIO"),
    (r"pinMode\((\w+),\s*INPUT\)", "pin = Pin(\\1, Pin.IN)", "GPIO"),
    (r"pinMode\((\w+),\s*INPUT_PULLUP\)", "pin = Pin(\\1, Pin.IN, Pin.PULL_UP)", "GPIO"),
    (r"digitalWrite\((\w+),\s*HIGH\)", "pin.value(1)", "GPIO"),
    (r"digitalWrite\((\w+),\s*LOW\)", "pin.value(0)", "GPIO"),
    (r"digitalRead\((\w+)\)", "pin.value()", "GPIO"),
    (r"analogRead\((\w+)\)", "adc = ADC(Pin(\\1)); adc.read()", "ADC"),
    (r"analogWrite\((\w+),\s*(.+)\)", "pwm = PWM(Pin(\\1)); pwm.duty(\\2)", "PWM"),

    # Timing
    (r"delay\((\d+)\)", "time.sleep_ms(\\1)", "Timing"),
    (r"delayMicroseconds\((\d+)\)", "time.sleep_us(\\1)", "Timing"),
    (r"millis\(\)", "time.ticks_ms()", "Timing"),
    (r"micros\(\)", "time.ticks_us()", "Timing"),

    # Interrupts
    (r"attachInterrupt\((\w+),\s*(\w+),\s*(\w+)\)", "pin.irq(handler=\\2, trigger=\\3)", "IRQ"),
    (r"detachInterrupt\((\w+)\)", "pin.irq(handler=None)", "IRQ"),
]


def parse_arduino_source(source_path: str) -> Dict[str, Any]:
    """解析 Arduino/C++ 源文件，提取结构信息。"""
    result: Dict[str, Any] = {
        "source": source_path,
        "includes": [],
        "global_vars": [],
        "functions": [],
        "api_matches": [],
        "has_setup_loop": False,
        "error": None,
    }

    try:
        with open(source_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        result["error"] = "File not found: %s" % source_path
        return result
    except Exception as e:
        result["error"] = "Read failed: %s" % e
        return result

    source_text = "".join(lines)

    # 提取 #include
    include_pattern = re.compile(r'#include\s+[<"](.+?)[>"]')
    result["includes"] = include_pattern.findall(source_text)

    # 检测 setup/loop 结构
    result["has_setup_loop"] = bool(
        re.search(r"void\s+setup\s*\(\s*\)", source_text)
        and re.search(r"void\s+loop\s*\(\s*\)", source_text)
    )

    # 提取全局变量（在函数外部的常量定义）
    global_pattern = re.compile(
        r"^(?:const\s+)?(?:int|float|byte|uint\w+_t|char\s*\*?)\s+(\w+)\s*=\s*(.+?);",
        re.MULTILINE,
    )
    for m in global_pattern.finditer(source_text):
        name, value = m.group(1), m.group(2).strip()
        if not re.search(r"\b(?:if|for|while|return)\b", source_text[max(0, m.start() - 50):m.start()]):
            result["global_vars"].append({"name": name, "value": value})

    # 提取函数签名
    func_pattern = re.compile(
        r"^(?:static\s+)?(?:inline\s+)?"
        r"(?:void|int|float|bool|byte|uint\w+_t|char\s*\*?|String)\s+"
        r"(\w+)\s*\((.*?)\)",
        re.MULTILINE,
    )
    for i, line in enumerate(lines, start=1):
        # 跳过被注释的行
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        m = func_pattern.match(stripped)
        if m:
            name = m.group(1)
            params_raw = m.group(2).strip()
            params = [p.strip() for p in params_raw.split(",") if p.strip()] if params_raw else []
            result["functions"].append({
                "name": name,
                "return_type": stripped.split()[0],
                "params": params,
                "line": i,
            })

    # API 映射匹配
    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        for pattern, mpy_equiv, category in API_MAPPING:
            try:
                m = re.search(pattern, stripped)
                if m:
                    result["api_matches"].append({
                        "arduino": m.group(0),
                        "mpy_equiv": mpy_equiv,
                        "category": category,
                        "line": line_num,
                    })
                    break
            except re.error:
                continue

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Arduino → MicroPython API mapping + structure extraction"
    )
    parser.add_argument("--input", required=True, help="Arduino/C++ source file (.ino/.cpp)")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    result = parse_arduino_source(args.input)

    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(
            "Extracted %d functions, %d API matches, %d includes → %s"
            % (len(result["functions"]), len(result["api_matches"]),
               len(result["includes"]), args.output)
        )
    except Exception as e:
        json.dump(
            {"source": args.input, "api_matches": [], "error": "Write failed: %s" % e},
            sys.stdout, ensure_ascii=False, indent=2,
        )
        sys.exit(1)

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
