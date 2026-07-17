#!/usr/bin/env python3
"""Generate a simple 64x64 PNG icon for an MPOS App using only stdlib."""

from __future__ import annotations

import argparse
import hashlib
import math
import struct
import zlib
from pathlib import Path


PALETTES = [
    ((23, 35, 51), (38, 166, 154), (255, 213, 79)),
    ((31, 41, 55), (96, 165, 250), (248, 250, 252)),
    ((24, 24, 27), (244, 114, 182), (250, 204, 21)),
    ((17, 24, 39), (52, 211, 153), (209, 250, 229)),
    ((39, 39, 42), (251, 146, 60), (255, 247, 237)),
    ((30, 41, 59), (129, 140, 248), (226, 232, 240)),
]

FONT_5X7 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
}


class Canvas:
    def __init__(self, size: int, bg: tuple[int, int, int]):
        self.size = size
        self.pixels = [[(*bg, 255) for _ in range(size)] for _ in range(size)]

    def set(self, x: int, y: int, color: tuple[int, int, int], alpha: int = 255) -> None:
        if 0 <= x < self.size and 0 <= y < self.size:
            if alpha >= 255:
                self.pixels[y][x] = (*color, 255)
            else:
                old = self.pixels[y][x]
                inv = 255 - alpha
                self.pixels[y][x] = (
                    (color[0] * alpha + old[0] * inv) // 255,
                    (color[1] * alpha + old[1] * inv) // 255,
                    (color[2] * alpha + old[2] * inv) // 255,
                    255,
                )

    def rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int], alpha: int = 255) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, color, alpha)

    def circle(self, cx: int, cy: int, r: int, color: tuple[int, int, int], alpha: int = 255) -> None:
        rr = r * r
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= rr:
                    self.set(x, y, color, alpha)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], width: int = 1) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.circle(x0, y0, max(0, width - 1), color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def char(self, ch: str, x: int, y: int, color: tuple[int, int, int], scale: int = 4) -> None:
        pattern = FONT_5X7.get(ch.upper())
        if not pattern:
            return
        for row, bits in enumerate(pattern):
            for col, bit in enumerate(bits):
                if bit == "1":
                    self.rect(x + col * scale, y + row * scale, scale, scale, color)

    def png_bytes(self) -> bytes:
        raw = bytearray()
        for row in self.pixels:
            raw.append(0)
            for rgba in row:
                raw.extend(bytes(rgba))
        compressed = zlib.compress(bytes(raw), 9)
        def chunk(kind: bytes, data: bytes) -> bytes:
            import binascii
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        header = struct.pack(">IIBBBBB", self.size, self.size, 8, 6, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def choose_kind(text: str) -> str:
    table = [
        ("weather", {"weather", "sun", "cloud", "rain", "forecast"}),
        ("music", {"music", "audio", "sound", "song", "player", "mic"}),
        ("camera", {"camera", "photo", "image", "qr", "scan"}),
        ("chat", {"chat", "message", "mqtt", "websocket", "network", "wifi"}),
        ("clock", {"clock", "timer", "time", "alarm", "calendar"}),
        ("battery", {"battery", "power", "voltage", "charge"}),
        ("sensor", {"sensor", "imu", "gyro", "compass", "temperature", "distance"}),
        ("game", {"game", "puzzle", "play", "score"}),
        ("light", {"light", "led", "lamp", "color"}),
    ]
    words = set(text.lower().replace("_", " ").replace("-", " ").split())
    for kind, keys in table:
        if words & keys:
            return kind
    return "letter"


def draw_symbol(canvas: Canvas, kind: str, label: str, primary: tuple[int, int, int], accent: tuple[int, int, int]) -> None:
    if kind == "weather":
        canvas.circle(24, 24, 10, accent)
        canvas.circle(38, 39, 11, primary)
        canvas.circle(28, 41, 8, primary)
        canvas.rect(25, 39, 25, 10, primary)
    elif kind == "music":
        canvas.line(38, 15, 38, 43, primary, 2)
        canvas.line(38, 15, 48, 20, primary, 2)
        canvas.circle(28, 43, 7, accent)
        canvas.circle(44, 48, 7, primary)
    elif kind == "camera":
        canvas.rect(15, 22, 34, 24, primary)
        canvas.rect(22, 17, 13, 7, primary)
        canvas.circle(32, 34, 10, accent)
        canvas.circle(32, 34, 5, (20, 20, 20))
    elif kind == "chat":
        canvas.circle(25, 27, 13, primary)
        canvas.circle(39, 38, 13, accent)
        canvas.rect(19, 38, 7, 8, primary)
        canvas.rect(39, 48, 7, 7, accent)
    elif kind == "clock":
        canvas.circle(32, 32, 20, primary)
        canvas.circle(32, 32, 16, (20, 20, 20), 180)
        canvas.line(32, 32, 32, 20, accent, 2)
        canvas.line(32, 32, 43, 37, accent, 2)
    elif kind == "battery":
        canvas.rect(15, 25, 33, 17, primary)
        canvas.rect(48, 30, 4, 7, primary)
        canvas.rect(19, 29, 21, 9, accent)
    elif kind == "sensor":
        canvas.circle(32, 32, 7, accent)
        for angle in range(0, 360, 60):
            x = 32 + int(math.cos(math.radians(angle)) * 20)
            y = 32 + int(math.sin(math.radians(angle)) * 20)
            canvas.line(32, 32, x, y, primary, 1)
            canvas.circle(x, y, 4, primary)
    elif kind == "game":
        canvas.rect(18, 18, 12, 12, primary)
        canvas.rect(34, 18, 12, 12, accent)
        canvas.rect(18, 34, 12, 12, accent)
        canvas.rect(34, 34, 12, 12, primary)
    elif kind == "light":
        canvas.circle(32, 27, 13, accent)
        canvas.rect(25, 39, 14, 8, primary)
        canvas.line(20, 16, 15, 10, primary, 1)
        canvas.line(44, 16, 49, 10, primary, 1)
    else:
        ch = next((c for c in label.upper() if "A" <= c <= "Z"), "M")
        canvas.char(ch, 22, 18, primary, scale=4)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a 64x64 MPOS PNG icon")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--label", default="MPOS")
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", type=int, default=64)
    args = parser.parse_args()
    if args.size != 64:
        raise SystemExit("Only 64x64 icons are supported")

    seed_text = f"{args.prompt} {args.label}".strip() or "MicroPythonOS App"
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    bg, primary, accent = PALETTES[digest[0] % len(PALETTES)]
    canvas = Canvas(64, bg)
    for y in range(64):
        shade = int((y / 63) * 26)
        for x in range(64):
            canvas.set(x, y, (min(255, bg[0] + shade), min(255, bg[1] + shade), min(255, bg[2] + shade)))
    canvas.circle(12, 12, 18, primary, 32)
    canvas.circle(55, 52, 22, accent, 38)
    draw_symbol(canvas, choose_kind(seed_text), args.label, primary, accent)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canvas.png_bytes())
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
