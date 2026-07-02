#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render wiring.json to Mermaid .md files plus SVG/PNG.
Reads the intermediate JSON from docs/wiring.json, outputs:
  - wiring.md          (Mermaid wiring schematic)
  - wiring.svg         (SVG via local mmdc first, optional mermaid.ink fallback)
  - wiring.png         (PNG via local mmdc first, optional mermaid.ink fallback)
  - wiring_pins.md     (pin cross-reference table)

Architecture mirrors upy-diagram: JSON → Mermaid code → .md + PNG.
No matplotlib dependency. The renderer prefers local Mermaid CLI (`mmdc`) and only
uses mermaid.ink when network rendering is explicitly allowed.

Usage:
  python render_wiring_local.py --input docs/wiring.json --output docs/
  python render_wiring_local.py --input docs/wiring.json --output docs/ --format png
  python render_wiring_local.py --input docs/wiring.json --output docs/ --format all

Defensive: every field access uses .get() with fallbacks.
Missing or malformed sections are skipped with a stderr warning, never crash.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
import re


def safe_get(d, key, default=None):
    """Get key from dict, never raise. Returns default on any failure."""
    try:
        return d.get(key, default)
    except Exception:
        return default


def safe_list(d, key):
    """Get a list from dict, always returns a list (empty on failure)."""
    try:
        val = d.get(key, [])
        return val if isinstance(val, list) else []
    except Exception:
        return []


def safe_int(d, key, default=0):
    """Get an int from dict, returns default on failure."""
    try:
        return int(d.get(key, default))
    except Exception:
        return default


