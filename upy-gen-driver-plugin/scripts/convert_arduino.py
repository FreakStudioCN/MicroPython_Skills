#!/usr/bin/env python3
"""Extract Arduino/C/C++ source structure and API mapping hints.

This script does not translate source code. It only provides deterministic
structure and API evidence for the LLM workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


API_MAPPING: list[tuple[str, str, str]] = [
    (r"Wire\.begin\(\)", "i2c = I2C(0, scl=Pin(SCL), sda=Pin(SDA))", "I2C"),
    (r"Wire\.beginTransmission\((\w+)\)", "i2c.writeto(\\1, ...)", "I2C"),
    (r"Wire\.endTransmission\(\)", "(I2C write completes after writeto)", "I2C"),
    (r"Wire\.requestFrom\((\w+),\s*(\d+)\)", "data = i2c.readfrom(\\1, \\2)", "I2C"),
    (r"Wire\.write\((.+)\)", "i2c.writeto(addr, bytes([\\1]))", "I2C"),
    (r"Wire\.read\(\)", "i2c.readfrom(addr, 1)[0]", "I2C"),
    (r"SPI\.begin\(\)", "spi = SPI(0, baudrate=1000000, polarity=0, phase=0)", "SPI"),
    (r"SPI\.transfer\((.+)\)", "spi.write(bytes([\\1])) / spi.read(1)", "SPI"),
    (r"Serial\.begin\((\d+)\)", "uart = UART(0, baudrate=\\1)", "UART"),
    (r"Serial\.print\((.+)\)", "uart.write(str(\\1))", "UART"),
    (r"Serial\.println\((.+)\)", "uart.write(str(\\1) + '\\r\\n')", "UART"),
    (r"pinMode\((\w+),\s*OUTPUT\)", "pin = Pin(\\1, Pin.OUT)", "GPIO"),
    (r"pinMode\((\w+),\s*INPUT\)", "pin = Pin(\\1, Pin.IN)", "GPIO"),
    (r"digitalWrite\((\w+),\s*HIGH\)", "pin.value(1)", "GPIO"),
    (r"digitalWrite\((\w+),\s*LOW\)", "pin.value(0)", "GPIO"),
    (r"digitalRead\((\w+)\)", "pin.value()", "GPIO"),
    (r"analogRead\((\w+)\)", "adc = ADC(Pin(\\1)); adc.read()", "ADC"),
    (r"delay\((\d+)\)", "time.sleep_ms(\\1)", "Timing"),
    (r"delayMicroseconds\((\d+)\)", "time.sleep_us(\\1)", "Timing"),
    (r"millis\(\)", "time.ticks_ms()", "Timing"),
    (r"micros\(\)", "time.ticks_us()", "Timing"),
    (r"attachInterrupt\((\w+),\s*(\w+),\s*(\w+)\)", "pin.irq(handler=\\2, trigger=\\3)", "IRQ"),
]


def parse_source(source_path: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": source_path,
        "includes": [],
        "global_vars": [],
        "functions": [],
        "api_matches": [],
        "has_setup_loop": False,
        "error": None,
    }
    try:
        lines = Path(source_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        result["error"] = f"File not found: {source_path}"
        return result
    except Exception as exc:
        result["error"] = f"Read failed: {exc}"
        return result
    source_text = "\n".join(lines)
    result["includes"] = re.findall(r'#include\s+[<"](.+?)[>"]', source_text)
    result["has_setup_loop"] = bool(
        re.search(r"void\s+setup\s*\(\s*\)", source_text)
        and re.search(r"void\s+loop\s*\(\s*\)", source_text)
    )
    global_pattern = re.compile(
        r"^(?:const\s+)?(?:int|float|byte|uint\w+_t|char\s*\*?)\s+(\w+)\s*=\s*(.+?);",
        re.MULTILINE,
    )
    for match in global_pattern.finditer(source_text):
        result["global_vars"].append({"name": match.group(1), "value": match.group(2).strip()})
    func_pattern = re.compile(
        r"^(?:static\s+)?(?:inline\s+)?"
        r"(void|int|float|bool|byte|uint\w+_t|char\s*\*?|String)\s+"
        r"(\w+)\s*\((.*?)\)"
    )
    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        func_match = func_pattern.match(stripped)
        if func_match:
            params_raw = func_match.group(3).strip()
            params = [item.strip() for item in params_raw.split(",") if item.strip()] if params_raw else []
            result["functions"].append({
                "name": func_match.group(2),
                "return_type": func_match.group(1),
                "params": params,
                "line": line_num,
            })
        for pattern, mpy_equiv, category in API_MAPPING:
            match = re.search(pattern, stripped)
            if match:
                result["api_matches"].append({
                    "arduino": match.group(0),
                    "mpy_equiv": mpy_equiv,
                    "category": category,
                    "line": line_num,
                })
                break
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Arduino/C/C++ source structure extraction")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--json-summary", action="store_true")
    args = parser.parse_args()
    result = parse_source(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = result.get("error") is None
    if args.json_summary:
        print(json.dumps({
            "status": "ok" if ok else "error",
            "functions": len(result.get("functions", [])),
            "api_matches": len(result.get("api_matches", [])),
            "includes": result.get("includes", []),
            "source": args.input,
            "output": args.output,
            "message": result.get("error"),
        }, ensure_ascii=False))
    else:
        print(f"Extracted {len(result.get('functions', []))} functions -> {args.output}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
