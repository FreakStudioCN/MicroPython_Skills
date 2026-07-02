#!/usr/bin/env python3
"""Derive component-level wiring topology from project-manifest pinout."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import configure_stdio, load_json, manifest_of, print_json


BUS_PREFIXES = ("i2s_", "i2c_", "spi_", "uart_")
MULTIWIRE_INTERFACES = {"I2S", "I2C", "SPI", "UART"}
MIDDLEWARE_TYPES = {"middleware", "cloud", "service", "software", "library"}
MIDDLEWARE_INTERFACES = {"WIFI", "NETWORK", "HTTP", "HTTPS", "MQTT", "REST"}
POWER_TYPES = {"power_3v3", "power_5v", "power_vin"}
GROUND_TYPES = {"gnd", "ground"}


def slug(value: Any, *, fallback: str = "component") -> str:
    text = str(value or fallback).strip().lower()
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    return text or fallback


def gpio_text(value: Any) -> str:
    return str(value).strip()


def is_gpio(value: Any) -> bool:
    text = gpio_text(value)
    return bool(re.match(r"^(?:GPIO)?\d+$", text, flags=re.IGNORECASE) or re.match(r"^GP\d+$", text, flags=re.IGNORECASE))


def mcu_pin(value: Any) -> str:
    text = gpio_text(value)
    if re.match(r"^\d+$", text):
        return f"GPIO{text}"
    if re.match(r"^gpio\d+$", text, flags=re.IGNORECASE):
        return f"GPIO{text[4:]}"
    return text


def bus_id(value: Any) -> str:
    return str(value or "").strip().upper()


def device_lookup(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    devices = manifest.get("devices")
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(devices, list):
        return result
    for dev in devices:
        if not isinstance(dev, dict):
            continue
        name = dev.get("name")
        if isinstance(name, str) and name:
            result[name] = dev
    return result


def is_physical_device(dev: dict[str, Any] | None) -> bool:
    if not isinstance(dev, dict):
        return True
    dtype = str(dev.get("type") or "").strip().lower()
    iface = str(dev.get("interface") or "").strip().upper()
    if dtype in MIDDLEWARE_TYPES:
        return False
    if iface in MIDDLEWARE_INTERFACES:
        return False
    return True


def component_type(dev: dict[str, Any] | None, name: str) -> str:
    dtype = str((dev or {}).get("type") or "").strip().lower()
    iface = str((dev or {}).get("interface") or "").strip().upper()
    lname = name.lower()
    if dtype == "speaker" or "max98357" in lname or "amplifier" in lname:
        return "audio_amplifier"
    if dtype in {"microphone", "mic"} or "inmp441" in lname or "microphone" in lname:
        return "microphone"
    if dtype in {"led", "button", "buzzer", "relay", "sensor"}:
        return dtype
    if iface == "I2S" and "speaker" in lname:
        return "audio_amplifier"
    if iface == "I2S":
        return "i2s_device"
    return dtype or "device"


def display_name(dev: dict[str, Any] | None, name: str) -> str:
    ctype = component_type(dev, name)
    if "max98357" in name.lower() and "amplifier" not in name.lower():
        return "MAX98357 Audio Amplifier"
    if "inmp441" in name.lower() and "microphone" not in name.lower():
        return "INMP441 Microphone"
    if ctype == "led" and name.upper() == "LED":
        return "Status LED"
    if ctype == "button" and "button" in name.lower():
        return "Push Button"
    return name


def signal_role(pin_type: str, pin_name: str, bus: str = "") -> str:
    lower = pin_type.lower()
    pin = pin_name.upper()
    if lower == "i2s_bck":
        return "BCK"
    if lower == "i2s_ws":
        return "WS"
    if lower == "i2s_data_in":
        return "DATA IN"
    if lower == "i2s_data_out":
        return "DATA OUT"
    if lower.startswith("i2c_"):
        return "SDA" if "data" in lower or pin == "SDA" else "SCL"
    if lower.startswith("spi_"):
        return lower.removeprefix("spi_").upper()
    if lower.startswith("uart_"):
        return lower.removeprefix("uart_").upper()
    if lower == "gpio_in_pullup":
        return "BUTTON" if "button" in pin_name.lower() else "GPIO IN"
    if lower == "gpio_in":
        return "GPIO IN"
    if lower == "gpio_out":
        return "GPIO OUT"
    if lower in POWER_TYPES:
        return "3.3V" if "3v3" in lower else ("5V" if "5v" in lower else "VIN")
    if lower in GROUND_TYPES:
        return "Ground"
    return pin or bus


def normalized_device_pin(device_name: str, device_type: str, pin_name: str, pin_type: str) -> str:
    """Normalize fragile generated pin names into stable schematic labels."""
    original = str(pin_name or "").strip()
    lower_device = str(device_name or "").lower()
    lower_type = str(device_type or "").lower()
    lower_pin_type = str(pin_type or "").lower()
    if lower_type == "led" or "led" in lower_device:
        if lower_pin_type in GROUND_TYPES:
            return "K"
        return "A"
    if lower_type == "button" or "button" in lower_device:
        if lower_pin_type in GROUND_TYPES:
            return "GND"
        return "OUT"
    if "max98357" in lower_device and original.upper() == "SD":
        return "SD"
    return original or "PIN"


def signal_name(pin: dict[str, Any]) -> str:
    ptype = str(pin.get("type") or "").strip()
    pname = str(pin.get("pin_name") or pin.get("signal") or "").strip()
    bus = bus_id(pin.get("bus"))
    role = signal_role(ptype, pname, bus)
    if ptype.lower() in POWER_TYPES:
        return "3.3V" if "3v3" in ptype.lower() else ("5V" if "5v" in ptype.lower() else "VIN")
    if ptype.lower() in GROUND_TYPES:
        return "GND"
    if ptype.lower() in {"gpio_in", "gpio_in_pullup"}:
        return "GPIO IN"
    if ptype.lower() == "gpio_out":
        return "GPIO OUT"
    if bus:
        return f"{bus} {role}"
    if pname:
        return pname
    return role


def conn_kind(pin_type: str) -> str:
    lower = pin_type.lower()
    if lower in POWER_TYPES:
        return "power"
    if lower in GROUND_TYPES:
        return "ground"
    return "signal"


def conn_protocol(pin_type: str, dev: dict[str, Any] | None) -> str:
    lower = pin_type.lower()
    if lower in POWER_TYPES or lower in GROUND_TYPES:
        return "Power"
    if lower.startswith("gpio_") or lower in {"adc", "pwm"}:
        return "GPIO"
    if lower.startswith("i2s_"):
        return "I2S"
    if lower.startswith("i2c_"):
        return "I2C"
    if lower.startswith("spi_"):
        return "SPI"
    if lower.startswith("uart_"):
        return "UART"
    iface = str((dev or {}).get("interface") or "").strip().upper()
    return iface or "GPIO"


def conn_direction(pin_type: str, dev: dict[str, Any] | None, name: str) -> str:
    lower = pin_type.lower()
    if lower in POWER_TYPES:
        return "power"
    if lower in GROUND_TYPES:
        return "ground"
    if lower in {"i2s_data_in", "gpio_in", "gpio_in_pullup"}:
        return "device_to_mcu"
    if lower.startswith("i2c_"):
        return "bidirectional"
    if lower in {"spi_miso", "uart_rx"}:
        return "device_to_mcu"
    return "mcu_to_device"


def endpoint_mcu(pin: dict[str, Any]) -> dict[str, str]:
    gpio = gpio_text(pin.get("gpio"))
    pname = str(pin.get("pin_name") or pin.get("signal") or "").strip()
    role = signal_name(pin)
    endpoint = {"component": "mcu", "pin": mcu_pin(gpio), "role": role}
    if is_gpio(gpio):
        endpoint["gpio"] = re.sub(r"^GPIO", "", gpio, flags=re.IGNORECASE)
    return endpoint


def endpoint_device(component_id: str, pin: dict[str, Any]) -> dict[str, str]:
    pin_name = str(pin.get("pin_name") or pin.get("signal") or "PIN").strip()
    role = signal_role(str(pin.get("type") or ""), pin_name, bus_id(pin.get("bus")))
    return {"component": component_id, "pin": pin_name, "role": role}


def add_component_pin(component: dict[str, Any], pin: str, role: str, ptype: str) -> None:
    pins = component.setdefault("pins", [])
    if not isinstance(pins, list):
        component["pins"] = pins = []
    for existing in pins:
        if isinstance(existing, dict) and existing.get("pin") == pin:
            return
    pins.append({"pin": pin, "role": role, "type": ptype})


def mcu_component(wiring: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    mcu = manifest.get("mcu") if isinstance(manifest.get("mcu"), dict) else {}
    wiring_mcu = wiring.get("mcu") if isinstance(wiring.get("mcu"), dict) else {}
    model = str(mcu.get("model") or mcu.get("name") or wiring_mcu.get("name") or wiring.get("meta", {}).get("mcu_model") or "MCU")
    name = str(mcu.get("display_name") or wiring_mcu.get("package") or model)
    return {
        "id": "mcu",
        "name": name,
        "type": "mcu",
        "model": model,
        "interface": "GPIO",
        "pins": [],
    }


def derive(manifest: dict[str, Any], wiring: dict[str, Any]) -> dict[str, Any]:
    devices = device_lookup(manifest)
    pinout = manifest.get("pinout")
    if not isinstance(pinout, list):
        pinout = []

    output = dict(wiring)
    components: dict[str, dict[str, Any]] = {"mcu": mcu_component(wiring, manifest)}
    component_ids: dict[str, str] = {}
    connections: list[dict[str, Any]] = []
    bus_groups: dict[str, dict[str, Any]] = {}

    for idx, pin in enumerate(pinout):
        if not isinstance(pin, dict):
            continue
        device_name = str(pin.get("device") or "").strip()
        if not device_name:
            continue
        dev = devices.get(device_name)
        if not is_physical_device(dev):
            continue

        cid = component_ids.get(device_name)
        if cid is None:
            base = slug(device_name)
            cid = base
            suffix = 2
            while cid in components:
                cid = f"{base}_{suffix}"
                suffix += 1
            component_ids[device_name] = cid
            comp_name = display_name(dev, device_name)
            components[cid] = {
                "id": cid,
                "name": comp_name,
                "type": component_type(dev, device_name),
                "interface": str((dev or {}).get("interface") or "GPIO"),
                "pins": [],
            }
            model = component_model(device_name)
            if model and model != comp_name:
                components[cid]["model"] = model

        ptype = str(pin.get("type") or "").strip()
        ctype = component_type(dev, device_name)
        raw_pname = str(pin.get("pin_name") or pin.get("signal") or "PIN").strip()
        pname = normalized_device_pin(device_name, ctype, raw_pname, ptype)
        pin_for_endpoint = dict(pin)
        pin_for_endpoint["pin_name"] = pname
        gpio = pin.get("gpio")
        if gpio is None or gpio_text(gpio) == "":
            continue

        kind = conn_kind(ptype)
        protocol = conn_protocol(ptype, dev)
        direction = conn_direction(ptype, dev, device_name)
        signal = signal_name(pin)
        role = signal_role(ptype, pname, bus_id(pin.get("bus")))
        add_component_pin(components[cid], pname, role, kind)
        add_component_pin(components["mcu"], mcu_pin(gpio), signal, kind)

        mcu_ep = endpoint_mcu(pin_for_endpoint)
        dev_ep = endpoint_device(cid, pin_for_endpoint)
        if direction == "device_to_mcu":
            from_ep, to_ep = dev_ep, mcu_ep
        else:
            from_ep, to_ep = mcu_ep, dev_ep
        conn = {
            "net": net_name(pin, device_name, idx),
            "signal": signal,
            "kind": kind,
            "protocol": protocol,
            "direction": direction,
            "from": from_ep,
            "to": to_ep,
        }
        notes = pin.get("notes")
        if isinstance(notes, str) and notes:
            conn["notes"] = notes
        connections.append(conn)

        bkey = str(pin.get("bus") or "").strip()
        if bkey and ptype.lower().startswith(BUS_PREFIXES):
            group = bus_groups.setdefault(
                bkey,
                {
                    "type": bus_protocol_type(ptype),
                    "id": bus_id(bkey),
                    "signals": [],
                    "devices": {},
                },
            )
            bus_role = bus_signal_role(ptype, pname)
            signal_entry = {"role": bus_role, "gpio": gpio_text(gpio)}
            if signal_entry not in group["signals"]:
                group["signals"].append(signal_entry)
            dev_entry = group["devices"].setdefault(
                cid,
                {
                    "name": display_name(dev, device_name),
                    "type": component_type(dev, device_name),
                    "quantity": int((dev or {}).get("quantity") or 1),
                    "pins": [],
                },
            )
            dev_pin = {"role": bus_role, "pin": pname}
            if dev_pin not in dev_entry["pins"]:
                dev_entry["pins"].append(dev_pin)

    buses = []
    for group in bus_groups.values():
        item = dict(group)
        item["devices"] = list(group["devices"].values())
        buses.append(item)

    if len(components) > 1 and connections:
        output["components"] = list(components.values())
        output["connections"] = connections
        output["buses"] = merge_buses(buses, output.get("buses"))
        output["standalone"] = filter_standalone(output.get("standalone"), connections)
        output["power"] = derive_power(connections, output.get("power"))
    return output


def component_model(device_name: str) -> str:
    upper = device_name.upper()
    for token in ("INMP441", "MAX98357", "SHT30", "DHT11", "DHT22", "BME280", "BMP280"):
        if token in upper:
            return token
    return ""


def net_name(pin: dict[str, Any], device_name: str, idx: int) -> str:
    base_parts = [pin.get("bus"), device_name, pin.get("pin_name") or pin.get("signal") or idx]
    base = "_".join(str(part) for part in base_parts if part not in (None, ""))
    return slug(base, fallback=f"net_{idx}")


def bus_protocol_type(pin_type: str) -> str:
    lower = pin_type.lower()
    for prefix in ("i2s", "i2c", "spi", "uart"):
        if lower.startswith(prefix + "_"):
            return prefix
    return "i2c"


def bus_signal_role(pin_type: str, pin_name: str) -> str:
    lower = pin_type.lower()
    pin = pin_name.upper()
    if lower == "i2s_bck":
        return "BCK"
    if lower == "i2s_ws":
        return "WS"
    if lower == "i2s_data_in":
        return "SD"
    if lower == "i2s_data_out":
        return "DIN"
    if lower.startswith("i2c_"):
        return "SDA" if "data" in lower or pin == "SDA" else "SCL"
    if lower.startswith("spi_"):
        return lower.removeprefix("spi_").upper()
    if lower.startswith("uart_"):
        return lower.removeprefix("uart_").upper()
    return pin or "SIGNAL"


def merge_buses(derived: list[dict[str, Any]], existing: Any) -> list[dict[str, Any]]:
    by_id = {str(item.get("id") or "").upper(): item for item in derived if isinstance(item, dict)}
    if isinstance(existing, list):
        for item in existing:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or "").upper()
            if key and key not in by_id and item.get("type") not in (None, ""):
                by_id[key] = item
    return list(by_id.values())


def filter_standalone(existing: Any, connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(existing, list):
        return []
    connected_gpio = {
        endpoint.get("gpio") or re.sub(r"^GPIO", "", str(endpoint.get("pin") or ""), flags=re.IGNORECASE)
        for conn in connections
        for endpoint in (conn.get("from"), conn.get("to"))
        if isinstance(endpoint, dict) and endpoint.get("component") == "mcu"
    }
    result = []
    for item in existing:
        if not isinstance(item, dict):
            continue
        pin = str(item.get("pin") or "")
        name = str(item.get("name") or "").lower()
        if "," in pin:
            continue
        if pin in connected_gpio and any(term in name for term in ("max98357", "inmp441", "i2s")):
            continue
        result.append(item)
    return result


def derive_power(connections: list[dict[str, Any]], existing: Any) -> list[dict[str, Any]]:
    rails: dict[str, dict[str, Any]] = {}
    for conn in connections:
        if not isinstance(conn, dict) or conn.get("kind") not in {"power", "ground"}:
            continue
        signal = str(conn.get("signal") or "")
        rail = "GND" if conn.get("kind") == "ground" else ("3.3V" if "3.3" in signal or "3V3" in signal else signal)
        entry = rails.setdefault(rail, {"rail": rail, "source_pins": [], "consumers": []})
        left = conn.get("from") if isinstance(conn.get("from"), dict) else {}
        right = conn.get("to") if isinstance(conn.get("to"), dict) else {}
        source_pin = left.get("pin")
        consumer = right.get("component")
        if source_pin and source_pin not in entry["source_pins"]:
            entry["source_pins"].append(source_pin)
        if consumer and consumer != "mcu" and consumer not in entry["consumers"]:
            entry["consumers"].append(consumer)
    if rails:
        return list(rails.values())
    return existing if isinstance(existing, list) else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wiring", required=True, help="Input docs/wiring.json path")
    parser.add_argument("--manifest", help="project-manifest.json path")
    parser.add_argument("--upstream", help="phase_complete.upy_generate_plugin.json path")
    parser.add_argument("--output", help="Output wiring JSON path. Defaults to overwriting --wiring")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    wiring_path = Path(args.wiring)
    output_path = Path(args.output) if args.output else wiring_path
    wiring = load_json(wiring_path)

    manifest: dict[str, Any] = {}
    if args.manifest and Path(args.manifest).is_file():
        manifest = load_json(args.manifest)
    if not manifest and args.upstream and Path(args.upstream).is_file():
        manifest = manifest_of(load_json(args.upstream))
    if not manifest:
        print_json({"status": "failed", "errors": ["manifest or upstream manifest_content is required"]})
        return 2

    output = derive(manifest, wiring)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_json(
        {
            "status": "ok",
            "output": str(output_path),
            "components": len(output.get("components", [])) if isinstance(output.get("components"), list) else 0,
            "connections": len(output.get("connections", [])) if isinstance(output.get("connections"), list) else 0,
            "buses": len(output.get("buses", [])) if isinstance(output.get("buses"), list) else 0,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
