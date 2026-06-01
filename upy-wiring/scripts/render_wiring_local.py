#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render wiring.json to SVG image + Markdown pin table.
Reads the intermediate JSON from docs/wiring.json, outputs:
  - wiring.svg  (vector diagram via matplotlib)
  - wiring.md   (pin cross-reference table)

Usage:
  python render_wiring_local.py --input docs/wiring.json --output docs/ --format svg
  python render_wiring_local.py --input docs/wiring.json --output docs/ --format png
  python render_wiring_local.py --input docs/wiring.json --output docs/ --format all

Defensive: every field access uses .get() with fallbacks.
Missing or malformed sections are skipped with a stderr warning, never crash.
"""

import argparse
import json
import os
import sys
import textwrap

# ── Protocol colour map ──
BUS_COLORS = {
    "i2c":     "#2196F3",  # blue
    "spi":     "#4CAF50",  # green
    "uart":    "#FF9800",  # orange
    "onewire": "#9C27B0",  # purple
    "can":     "#795548",  # brown
}

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

ALERT_ICONS = {"info": "[i]", "warning": "[!]", "danger": "[!!]"}


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
#  matplotlib renderer
# ═══════════════════════════════════════════════════════════

def render_matplotlib(wiring, output_dir, fmt="svg"):
    """Render wiring.json to SVG/PNG using matplotlib.

    Returns (filepath, warnings).
    """
    warnings = []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
        # CJK font support: try system Chinese fonts first, fall back gracefully
        _cjk_fonts = ['SimHei', 'Microsoft YaHei', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei']
        _available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
        for _f in _cjk_fonts:
            if _f in _available:
                plt.rcParams['font.sans-serif'] = [_f, 'DejaVu Sans']
                plt.rcParams['axes.unicode_minus'] = False
                break
    except ImportError:
        return None, ["matplotlib not installed. Run: pip install matplotlib"]

    try:
        fig, ax = plt.subplots(1, 1, figsize=(16, 12), dpi=100)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_xlim(0, 1600)
        ax.set_ylim(0, 1200)
    except Exception as e:
        return None, ["failed to init matplotlib: {}".format(e)]

    # ── Meta ──
    meta = safe_get(wiring, "meta", {})
    project = safe_get(meta, "project", "Unknown Project")
    try:
        fig.suptitle("Wiring Diagram — {}".format(project), fontsize=14, fontweight="bold")
    except Exception:
        pass

    # ── MCU ──
    mcu = safe_get(wiring, "mcu", {})
    mcu_name = safe_get(mcu, "name", "MCU")
    orientation = safe_get(mcu, "orientation", "vertical")

    # Default canvas / MCU position
    canvas = safe_get(wiring, "canvas", {})
    mcu_pos = safe_get(canvas, "mcu_position", {})
    mcu_x = safe_int(mcu_pos, "x", 550)
    mcu_y = safe_int(mcu_pos, "y", 250)
    mcu_w = safe_int(mcu_pos, "w", 300)
    mcu_h = safe_int(mcu_pos, "h", 500)

    # Draw MCU body
    try:
        mcu_rect = FancyBboxPatch(
            (mcu_x, mcu_y), mcu_w, mcu_h,
            boxstyle="round,pad=4", facecolor="#ECEFF1",
            edgecolor="#37474F", linewidth=2, zorder=2
        )
        ax.add_patch(mcu_rect)
        ax.text(mcu_x + mcu_w / 2, mcu_y + mcu_h / 2,
                mcu_name, ha="center", va="center",
                fontsize=11, fontweight="bold", zorder=3)
    except Exception as e:
        warnings.append("MCU body render failed: {}".format(e))

    # ── MCU Pins ──
    pins = safe_list(mcu, "pins")
    pin_spacing_left = 0
    pin_spacing_right = 0
    left_pin_y = 0
    right_pin_y = 0

    # Count left/right pins for spacing
    left_count = sum(1 for p in pins if isinstance(p, dict) and safe_get(p, "side") == "left")
    right_count = sum(1 for p in pins if isinstance(p, dict) and safe_get(p, "side") == "right")
    top_count = sum(1 for p in pins if isinstance(p, dict) and safe_get(p, "side") == "top")
    bottom_count = sum(1 for p in pins if isinstance(p, dict) and safe_get(p, "side") == "bottom")

    left_pin_positions = {}
    right_pin_positions = {}

    # Sort and assign positions
    left_pins = sorted(
        [p for p in pins if isinstance(p, dict) and safe_get(p, "side") == "left"],
        key=lambda p: safe_int(p, "pos", 0)
    )
    right_pins = sorted(
        [p for p in pins if isinstance(p, dict) and safe_get(p, "side") == "right"],
        key=lambda p: safe_int(p, "pos", 0)
    )
    top_pins = sorted(
        [p for p in pins if isinstance(p, dict) and safe_get(p, "side") in ("top",)],
        key=lambda p: safe_int(p, "pos", 0)
    )
    bottom_pins = sorted(
        [p for p in pins if isinstance(p, dict) and safe_get(p, "side") in ("bottom",)],
        key=lambda p: safe_int(p, "pos", 0)
    )

    pin_w = 40
    pin_h = 14

    def draw_pin(pin_info, px, py, side):
        """Draw a single pin label. Never raises."""
        try:
            gpio = safe_get(pin_info, "gpio", "??")
            label = safe_get(pin_info, "label", "")
            ptype = safe_get(pin_info, "type", "special")
            color = PIN_TYPE_COLORS.get(ptype, "#9E9E9E")
            display = label if label else gpio

            rect = FancyBboxPatch(
                (px, py), pin_w, pin_h,
                boxstyle="round,pad=1", facecolor=color,
                edgecolor="#37474F", linewidth=0.8, zorder=4, alpha=0.85
            )
            ax.add_patch(rect)
            ax.text(px + pin_w / 2, py + pin_h / 2,
                    display, ha="center", va="center",
                    fontsize=6, fontweight="bold", color="white", zorder=5)
            return px, py
        except Exception as e:
            warnings.append("pin render failed gpio={}: {}".format(
                safe_get(pin_info, "gpio", "?"), e))
            return px, py

    # Draw left pins
    if left_count > 0:
        gap = min(28, mcu_h / max(left_count, 1))
        start_y = mcu_y + gap
        for i, pin_info in enumerate(left_pins):
            py = start_y + i * gap
            if py > mcu_y + mcu_h - pin_h:
                break
            left_pin_positions[safe_get(pin_info, "gpio", "")] = (mcu_x - pin_w - 4, py)
            draw_pin(pin_info, mcu_x - pin_w - 4, py, "left")

    # Draw right pins
    if right_count > 0:
        gap = min(28, mcu_h / max(right_count, 1))
        start_y = mcu_y + gap
        for i, pin_info in enumerate(right_pins):
            py = start_y + i * gap
            if py > mcu_y + mcu_h - pin_h:
                break
            right_pin_positions[safe_get(pin_info, "gpio", "")] = (mcu_x + mcu_w + 4, py)
            draw_pin(pin_info, mcu_x + mcu_w + 4, py, "right")

    # Draw top pins
    if top_count > 0:
        gap = min(40, mcu_w / max(top_count, 1))
        start_x = mcu_x + gap
        for i, pin_info in enumerate(top_pins):
            px = start_x + i * gap
            if px > mcu_x + mcu_w - pin_w:
                break
            draw_pin(pin_info, px, mcu_y + mcu_h + 4, "top")

    # Draw bottom pins
    if bottom_count > 0:
        gap = min(40, mcu_w / max(bottom_count, 1))
        start_x = mcu_x + gap
        for i, pin_info in enumerate(bottom_pins):
            px = start_x + i * gap
            if px > mcu_x + mcu_w - pin_w:
                break
            draw_pin(pin_info, px, mcu_y - pin_h - 4, "bottom")

    # ── Buses ──
    buses = safe_list(wiring, "buses")
    bus_start_x = 200
    bus_y = 80
    bus_spacing = 280

    for bi, bus in enumerate(buses):
        if not isinstance(bus, dict):
            continue
        try:
            btype = safe_get(bus, "type", "i2c")
            bid = safe_get(bus, "id", "?")
            color = BUS_COLORS.get(btype, "#607D8B")
            signals = safe_list(bus, "signals")
            devices = safe_list(bus, "devices")

            # Determine bus anchor point from signals
            anchor_x = mcu_x + mcu_w / 2
            anchor_y = mcu_y + mcu_h / 2
            signal_labels = []
            for sig in signals:
                if not isinstance(sig, dict):
                    continue
                s_gpio = safe_get(sig, "gpio", "")
                s_role = safe_get(sig, "role", "")
                signal_labels.append("{}({})".format(s_role, s_gpio))
                # Find pin position near MCU
                if s_gpio in left_pin_positions:
                    px, py = left_pin_positions[s_gpio]
                    anchor_x = px + pin_w + 4
                    anchor_y = py + pin_h / 2
                elif s_gpio in right_pin_positions:
                    px, py = right_pin_positions[s_gpio]
                    anchor_x = px
                    anchor_y = py + pin_h / 2

            bus_label = "{} {} ({})".format(btype.upper(), bid, ", ".join(signal_labels))

            # Draw bus trunk line
            bx = bus_start_x + bi * bus_spacing
            trunk_top = bus_y
            trunk_bottom = bus_y + 40 + len(devices) * 50

            try:
                ax.plot([bx, bx], [trunk_top, trunk_bottom],
                        color=color, linewidth=2.5, zorder=2, alpha=0.8)
            except Exception:
                pass

            # Bus label
            try:
                ax.text(bx, trunk_top - 18, bus_label,
                        ha="center", va="bottom", fontsize=7,
                        fontweight="bold", color=color, zorder=3)
            except Exception:
                pass

            # Draw devices on bus
            dev_w = 130
            dev_h = 36
            for di, dev in enumerate(devices):
                if not isinstance(dev, dict):
                    continue
                try:
                    d_name = safe_get(dev, "name", "Device")
                    d_addr = safe_get(dev, "addr", "")
                    d_type = safe_get(dev, "type", "")
                    label = d_name
                    if d_addr:
                        label = "{} ({})".format(d_name, d_addr)

                    dy = bus_y + 40 + di * 50 + (50 - dev_h) / 2

                    # Device box
                    dev_rect = FancyBboxPatch(
                        (bx - dev_w / 2, dy), dev_w, dev_h,
                        boxstyle="round,pad=2", facecolor="white",
                        edgecolor=color, linewidth=1.5, zorder=4
                    )
                    ax.add_patch(dev_rect)
                    ax.text(bx, dy + dev_h / 2, label,
                            ha="center", va="center", fontsize=7, zorder=5)

                    # Branch line from trunk to device
                    ax.plot([bx, bx - dev_w / 2], [dy + dev_h / 2, dy + dev_h / 2],
                            color=color, linewidth=1.2, alpha=0.6, zorder=2)
                except Exception as e:
                    warnings.append("bus device render failed '{}': {}".format(
                        safe_get(dev, "name", "?"), e))

            # Draw connection from MCU to bus trunk
            try:
                ax.plot([anchor_x, bx], [anchor_y, trunk_top],
                        color=color, linewidth=2, linestyle="--", alpha=0.5, zorder=1)
            except Exception:
                pass

        except Exception as e:
            warnings.append("bus render failed idx={}: {}".format(bi, e))

    # ── Standalone devices ──
    standalones = safe_list(wiring, "standalone")
    sa_start_x = 1150
    sa_start_y = 250
    sa_spacing = 60

    for si, sa in enumerate(standalones):
        if not isinstance(sa, dict):
            continue
        try:
            sa_pin = safe_get(sa, "pin", "??")
            sa_name = safe_get(sa, "name", "Device")
            sa_type = safe_get(sa, "type", "gpio_out")
            sa_ext = safe_get(sa, "external_components", "")
            color = PIN_TYPE_COLORS.get(sa_type, "#607D8B")

            sx = sa_start_x
            sy = sa_start_y + si * sa_spacing
            sw = 140
            sh = 40

            # Find pin position
            pin_x = sx
            pin_y = sy
            if sa_pin in left_pin_positions:
                pin_x, pin_y = left_pin_positions[sa_pin]
                pin_x += pin_w + 4
                pin_y += pin_h / 2
            elif sa_pin in right_pin_positions:
                pin_x, pin_y = right_pin_positions[sa_pin]
                pin_y += pin_h / 2

            # Device box
            rect = FancyBboxPatch(
                (sx, sy), sw, sh,
                boxstyle="round,pad=2", facecolor="white",
                edgecolor=color, linewidth=1.5, zorder=4
            )
            ax.add_patch(rect)
            display = sa_name
            if sa_ext:
                display = "{}\n({})".format(sa_name, sa_ext)
            ax.text(sx + sw / 2, sy + sh / 2, display,
                    ha="center", va="center", fontsize=7, zorder=5)

            # Connection line to MCU pin
            try:
                ax.plot([pin_x, sx], [pin_y, sy + sh / 2],
                        color=color, linewidth=1.5, alpha=0.7, zorder=2)
            except Exception:
                pass

        except Exception as e:
            warnings.append("standalone render failed '{}': {}".format(
                safe_get(sa, "name", "?"), e))

    # ── Power rails ──
    power_list = safe_list(wiring, "power")
    power_y_start = 20
    for pi, pwr in enumerate(power_list):
        if not isinstance(pwr, dict):
            continue
        try:
            rail = safe_get(pwr, "rail", "?")
            consumers = safe_list(pwr, "consumers")
            pcolor = "#FF9800" if rail == "3.3V" else ("#F44336" if rail == "5V" else "#212121")

            py = power_y_start + pi * 28
            ax.text(10, py, "{}: {}".format(rail, ", ".join(consumers)),
                    fontsize=7, color=pcolor, fontweight="bold", zorder=3)
        except Exception as e:
            warnings.append("power render failed: {}".format(e))

    # ── Alerts ──
    alerts = safe_list(wiring, "alerts")
    alert_start_y = 1180
    alert_count = 0
    for ai, alert in enumerate(alerts):
        if not isinstance(alert, dict):
            continue
        try:
            level = safe_get(alert, "level", "info")
            msg = safe_get(alert, "msg", "")
            icon = ALERT_ICONS.get(level, "[?]")
            text = "{} {}".format(icon, msg)
            color_map = {"info": "#2196F3", "warning": "#FF9800", "danger": "#F44336"}
            acolor = color_map.get(level, "#9E9E9E")

            wrapped = textwrap.fill(text, width=90)
            ay = alert_start_y - alert_count * 22
            # Count lines
            n_lines = wrapped.count("\n") + 1
            for line in wrapped.split("\n"):
                ax.text(10, ay, line, fontsize=7, color=acolor, zorder=3)
                ay -= 14
            alert_count += 1
        except Exception as e:
            warnings.append("alert render failed: {}".format(e))

    # ── Legend ──
    try:
        legend_items = [
            ("I2C", BUS_COLORS["i2c"]),
            ("SPI", BUS_COLORS["spi"]),
            ("UART", BUS_COLORS["uart"]),
            ("GPIO", PIN_TYPE_COLORS["gpio_out"]),
            ("Power", PIN_TYPE_COLORS["power_3v3"]),
            ("GND", PIN_TYPE_COLORS["gnd"]),
        ]
        legend_x = 10
        legend_y = 1150
        for li, (lbl, lclr) in enumerate(legend_items):
            lx = legend_x + li * 90
            rect = FancyBboxPatch(
                (lx, legend_y), 18, 12,
                boxstyle="round,pad=1", facecolor=lclr,
                edgecolor="#37474F", linewidth=0.5, zorder=4
            )
            ax.add_patch(rect)
            ax.text(lx + 22, legend_y + 6, lbl, fontsize=7, va="center", zorder=5)
    except Exception as e:
        warnings.append("legend render failed: {}".format(e))

    # ── Save ──
    ext = "svg" if fmt in ("svg", "all") else "png"
    out_path = os.path.join(output_dir, "wiring.{}".format(ext))
    try:
        os.makedirs(output_dir, exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight", format=ext,
                     facecolor="white", edgecolor="none")
        plt.close(fig)
    except Exception as e:
        plt.close(fig)
        return None, ["save failed: {}".format(e)]

    return out_path, warnings


# ═══════════════════════════════════════════════════════════
#  Markdown pin table
# ═══════════════════════════════════════════════════════════

def render_markdown_table(wiring, output_dir):
    """Generate wiring.md pin cross-reference table. Returns (filepath, warnings)."""
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
            # Collect physical pin numbers from bus signals
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
                # Use pin_map lookup; fall back to signal-level aggregation
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

        out_path = os.path.join(output_dir, "wiring.md")
        os.makedirs(output_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return out_path, warnings
    except Exception as e:
        return None, ["markdown render failed: {}".format(e)]


# ═══════════════════════════════════════════════════════════
#  main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Render wiring.json to image + markdown")
    parser.add_argument("--input", required=True, help="Path to wiring.json")
    parser.add_argument("--output", required=True, help="Output directory (e.g. docs/)")
    parser.add_argument("--format", default="svg",
                        choices=["svg", "png", "all"],
                        help="Output format: svg, png, or all (svg + md)")
    args = parser.parse_args()

    # Load
    wiring, err = load_wiring_json(args.input)
    if err:
        print("[FAIL] {}".format(err), file=sys.stderr)
        sys.exit(1)

    all_warnings = []

    # Render image
    img_path, img_warnings = render_matplotlib(wiring, args.output, args.format)
    all_warnings.extend(img_warnings)
    if img_path:
        print("[OK] Image: {}".format(img_path))
    else:
        print("[WARN] Image render failed", file=sys.stderr)

    # Render markdown
    md_path, md_warnings = render_markdown_table(wiring, args.output)
    all_warnings.extend(md_warnings)
    if md_path:
        print("[OK] Markdown: {}".format(md_path))

    # Report warnings
    if all_warnings:
        print("\n{} warning(s):".format(len(all_warnings)), file=sys.stderr)
        for w in all_warnings:
            print("  - {}".format(w), file=sys.stderr)

    if img_path or md_path:
        print("\nDone.")
        sys.exit(0)
    else:
        print("\n[FAIL] No output generated.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