def load_wiring_json(path):
    """Load wiring.json. Returns (data, error)."""
    if not os.path.isfile(path):
        return None, "wiring.json not found: {}".format(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, "JSON parse error: {}".format(e)
    except Exception as e:
        return None, "read error: {}".format(e)


# ═══════════════════════════════════════════════════════════
#  Mermaid helpers (standalone — mirrors upy-diagram)
# ═══════════════════════════════════════════════════════════

safe_mermaid_chars = str.maketrans({
    '"': "'", "<": "[", ">": "]", "{": "(", "}": ")",
    "(": "（", ")": "）", ";": "；",
    "[": "【", "]": "】", "@": "at", "#": "no.",
})


def mermaid_escape(text):
    """Escape special characters for Mermaid node labels."""
    if not text:
        return ""
    try:
        return str(text).translate(safe_mermaid_chars).replace("\n", " ")
    except Exception:
        return str(text)


def inject_svg_cjk_fonts(data):
    """Inject CJK-compatible fonts into Mermaid SVG bytes."""
    try:
        svg_text = data.decode("utf-8")
        svg_text = svg_text.replace(
            'font-family:"trebuchet ms",verdana,arial,sans-serif',
            'font-family:"Microsoft YaHei","PingFang SC","Noto Sans SC","trebuchet ms",verdana,arial,sans-serif'
        )
        return svg_text.encode("utf-8")
    except Exception:
        return data


def render_mermaid_image_local(mermaid_code, output_path, fmt="svg", timeout_ms=30000):
    """Convert Mermaid code to SVG/PNG with local Mermaid CLI. Returns (path, error)."""
    mmdc = shutil.which("mmdc")
    if not mmdc:
        return None, "local Mermaid CLI not found: mmdc"

    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="upy-wiring-mmdc-") as temp_dir:
            source_path = os.path.join(temp_dir, "wiring.mmd")
            with open(source_path, "w", encoding="utf-8") as f:
                f.write(mermaid_code)
            proc = subprocess.run(
                [
                    mmdc,
                    "-i",
                    source_path,
                    "-o",
                    output_path,
                    "-b",
                    "white",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=max(1, timeout_ms / 1000),
                check=False,
            )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            return None, "local mmdc render failed: {}".format(detail or proc.returncode)
        if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
            return None, "local mmdc produced no output"
        if fmt == "svg":
            try:
                with open(output_path, "rb") as f:
                    data = f.read()
                with open(output_path, "wb") as f:
                    f.write(inject_svg_cjk_fonts(data))
            except Exception:
                pass
        return output_path, None
    except subprocess.TimeoutExpired:
        return None, "local mmdc render timed out after {}ms".format(timeout_ms)
    except Exception as e:
        return None, "local mmdc render failed: {}".format(e)


def render_mermaid_image_network(mermaid_code, output_path, fmt="svg", timeout_ms=30000):
    """Convert Mermaid code to SVG/PNG via mermaid.ink API. Returns (path, error).

    fmt: "svg" (vector, sharp at any scale) or "png" (raster, may be blurry).
    SVG is the default — produces crisp, scalable output.
    Uses GET /svg/<base64> for SVG, /img/<base64> for PNG.

    SVG output is post-processed to inject CJK-compatible fonts (Microsoft YaHei,
    PingFang SC, Noto Sans SC) so Chinese/Japanese/Korean labels render correctly.
    """

    try:
        encoded = base64.urlsafe_b64encode(mermaid_code.encode("utf-8")).decode("ascii")
        if fmt == "svg":
            url = "https://mermaid.ink/svg/{}".format(encoded)
        else:
            url = "https://mermaid.ink/img/{}?type={}".format(encoded, fmt)
        req = urllib.request.Request(url, headers={"User-Agent": "upy-wiring/1.0"})
        with urllib.request.urlopen(req, timeout=max(1, timeout_ms / 1000)) as resp:
            data = resp.read()

        if fmt == "svg":
            data = inject_svg_cjk_fonts(data)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(data)
        return output_path, None
    except Exception as e:
        return None, "mermaid.ink render failed: {}".format(e)


def render_mermaid_image(mermaid_code, output_path, fmt="svg", network_rendering="ask", timeout_ms=30000):
    """Render with local mmdc first, then optional mermaid.ink fallback."""
    local_path, local_error = render_mermaid_image_local(mermaid_code, output_path, fmt=fmt, timeout_ms=timeout_ms)
    if local_path:
        return local_path, None, "local_mmdc"

    if network_rendering == "deny":
        return None, local_error, None

    network_path, network_error = render_mermaid_image_network(mermaid_code, output_path, fmt=fmt, timeout_ms=timeout_ms)
    if network_path:
        return network_path, None, "mermaid_ink"

    return None, "{}; {}".format(local_error, network_error), None


# ═══════════════════════════════════════════════════════════
#  wiring.md — Mermaid wiring schematic
# ═══════════════════════════════════════════════════════════

PIN_TYPE_COLORS = {
    "power_3v3":       "#FF9800",
    "power_5v":        "#F44336",
    "gnd":             "#212121",
    "i2c_data":        "#2196F3",
    "i2c_clock":       "#2196F3",
    "spi_mosi":        "#4CAF50",
    "spi_miso":        "#4CAF50",
    "spi_sck":         "#4CAF50",
    "spi_cs":          "#4CAF50",
    "uart_tx":         "#FF9800",
    "uart_rx":         "#FF9800",
    "gpio_out":        "#607D8B",
    "gpio_in":         "#607D8B",
    "gpio_in_pullup":  "#607D8B",
    "adc":             "#E91E63",
    "pwm":             "#00BCD4",
    "i2s":             "#3F51B5",
    "special":         "#9E9E9E",
}

BUS_COLORS = {
    "i2c":     "#2196F3",
    "spi":     "#4CAF50",
    "uart":    "#FF9800",
    "onewire": "#9C27B0",
    "can":     "#795548",
    "i2s":     "#3F51B5",
}

ALERT_LEVEL_COLORS = {"info": "#2196F3", "warning": "#FF9800", "danger": "#F44336"}


def node_id(prefix, value):
    """Build a stable Mermaid node id from arbitrary component text."""
    text = str(value or prefix)
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", text).strip("_")
    if not safe:
        safe = prefix
    if safe[0].isdigit():
        safe = "{}_{}".format(prefix, safe)
    return "{}_{}".format(prefix, safe)


def endpoint_label(endpoint):
    """Return the compact display label for one connection endpoint."""
    if not isinstance(endpoint, dict):
        return ""
    label = safe_get(endpoint, "label", "")
    if label:
        return str(label)
    pin = safe_get(endpoint, "pin", "")
    role = safe_get(endpoint, "role", "")
    gpio = safe_get(endpoint, "gpio", "")
    parts = []
    pin_text = str(pin)
    gpio_text = str(gpio)
    pin_without_gpio_prefix = re.sub(r"^GPIO", "", pin_text, flags=re.IGNORECASE)
    if gpio and gpio_text != pin_text and gpio_text != pin_without_gpio_prefix:
        parts.append(str(gpio))
    if pin:
        parts.append(str(pin))
    if role and str(role) not in parts:
        parts.append(str(role))
    return " / ".join(parts)


def connection_edge_label(conn):
    """Build a pin-to-pin edge label for component topology rendering."""
    if not isinstance(conn, dict):
        return ""
    signal = safe_get(conn, "signal", "")
    left = endpoint_label(safe_get(conn, "from", {}))
    right = endpoint_label(safe_get(conn, "to", {}))
    pieces = []
    if left:
        pieces.append(left)
    if signal and signal not in pieces:
        pieces.append(signal)
    if right:
        pieces.append(right)
    return " → ".join(pieces)


def connection_arrow(conn):
    direction = safe_get(conn, "direction", "")
    kind = safe_get(conn, "kind", "signal")
    if direction in ("power", "ground") or kind in ("power", "ground"):
        return "-.->"
    if direction == "device_to_mcu":
        return "-->"
    if direction == "bidirectional":
        return "<-->"
    return "-->"


def _component_nodes(wiring):
    """Return component node map. Prefer explicit components, infer from legacy data otherwise."""
    components = safe_list(wiring, "components")
    if not components:
        return {}, []
    nodes = {}
    ordered = []
    for idx, comp in enumerate(components):
        if not isinstance(comp, dict):
            continue
        cid = safe_get(comp, "id", "") or safe_get(comp, "name", "") or "component_{}".format(idx)
        nid = node_id("c", cid)
        name = safe_get(comp, "name", cid)
        model = safe_get(comp, "model", "")
        interface = safe_get(comp, "interface", "")
        ctype = safe_get(comp, "type", "")
        label_parts = [name]
        if model and model != name:
            label_parts.append(model)
        if interface:
            label_parts.append(interface)
        elif ctype:
            label_parts.append(ctype)
        label = "<br/>".join(mermaid_escape(part) for part in label_parts if part)
        nodes[str(cid)] = nid
        nodes[str(name)] = nid
        ordered.append((nid, comp, label))
    return nodes, ordered


def _component_display_names(wiring):
    """Map component ids and names to user-facing component names."""
    names = {}
    for idx, comp in enumerate(safe_list(wiring, "components")):
        if not isinstance(comp, dict):
            continue
        cid = safe_get(comp, "id", "") or safe_get(comp, "name", "") or "component_{}".format(idx)
        name = safe_get(comp, "name", cid)
        names[str(cid)] = str(name)
        names[str(name)] = str(name)
    return names


def compact_endpoint_label(endpoint, component_names=None, include_component=False):
    """Return a short endpoint label for readable component topology diagrams."""
    if not isinstance(endpoint, dict):
        return ""
    component_names = component_names or {}
    component = safe_get(endpoint, "component", "")
    component_name = component_names.get(str(component), component)
    pin = str(safe_get(endpoint, "pin", "") or "")
    role = str(safe_get(endpoint, "role", "") or "")
    gpio = str(safe_get(endpoint, "gpio", "") or "")
    if str(component).lower() == "mcu":
        if pin:
            label = pin
        elif gpio:
            label = "GPIO{}".format(gpio) if gpio.isdigit() else gpio
        else:
            label = role
        if role and role != label and role not in label:
            label = "{} {}".format(label, role)
        return label
    if include_component and component_name:
        return "{}.{}".format(component_name, pin) if pin else str(component_name)
    return pin or role


def connection_node_label(conn, component_names):
    """Build the middle net-node label instead of a long Mermaid edge label."""
    if not isinstance(conn, dict):
        return ""
    left = safe_get(conn, "from", {})
    right = safe_get(conn, "to", {})
    direction = safe_get(conn, "direction", "")
    signal = str(safe_get(conn, "signal", "") or "")
    if direction == "device_to_mcu":
        mcu_ep, dev_ep = right, left
    else:
        mcu_ep, dev_ep = left, right
    left_label = compact_endpoint_label(mcu_ep, component_names=component_names)
    right_label = compact_endpoint_label(dev_ep, component_names=component_names, include_component=True)
    if signal and signal not in left_label:
        left_label = "{} {}".format(left_label, signal).strip()
    if left_label and right_label:
        return "{} to {}".format(left_label, right_label)
    return signal or left_label or right_label


def _build_component_topology_mermaid(wiring):
    """Build component-level, pin-annotated wiring topology Mermaid code."""
    components = safe_list(wiring, "components")
    connections = safe_list(wiring, "connections")
    if not components or not connections:
        return None

    lines = [
        "%%{init: {'theme': 'base', 'themeVariables': {'background': '#ffffff', 'mainBkg': '#ffffff'}}}%%",
        "graph LR",
    ]
    node_map, ordered = _component_nodes(wiring)
    display_names = _component_display_names(wiring)

    for nid, comp, label in ordered:
        ctype = safe_get(comp, "type", "")
        interface = safe_get(comp, "interface", "")
        fill = "#ECEFF1"
        stroke = "#607D8B"
        if ctype == "mcu":
            fill, stroke = "#E3F2FD", "#1565C0"
        elif interface.upper() == "I2S" or ctype in ("microphone", "audio_amplifier"):
            fill, stroke = "#E8EAF6", "#3F51B5"
        elif ctype in ("led", "button", "buzzer"):
            fill, stroke = "#F1F8E9", "#558B2F"
        lines.append('  {}["{}"]'.format(nid, label))
        lines.append("  style {} fill:{},stroke:{},stroke-width:2px,color:#263238".format(nid, fill, stroke))

    lines.append("")
    for idx, conn in enumerate(connections):
        if not isinstance(conn, dict):
            continue
        left = safe_get(conn, "from", {})
        right = safe_get(conn, "to", {})
        left_key = safe_get(left, "component", "")
        right_key = safe_get(right, "component", "")
        src_node = node_map.get(str(left_key))
        dst_node = node_map.get(str(right_key))
        if not src_node or not dst_node:
            continue
        label = mermaid_escape(connection_node_label(conn, display_names))
        net_node = "net_{}".format(idx)
        kind = safe_get(conn, "kind", "signal")
        protocol = str(safe_get(conn, "protocol", "") or "").upper()
        if kind in ("power", "ground"):
            fill, stroke = "#FFF3E0", "#F57C00"
        elif protocol == "I2S":
            fill, stroke = "#EEF2FF", "#3F51B5"
        elif protocol == "GPIO":
            fill, stroke = "#F7F9FA", "#607D8B"
        else:
            fill, stroke = "#F7F9FA", "#546E7A"
        lines.append('  {}["{}"]'.format(net_node, label))
        lines.append("  style {} fill:{},stroke:{},stroke-width:1px,color:#263238".format(net_node, fill, stroke))
        arrow = connection_arrow(conn)
        if arrow == "<-->":
            lines.append("  {} --- {}".format(src_node, net_node))
            lines.append("  {} --- {}".format(net_node, dst_node))
        elif arrow == "-.->":
            lines.append("  {} -.-> {}".format(src_node, net_node))
            lines.append("  {} -.-> {}".format(net_node, dst_node))
        else:
            lines.append("  {} --> {}".format(src_node, net_node))
            lines.append("  {} --> {}".format(net_node, dst_node))

    return "\n".join(lines)

    alerts = safe_list(wiring, "alerts")
    if alerts:
        lines.append("")
        lines.append("  subgraph alerts_sg[注意事项]")
        lines.append("    style alerts_sg fill:#FFF8E1,stroke:#F9A825,stroke-dasharray: 5 5")
        for ai, alert in enumerate(alerts):
            if not isinstance(alert, dict):
                continue
            level = safe_get(alert, "level", "info")
            msg = safe_get(alert, "msg", "")
            icon = {"info": "[i]", "warning": "[!]", "danger": "[!!]"}.get(level, "[?]")
            color = ALERT_LEVEL_COLORS.get(level, "#9E9E9E")
            aid = "al_{}".format(ai)
            lines.append('    {}["{}"]'.format(aid, mermaid_escape("{} {}".format(icon, msg))))
            lines.append("    style {} fill:{},stroke:#37474F,color:#fff".format(aid, color))
        lines.append("  end")

    return "\n".join(lines)


def _build_wiring_mermaid(wiring):
    """Build Mermaid graph TB string for wiring schematic. Returns str or None."""
    try:
        topology = _build_component_topology_mermaid(wiring)
        if topology:
            return topology

        lines = ["graph TB"]
        meta = safe_get(wiring, "meta", {})
        project = safe_get(meta, "project", "Unknown Project")
        mcu_model = safe_get(meta, "mcu_model", "MCU")

        # ── MCU subgraph with used pins ──
        mcu = safe_get(wiring, "mcu", {})
        mcu_name = safe_get(mcu, "name", "MCU")
        mcu_package = safe_get(mcu, "package", "")
        pins = safe_list(mcu, "pins")

        mcu_title = mermaid_escape("{} ({})".format(mcu_model, mcu_name))
        if mcu_package:
            mcu_title = mermaid_escape("{} — {} ({})".format(mcu_model, mcu_package, mcu_name))

        lines.append("  subgraph mcu_sg[{}]".format(mcu_title))
        lines.append("    direction TB")

        pin_nodes = {}  # gpio → node_id
        for p in pins:
            if not isinstance(p, dict):
                continue
            try:
                gpio = safe_get(p, "gpio", "??")
                phys = safe_int(p, "physical_pin", 0)
                label = safe_get(p, "label", "")
                ptype = safe_get(p, "type", "special")
                side = safe_get(p, "side", "")

                node_id = "mp_" + gpio.replace("(", "_").replace(")", "_").replace(".", "_").replace(" ", "_")
                pin_nodes[gpio] = node_id

                # Build compact label
                pin_label = gpio
                if phys:
                    pin_label = "{} Pin{}".format(gpio, phys)
                if label and label != gpio:
                    pin_label = "{}<br/>{}".format(pin_label, mermaid_escape(label))

                # Colour by pin type
                color = PIN_TYPE_COLORS.get(ptype, "#9E9E9E")
                lines.append('    {}["{}"]'.format(node_id, pin_label))
                lines.append("    style {} fill:{},stroke:#37474F,color:#fff".format(
                    node_id, color))
            except Exception:
                pass

        lines.append("  end")
        lines.append("")

        # ── Bus subgraphs ──
        buses = safe_list(wiring, "buses")
        bus_device_nodes = {}  # device_name → node_id
        bus_idx = 0
        for bus in buses:
            if not isinstance(bus, dict):
                continue
            try:
                btype = safe_get(bus, "type", "i2c")
                bid = safe_get(bus, "id", "?")
                freq = safe_int(bus, "frequency_hz", 0)
                devices = safe_list(bus, "devices")

                bus_label = "{} {}".format(btype.upper(), bid)
                if freq:
                    if freq >= 1000000:
                        bus_label = "{} @ {:.1f}MHz".format(bus_label, freq / 1000000)
                    elif freq >= 1000:
                        bus_label = "{} @ {}kHz".format(bus_label, freq // 1000)
                    else:
                        bus_label = "{} @ {}Hz".format(bus_label, freq)
                bus_label = mermaid_escape(bus_label)

                sg_id = "bus_sg_{}".format(bus_idx)
                lines.append("  subgraph {}[{}]".format(sg_id, bus_label))
                color = BUS_COLORS.get(btype, "#607D8B")
                lines.append("    style {} fill:#fafafa,stroke:{},stroke-width:2px".format(sg_id, color))

                for di, dev in enumerate(devices):
                    if not isinstance(dev, dict):
                        continue
                    try:
                        d_name = safe_get(dev, "name", "Device")
                        d_addr = safe_get(dev, "addr", "")
                        d_cs = safe_get(dev, "cs_gpio", "")

                        node_id = "bd_{}_{}".format(bus_idx, di)
                        bus_device_nodes[d_name] = node_id

                        d_label = mermaid_escape(d_name)
                        if d_addr:
                            d_label = "{}<br/>{}".format(d_label, d_addr)
                        if d_cs:
                            d_label = "{}<br/>CS={}".format(d_label, mermaid_escape(d_cs))

                        lines.append('    {}["{}"]'.format(node_id, d_label))
                    except Exception:
                        pass

                lines.append("  end")
                lines.append("")
                bus_idx += 1
            except Exception:
                bus_idx += 1

        # ── Standalone GPIO devices ──
        standalones = safe_list(wiring, "standalone")
        standalone_nodes = {}
        if standalones:
            lines.append("  subgraph sa_sg[独立 GPIO 器件]")
            for si, sa in enumerate(standalones):
                if not isinstance(sa, dict):
                    continue
                try:
                    sa_name = safe_get(sa, "name", "Device")
                    sa_ext = safe_get(sa, "external_components", "")
                    sa_pin = safe_get(sa, "pin", "??")

                    node_id = "sa_{}".format(si)
                    standalone_nodes[sa_name] = node_id

                    sa_label = mermaid_escape(sa_name)
                    if sa_ext:
                        sa_label = "{}<br/>{}".format(sa_label, mermaid_escape(sa_ext))
                    if sa_pin != "??":
                        sa_label = "{}<br/>← {}".format(sa_label, mermaid_escape(sa_pin))

                    lines.append('    {}["{}"]'.format(node_id, sa_label))
                except Exception:
                    pass
            lines.append("  end")
            lines.append("")

        # ── Power connections (dotted edges from power pins to all consumers) ──
        power_list = safe_list(wiring, "power")
        for pwr in power_list:
            if not isinstance(pwr, dict):
                continue
            try:
                rail = safe_get(pwr, "rail", "?")
                source_pins = safe_list(pwr, "source_pins")
                consumers = safe_list(pwr, "consumers")

                for sp in source_pins:
                    src_node = pin_nodes.get(str(sp))
                    if not src_node:
                        continue
                    for consumer in consumers:
                        # Check bus devices
                        dst_node = bus_device_nodes.get(str(consumer))
                        if not dst_node:
                            dst_node = standalone_nodes.get(str(consumer))
                        if not dst_node:
                            continue
                        lines.append("  {} -.->|{}| {}".format(
                            src_node, mermaid_escape(rail), dst_node))
            except Exception:
                pass

        # ── Bus signal edges (pin → device) ──
        bus_idx = 0
        for bus in buses:
            if not isinstance(bus, dict):
                bus_idx += 1
                continue
            try:
                signals = safe_list(bus, "signals")
                devices = safe_list(bus, "devices")

                for sig in signals:
                    if not isinstance(sig, dict):
                        continue
                    s_role = safe_get(sig, "role", "?")
                    s_gpio = safe_get(sig, "gpio", "")
                    src_node = pin_nodes.get(s_gpio)
                    if not src_node:
                        continue
                    for di, dev in enumerate(devices):
                        if not isinstance(dev, dict):
                            continue
                        d_name = safe_get(dev, "name", "")
                        dst_node = bus_device_nodes.get(d_name)
                        if not dst_node:
                            continue
                        lines.append("  {} -->|{}| {}".format(
                            src_node, mermaid_escape(s_role), dst_node))
            except Exception:
                pass
            bus_idx += 1

        # ── Standalone GPIO edges ──
        for si, sa in enumerate(standalones):
            if not isinstance(sa, dict):
                continue
            try:
                sa_pin = safe_get(sa, "pin", "")
                sa_name = safe_get(sa, "name", "")
                src_node = pin_nodes.get(sa_pin)
                dst_node = standalone_nodes.get(sa_name)
                if src_node and dst_node:
                    lines.append("  {} --> {}".format(src_node, dst_node))
            except Exception:
                pass

        # ── Alerts section ──
        alerts = safe_list(wiring, "alerts")
        if alerts:
            lines.append("")
            lines.append("  subgraph alerts_sg[注意事项]")
            lines.append("    style alerts_sg fill:#FFF8E1,stroke:#F9A825,stroke-dasharray: 5 5")
            for ai, alert in enumerate(alerts):
                if not isinstance(alert, dict):
                    continue
                try:
                    level = safe_get(alert, "level", "info")
                    msg = safe_get(alert, "msg", "")
                    icon = {"info": "[i]", "warning": "[!]", "danger": "[!!]"}.get(level, "[?]")
                    color = ALERT_LEVEL_COLORS.get(level, "#9E9E9E")

                    node_id = "al_{}".format(ai)
                    alert_text = mermaid_escape("{} {}".format(icon, msg))
                    lines.append('    {}["{}"]'.format(node_id, alert_text))
                    lines.append("    style {} fill:{},stroke:#37474F,color:#fff".format(
                        node_id, color))
                except Exception:
                    pass
            lines.append("  end")

        return "\n".join(lines)
    except Exception:
        return None


def render_wiring_schematic(wiring, output_dir):
    """Generate wiring.md with Mermaid wiring schematic. Returns (filepath, warnings)."""
    warnings = []
    try:
        mermaid_code = _build_wiring_mermaid(wiring)
        if not mermaid_code:
            return None, ["failed to build wiring mermaid code"]

        meta = safe_get(wiring, "meta", {})
        project = safe_get(meta, "project", "Unknown Project")
        mcu_model = safe_get(meta, "mcu_model", "MCU")

        lines = [
            "# {} — 接线示意图".format(project),
            "",
            "> MCU: **{}** | 生成时间: {}".format(
                mcu_model, safe_get(meta, "generated_at", "N/A")),
            "",
            "```mermaid",
            mermaid_code,
            "```",
            "",
        ]

        out_path = os.path.join(output_dir, "wiring.md")
        os.makedirs(output_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return out_path, warnings
    except Exception as e:
        return None, ["wiring schematic render exception: {}".format(e)]


def render_wiring_svg(wiring, output_dir, fmt="svg", network_rendering="ask", timeout_ms=30000):
    """Render wiring schematic to SVG/PNG. Returns (filepath, warnings)."""
    warnings = []
    try:
        mermaid_code = _build_wiring_mermaid(wiring)
        if not mermaid_code:
            return None, ["failed to build wiring mermaid code for image"]

        out_path = os.path.join(output_dir, "wiring.{}".format(fmt))
        path, err, backend = render_mermaid_image(
            mermaid_code,
            out_path,
            fmt=fmt,
            network_rendering=network_rendering,
            timeout_ms=timeout_ms,
        )
        if path:
            if backend:
                warnings.append("wiring {} backend: {}".format(fmt, backend))
            return path, warnings
        if err:
            warnings.append(err)
        return None, warnings
    except Exception as e:
        return None, ["wiring {} render exception: {}".format(fmt, e)]


# ═══════════════════════════════════════════════════════════
#  wiring_pins.md — pin cross-reference table
# ═══════════════════════════════════════════════════════════

def render_pin_table(wiring, output_dir):
    """Generate wiring_pins.md pin cross-reference table. Returns (filepath, warnings)."""
    warnings = []
    lines = []
    try:
        meta = safe_get(wiring, "meta", {})
        project = safe_get(meta, "project", "Unknown Project")

        # Build gpio → {physical_pin, gpio_label} lookup from mcu.pins
        pin_map = {}
        mcu = safe_get(wiring, "mcu", {})
        for p in safe_list(mcu, "pins"):
            if not isinstance(p, dict):
                continue
            gpio_key = safe_get(p, "gpio", "")
            pin_map[gpio_key] = {
                "physical": str(safe_int(p, "physical_pin")) if safe_int(p, "physical_pin") else "—",
                "gpio_label": gpio_key,
            }

        lines.append("# {} — 引脚对照表".format(project))
        lines.append("")

        connections = safe_list(wiring, "connections")
        if connections:
            display_names = _component_display_names(wiring)
            lines.append("| # | 信号 / Net | 源组件 | 源引脚 | 目标组件 | 目标引脚 | 协议 | 方向 | 备注 |")
            lines.append("|---|------------|--------|--------|----------|----------|------|------|------|")
            idx = 0
            for conn in connections:
                if not isinstance(conn, dict):
                    continue
                idx += 1
                left = safe_get(conn, "from", {})
                right = safe_get(conn, "to", {})
                signal = safe_get(conn, "signal", safe_get(conn, "net", "?"))
                source_key = safe_get(left, "component", "?")
                target_key = safe_get(right, "component", "?")
                source = display_names.get(str(source_key), source_key)
                target = display_names.get(str(target_key), target_key)
                source_pin = endpoint_label(left) or "—"
                target_pin = endpoint_label(right) or "—"
                protocol = safe_get(conn, "protocol", safe_get(conn, "kind", "signal"))
                direction = safe_get(conn, "direction", "mcu_to_device")
                notes = safe_get(conn, "notes", "")
                lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    idx,
                    signal,
                    source,
                    source_pin,
                    target,
                    target_pin,
                    protocol,
                    direction,
                    notes or "-",
                ))
            lines.append("")
            lines.append("## 注意事项")
            lines.append("")
            for alert in safe_list(wiring, "alerts"):
                if not isinstance(alert, dict):
                    continue
                level = safe_get(alert, "level", "info")
                msg = safe_get(alert, "msg", "")
                prefix = "> " if level == "info" else "> **{}** ".format(level.upper())
                lines.append(prefix + msg)

            out_path = os.path.join(output_dir, "wiring_pins.md")
            os.makedirs(output_dir, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return out_path, warnings

        lines.append("| # | 器件 | MCU 引脚 | GPIO | 协议 | 地址 / 备注 |")
        lines.append("|---|------|---------|------|------|-------------|")

        idx = 0
        buses = safe_list(wiring, "buses")
        for bus in buses:
            if not isinstance(bus, dict):
                continue
            btype = safe_get(bus, "type", "?")
            bid = safe_get(bus, "id", "?")
            signals = safe_list(bus, "signals")
            sig_str = ", ".join(
                "{}={}".format(
                    safe_get(s, "role", "?"),
                    safe_get(s, "gpio", "?")
                ) for s in signals if isinstance(s, dict)
            )
            phys_pins = []
            gpio_labels = []
            for s in signals:
                if not isinstance(s, dict):
                    continue
                s_gpio = safe_get(s, "gpio", "")
                pinfo = pin_map.get(s_gpio, {})
                phys = pinfo.get("physical", "—")
                gpio_l = pinfo.get("gpio_label", s_gpio)
                if phys != "—":
                    phys_pins.append(phys)
                if gpio_l != "—":
                    gpio_labels.append(gpio_l)

            devices = safe_list(bus, "devices")
            for dev in devices:
                if not isinstance(dev, dict):
                    continue
                idx += 1
                d_name = safe_get(dev, "name", "?")
                d_addr = safe_get(dev, "addr", "")
                d_cs = safe_get(dev, "cs_gpio", "")
                note = d_addr if d_addr else ("CS={}".format(d_cs) if d_cs else "")
                phys_str = ", ".join(phys_pins) if phys_pins else "—"
                gpio_str = ", ".join(gpio_labels) if gpio_labels else "—"
                lines.append("| {} | {} | {} | {} | {} {} ({}) | {} |".format(
                    idx, d_name, phys_str, gpio_str, btype.upper(), bid, sig_str, note))

        standalones = safe_list(wiring, "standalone")
        for sa in standalones:
            if not isinstance(sa, dict):
                continue
            idx += 1
            sa_pin = safe_get(sa, "pin", "?")
            pinfo = pin_map.get(sa_pin, {})
            phys_str = pinfo.get("physical", "—")
            gpio_str = pinfo.get("gpio_label", sa_pin)
            lines.append("| {} | {} | {} | {} | GPIO | {} |".format(
                idx,
                safe_get(sa, "name", "?"),
                phys_str,
                gpio_str,
                safe_get(sa, "external_components", "") or "-"
            ))

        # Alerts section
        alerts = safe_list(wiring, "alerts")
        if alerts:
            lines.append("")
            lines.append("## 注意事项")
            lines.append("")
            for alert in alerts:
                if not isinstance(alert, dict):
                    continue
                level = safe_get(alert, "level", "info")
                msg = safe_get(alert, "msg", "")
                prefix = "> " if level == "info" else "> **{}** ".format(level.upper())
                lines.append(prefix + msg)

        out_path = os.path.join(output_dir, "wiring_pins.md")
        os.makedirs(output_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return out_path, warnings
    except Exception as e:
        return None, ["pin table render exception: {}".format(e)]


# ═══════════════════════════════════════════════════════════
#  wiring.html — self-contained HTML page (Mermaid.js CDN)
# ═══════════════════════════════════════════════════════════

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{ --bg: #fff; --text: #333; --border: #e0e0e0; --code-bg: #f8f8f8; --tab-active: #1a73e8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #1e1e1e; --text: #ddd; --border: #444; --code-bg: #2d2d2d; --tab-active: #5caeff; }} }}
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: var(--bg); color: var(--text); }}
  h1 {{ font-size: 1.4em; margin-bottom: 4px; }}
  .meta {{ color: #888; font-size: 0.85em; margin-bottom: 16px; }}
  .tabs {{ display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 2px solid var(--border); }}
  .tabs button {{ padding: 8px 20px; border: none; background: transparent; cursor: pointer; font-size: 14px; color: var(--text); border-bottom: 2px solid transparent; margin-bottom: -2px; }}
  .tabs button:hover {{ color: var(--tab-active); }}
  .tabs button.active {{ color: var(--tab-active); border-bottom-color: var(--tab-active); font-weight: 600; }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .source {{ background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; overflow-x: auto; }}
  .source pre {{ margin: 0; white-space: pre-wrap; font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", monospace; font-size: 13px; line-height: 1.5; }}
  .mermaid {{ text-align: center; padding: 20px 0; }}
  .mermaid svg {{ max-width: 100%; height: auto; }}
  #fallback {{ display: none; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">MCU: {mcu_model} | Project: {project} | Generated: {generated_at}</div>

<div class="tabs">
  <button class="active" onclick="switchTab('diagram')">{tab_diagram}</button>
  <button onclick="switchTab('source')">{tab_source}</button>
</div>

<div id="diagram" class="panel active">
  <div class="mermaid">
{MERMAID_CODE}
  </div>
  <div id="fallback" class="source">
    <p style="color:#f44336">Mermaid.js failed to load. Showing source code instead.</p>
    <pre>{MERMAID_ESCAPED}</pre>
  </div>
</div>

<div id="source" class="panel">
  <div class="source">
    <pre>{MERMAID_ESCAPED}</pre>
  </div>
</div>

<script>
function switchTab(id) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}}
</script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({{ startOnLoad: true, theme: 'default', securityLevel: 'loose' }});
  window.addEventListener('error', function(e) {{
    if (e.target && e.target.tagName === 'SCRIPT' && e.target.src.includes('mermaid')) {{
      document.getElementById('fallback').style.display = 'block';
    }}
  }}, true);
</script>
</body>
</html>"""


def _mermaid_html_escape(text):
    """Escape Mermaid code for safe embedding in HTML <pre>."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_wiring_html(wiring, output_dir):
    """Generate wiring.html — self-contained HTML with Mermaid.js CDN. Returns (filepath, warnings)."""
    warnings = []
    try:
        mermaid_code = _build_wiring_mermaid(wiring)
        if not mermaid_code:
            return None, ["failed to build wiring mermaid code for HTML"]

        meta = safe_get(wiring, "meta", {})
        project = safe_get(meta, "project", "Unknown Project")
        mcu_model = safe_get(meta, "mcu_model", "MCU")
        generated_at = safe_get(meta, "generated_at", "N/A")

        html = HTML_TEMPLATE.format(
            title="{} — 接线示意图".format(project),
            project=project,
            mcu_model=mcu_model,
            generated_at=generated_at,
            tab_diagram="接线图",
            tab_source="Mermaid 源码",
            MERMAID_CODE=mermaid_code,
            MERMAID_ESCAPED=_mermaid_html_escape(mermaid_code),
        )

        out_path = os.path.join(output_dir, "wiring.html")
        os.makedirs(output_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        return out_path, warnings
    except Exception as e:
        return None, ["wiring HTML render exception: {}".format(e)]


# ═══════════════════════════════════════════════════════════
#  main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Render wiring.json to Mermaid .md files plus SVG/PNG")
    parser.add_argument("--input", required=True, help="Path to wiring.json")
    parser.add_argument("--output", required=True, help="Output directory (e.g. docs/)")
    parser.add_argument("--format", default="all",
                        choices=["md", "svg", "png", "html", "all"],
                        help="Output format: md (Mermaid .md), svg (vector), "
                             "png (raster), html (self-contained browser page), "
                             "all (md + svg + png + html)")
    parser.add_argument("--network-rendering", default="ask", choices=["ask", "allow", "deny"],
                        help="Network rendering policy for mermaid.ink fallback.")
    parser.add_argument("--timeout-ms", type=int, default=30000,
                        help="Render timeout in milliseconds for local mmdc and network fallback.")
    args = parser.parse_args()

    wiring, err = load_wiring_json(args.input)
    if err:
        print("[FAIL] {}".format(err), file=sys.stderr)
        sys.exit(1)
    try:
        os.makedirs(args.output, exist_ok=True)
    except Exception as e:
        print("[FAIL] cannot create output directory {}: {}".format(args.output, e), file=sys.stderr)
        sys.exit(1)

    all_warnings = []
    ok_count = 0
    generated = {"md": False, "svg": False, "png": False, "html": False, "pins": False}

    # ── Mermaid .md schematic ──
    if args.format in ("md", "all"):
        try:
            path, warns = render_wiring_schematic(wiring, args.output)
            all_warnings.extend(warns)
            if path:
                print("[OK] {}".format(path))
                generated["md"] = True
                ok_count += 1
        except Exception as e:
            all_warnings.append("wiring schematic .md crashed: {}".format(e))
            print("[WARN] wiring schematic .md crashed: {}".format(e), file=sys.stderr)

    # ── SVG / PNG via local mmdc, optional mermaid.ink fallback ──
    if args.format in ("svg", "all"):
        try:
            path, warns = render_wiring_svg(
                wiring,
                args.output,
                fmt="svg",
                network_rendering=args.network_rendering,
                timeout_ms=args.timeout_ms,
            )
            all_warnings.extend(warns)
            if path:
                print("[OK] {}".format(path))
                generated["svg"] = True
                ok_count += 1
        except Exception as e:
            all_warnings.append("wiring SVG crashed: {}".format(e))
            print("[WARN] wiring SVG crashed: {}".format(e), file=sys.stderr)

    if args.format in ("png", "all"):
        try:
            path, warns = render_wiring_svg(
                wiring,
                args.output,
                fmt="png",
                network_rendering=args.network_rendering,
                timeout_ms=args.timeout_ms,
            )
            all_warnings.extend(warns)
            if path:
                print("[OK] {}".format(path))
                generated["png"] = True
                ok_count += 1
        except Exception as e:
            all_warnings.append("wiring PNG crashed: {}".format(e))
            print("[WARN] wiring PNG crashed: {}".format(e), file=sys.stderr)

    # ── HTML (self-contained browser page) ──
    if args.format in ("html", "all"):
        try:
            path, warns = render_wiring_html(wiring, args.output)
            all_warnings.extend(warns)
            if path:
                print("[OK] {}".format(path))
                generated["html"] = True
                ok_count += 1
        except Exception as e:
            all_warnings.append("wiring HTML crashed: {}".format(e))
            print("[WARN] wiring HTML crashed: {}".format(e), file=sys.stderr)

    # ── Pin table (always generated) ──
    try:
        path, warns = render_pin_table(wiring, args.output)
        all_warnings.extend(warns)
        if path:
            print("[OK] {}".format(path))
            generated["pins"] = True
            ok_count += 1
    except Exception as e:
        all_warnings.append("pin table crashed: {}".format(e))
        print("[WARN] pin table crashed: {}".format(e), file=sys.stderr)

    # ── Report ──
    if all_warnings:
        print("\n{} warning(s):".format(len(all_warnings)), file=sys.stderr)
        for w in all_warnings:
            print("  - {}".format(w), file=sys.stderr)

    required_outputs = {"pins"}
    if args.format == "all":
        required_outputs.update({"md", "svg", "png", "html"})
    else:
        required_outputs.add(args.format)
    missing_outputs = sorted(item for item in required_outputs if not generated.get(item))
    if missing_outputs:
        print("\n[FAIL] Missing requested output(s): {}".format(", ".join(missing_outputs)), file=sys.stderr)
        sys.exit(1)

    if ok_count > 0:
        print("\nDone. {} file(s) generated.".format(ok_count))
        sys.exit(0)
    else:
        print("\n[FAIL] No output generated.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
