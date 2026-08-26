#!/usr/bin/env python3
"""Render a constrained visual specification and emit an LVGL v9 image."""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path


ASSET_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_OUTPUT_PIXELS = 262_144
MAX_RENDER_PIXELS = 4_194_304
MAX_SHAPES = 512
MAX_SHAPE_BOUND = 4096
MAX_DRAW_WORK_UNITS = 8_000_000
MAX_SPEC_BYTES = 1_048_576
MAX_RUNTIME_BYTES = 1_048_576
SUPPORTED_SHAPES = {"rect", "circle", "line", "polygon", "gradient"}
COLOR_FORMATS = {
    "A8": 0x0E,
    "RGB565": 0x12,
    "RGB565A8": 0x14,
}


class AssetSpecError(ValueError):
    pass


def _integer(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssetSpecError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise AssetSpecError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise AssetSpecError(f"{name} must be at most {maximum}")
    return value


def _color(value, name="color"):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value):
        raise AssetSpecError(f"{name} must be #RRGGBB or #RRGGBBAA")
    raw = value[1:]
    alpha = int(raw[6:8], 16) if len(raw) == 8 else 255
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), alpha


def _reject_extra_fields(item, allowed, context):
    extra = sorted(set(item) - set(allowed))
    if extra:
        raise AssetSpecError(f"unsupported fields for {context}: {', '.join(extra)}")


def _shape_integer(value, name, minimum=-MAX_SHAPE_BOUND, maximum=MAX_SHAPE_BOUND):
    try:
        return _integer(value, name, minimum, maximum)
    except AssetSpecError as exc:
        raise AssetSpecError(f"{name} exceeds shape bound: {exc}") from exc


class Canvas:
    def __init__(self, width, height, background, scale):
        self.output_width = width
        self.output_height = height
        self.scale = scale
        self.width = width * scale
        self.height = height * scale
        if self.width * self.height > MAX_RENDER_PIXELS:
            raise AssetSpecError("supersampled image exceeds render pixel budget")
        self.pixels = bytearray(background * (self.width * self.height))
        self.work_units = 0

    def consume_work(self, amount):
        self.work_units += max(0, amount)
        if self.work_units > MAX_DRAW_WORK_UNITS:
            raise AssetSpecError("visual asset exceeds draw work budget")

    def blend(self, x, y, source):
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        offset = (y * self.width + x) * 4
        sr, sg, sb, sa = source
        if sa == 255:
            self.pixels[offset:offset + 4] = bytes(source)
            return
        if sa == 0:
            return
        dr, dg, db, da = self.pixels[offset:offset + 4]
        out_a_num = sa * 255 + da * (255 - sa)
        if out_a_num == 0:
            self.pixels[offset:offset + 4] = b"\x00\x00\x00\x00"
            return
        out_a = (out_a_num + 127) // 255
        denominator = out_a_num
        red = (sr * sa * 255 + dr * da * (255 - sa) + denominator // 2) // denominator
        green = (sg * sa * 255 + dg * da * (255 - sa) + denominator // 2) // denominator
        blue = (sb * sa * 255 + db * da * (255 - sa) + denominator // 2) // denominator
        self.pixels[offset:offset + 4] = bytes((red, green, blue, out_a))

    def draw_rect(self, shape):
        _reject_extra_fields(
            shape,
            {"type", "x", "y", "width", "height", "color", "radius"},
            "rect",
        )
        x = _shape_integer(shape.get("x"), "rect.x") * self.scale
        y = _shape_integer(shape.get("y"), "rect.y") * self.scale
        width = _shape_integer(shape.get("width"), "rect.width", 1) * self.scale
        height = _shape_integer(shape.get("height"), "rect.height", 1) * self.scale
        radius = _shape_integer(shape.get("radius", 0), "rect.radius", 0) * self.scale
        color = _color(shape.get("color"), "rect.color")
        radius = min(radius, width // 2, height // 2)
        start_x = max(0, x)
        end_x = min(self.width, x + width)
        start_y = max(0, y)
        end_y = min(self.height, y + height)
        self.consume_work(max(0, end_x - start_x) * max(0, end_y - start_y))
        for yy in range(start_y, end_y):
            for xx in range(start_x, end_x):
                if radius:
                    cx = x + radius if xx < x + radius else x + width - radius - 1 if xx >= x + width - radius else xx
                    cy = y + radius if yy < y + radius else y + height - radius - 1 if yy >= y + height - radius else yy
                    if (xx - cx) ** 2 + (yy - cy) ** 2 > radius ** 2:
                        continue
                self.blend(xx, yy, color)

    def draw_circle(self, shape):
        _reject_extra_fields(shape, {"type", "cx", "cy", "radius", "color"}, "circle")
        cx = _shape_integer(shape.get("cx"), "circle.cx") * self.scale
        cy = _shape_integer(shape.get("cy"), "circle.cy") * self.scale
        radius = _shape_integer(shape.get("radius"), "circle.radius", 1) * self.scale
        color = _color(shape.get("color"), "circle.color")
        radius_squared = radius * radius
        start_x = max(0, cx - radius)
        end_x = min(self.width - 1, cx + radius)
        start_y = max(0, cy - radius)
        end_y = min(self.height - 1, cy + radius)
        self.consume_work(max(0, end_x - start_x + 1) * max(0, end_y - start_y + 1))
        for yy in range(start_y, end_y + 1):
            for xx in range(start_x, end_x + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= radius_squared:
                    self.blend(xx, yy, color)

    def draw_line(self, shape):
        _reject_extra_fields(shape, {"type", "x1", "y1", "x2", "y2", "width", "color"}, "line")
        x1 = _shape_integer(shape.get("x1"), "line.x1") * self.scale
        y1 = _shape_integer(shape.get("y1"), "line.y1") * self.scale
        x2 = _shape_integer(shape.get("x2"), "line.x2") * self.scale
        y2 = _shape_integer(shape.get("y2"), "line.y2") * self.scale
        line_width = _shape_integer(shape.get("width", 1), "line.width", 1) * self.scale
        color = _color(shape.get("color"), "line.color")
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        radius = max(0, line_width // 2)
        diameter = radius * 2 + 1
        self.consume_work((steps + 1) * diameter * diameter)
        for index in range(steps + 1):
            x = round(x1 + (x2 - x1) * index / steps)
            y = round(y1 + (y2 - y1) * index / steps)
            for yy in range(y - radius, y + radius + 1):
                for xx in range(x - radius, x + radius + 1):
                    if radius == 0 or (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2:
                        self.blend(xx, yy, color)

    def draw_polygon(self, shape):
        _reject_extra_fields(shape, {"type", "points", "color"}, "polygon")
        raw_points = shape.get("points")
        if not isinstance(raw_points, list) or len(raw_points) < 3 or len(raw_points) > 256:
            raise AssetSpecError("polygon.points must contain 3 to 256 points")
        points = []
        for index, point in enumerate(raw_points):
            if not isinstance(point, list) or len(point) != 2:
                raise AssetSpecError(f"polygon.points[{index}] must be [x, y]")
            points.append(
                (
                    _shape_integer(point[0], f"polygon.points[{index}].x") * self.scale,
                    _shape_integer(point[1], f"polygon.points[{index}].y") * self.scale,
                )
            )
        color = _color(shape.get("color"), "polygon.color")
        minimum_y = max(0, min(point[1] for point in points))
        maximum_y = min(self.height - 1, max(point[1] for point in points))
        scanlines = max(0, maximum_y - minimum_y + 1)
        self.consume_work(scanlines * len(points) + self.width * scanlines)
        for yy in range(minimum_y, maximum_y + 1):
            scan_y = yy + 0.5
            intersections = []
            for index, (x1, y1) in enumerate(points):
                x2, y2 = points[(index + 1) % len(points)]
                if y1 == y2 or scan_y < min(y1, y2) or scan_y >= max(y1, y2):
                    continue
                intersections.append(x1 + (scan_y - y1) * (x2 - x1) / (y2 - y1))
            intersections.sort()
            for index in range(0, len(intersections) - 1, 2):
                start = max(0, math.ceil(intersections[index]))
                end = min(self.width - 1, math.floor(intersections[index + 1]))
                for xx in range(start, end + 1):
                    self.blend(xx, yy, color)

    def draw_gradient(self, shape):
        _reject_extra_fields(
            shape,
            {"type", "x", "y", "width", "height", "start_color", "end_color", "direction"},
            "gradient",
        )
        x = _shape_integer(shape.get("x"), "gradient.x") * self.scale
        y = _shape_integer(shape.get("y"), "gradient.y") * self.scale
        width = _shape_integer(shape.get("width"), "gradient.width", 1) * self.scale
        height = _shape_integer(shape.get("height"), "gradient.height", 1) * self.scale
        start = _color(shape.get("start_color"), "gradient.start_color")
        end = _color(shape.get("end_color"), "gradient.end_color")
        direction = shape.get("direction", "vertical")
        if direction not in {"horizontal", "vertical"}:
            raise AssetSpecError("gradient.direction must be horizontal or vertical")
        span = max(1, width - 1 if direction == "horizontal" else height - 1)
        start_x = max(0, x)
        end_x = min(self.width, x + width)
        start_y = max(0, y)
        end_y = min(self.height, y + height)
        self.consume_work(max(0, end_x - start_x) * max(0, end_y - start_y))
        for yy in range(start_y, end_y):
            for xx in range(start_x, end_x):
                position = xx - x if direction == "horizontal" else yy - y
                color = tuple(
                    (start[channel] * (span - position) + end[channel] * position + span // 2) // span
                    for channel in range(4)
                )
                self.blend(xx, yy, color)

    def draw(self, shape):
        if not isinstance(shape, dict):
            raise AssetSpecError("every shape must be an object")
        shape_type = shape.get("type")
        if shape_type not in SUPPORTED_SHAPES:
            raise AssetSpecError(f"unsupported shape type: {shape_type}")
        getattr(self, f"draw_{shape_type}")(shape)

    def output_pixels(self):
        if self.scale == 1:
            return bytes(self.pixels)
        result = bytearray()
        samples = self.scale * self.scale
        for output_y in range(self.output_height):
            for output_x in range(self.output_width):
                alpha_sum = 0
                red_sum = 0
                green_sum = 0
                blue_sum = 0
                for sample_y in range(output_y * self.scale, (output_y + 1) * self.scale):
                    for sample_x in range(output_x * self.scale, (output_x + 1) * self.scale):
                        offset = (sample_y * self.width + sample_x) * 4
                        red, green, blue, alpha = self.pixels[offset:offset + 4]
                        alpha_sum += alpha
                        red_sum += red * alpha
                        green_sum += green * alpha
                        blue_sum += blue * alpha
                output_alpha = (alpha_sum + samples // 2) // samples
                if alpha_sum:
                    output_red = (red_sum + alpha_sum // 2) // alpha_sum
                    output_green = (green_sum + alpha_sum // 2) // alpha_sum
                    output_blue = (blue_sum + alpha_sum // 2) // alpha_sum
                else:
                    output_red = output_green = output_blue = 0
                result.extend((output_red, output_green, output_blue, output_alpha))
        return bytes(result)


def validate_spec(payload):
    if not isinstance(payload, dict):
        raise AssetSpecError("visual asset spec must be an object")
    _reject_extra_fields(
        payload,
        {"schema_version", "id", "width", "height", "background", "supersample", "shapes", "runtime_format"},
        "visual asset spec",
    )
    if payload.get("schema_version") != "mpos-visual-asset-spec-v1":
        raise AssetSpecError("unsupported visual asset schema_version")
    asset_id = payload.get("id")
    if not isinstance(asset_id, str) or not ASSET_ID_RE.fullmatch(asset_id):
        raise AssetSpecError("invalid asset id")
    width = _integer(payload.get("width"), "width", 1, 1024)
    height = _integer(payload.get("height"), "height", 1, 1024)
    if width * height > MAX_OUTPUT_PIXELS:
        raise AssetSpecError("visual asset exceeds output pixel budget")
    background = _color(payload.get("background", "#00000000"), "background")
    supersample = _integer(payload.get("supersample", 1), "supersample", 1, 4)
    if supersample not in {1, 2, 4}:
        raise AssetSpecError("supersample must be 1, 2, or 4")
    shapes = payload.get("shapes")
    if not isinstance(shapes, list) or len(shapes) > MAX_SHAPES:
        raise AssetSpecError(f"shapes must be a list with at most {MAX_SHAPES} entries")
    runtime_format = payload.get("runtime_format", "auto")
    if runtime_format not in {"auto", *COLOR_FORMATS}:
        raise AssetSpecError("runtime_format must be auto, A8, RGB565, or RGB565A8")
    return asset_id, width, height, background, supersample, shapes, runtime_format


def png_bytes(width, height, pixels):
    raw = bytearray()
    row_size = width * 4
    for row in range(height):
        raw.append(0)
        raw.extend(pixels[row * row_size:(row + 1) * row_size])

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def lvgl_bin_bytes(width, height, pixels, runtime_format):
    has_alpha = any(pixels[index] != 255 for index in range(3, len(pixels), 4))
    selected = "RGB565A8" if runtime_format == "auto" and has_alpha else "RGB565" if runtime_format == "auto" else runtime_format
    if selected == "RGB565" and has_alpha:
        raise AssetSpecError("RGB565 cannot preserve transparent pixels; use RGB565A8 or A8")
    if selected == "A8":
        stride = width
        data = bytes(pixels[index] for index in range(3, len(pixels), 4))
    else:
        stride = width * 2
        rgb = bytearray()
        alpha = bytearray()
        for index in range(0, len(pixels), 4):
            red, green, blue, opacity = pixels[index:index + 4]
            color = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
            rgb.extend(struct.pack("<H", color))
            if selected == "RGB565A8":
                alpha.append(opacity)
        data = bytes(rgb + alpha)
    header = struct.pack(
        "<BBHHHHH",
        0x19,
        COLOR_FORMATS[selected],
        0,
        width,
        height,
        stride,
        0,
    )
    return header + data, selected, has_alpha


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _confined_path(allowed_root, value, name, must_exist=False):
    path = Path(value).resolve(strict=must_exist)
    try:
        path.relative_to(allowed_root)
    except ValueError as exc:
        raise AssetSpecError(f"{name} must stay inside allowed root") from exc
    return path


def build(args):
    allowed_root = Path(args.allowed_root).resolve(strict=True)
    if not allowed_root.is_dir():
        raise AssetSpecError("allowed root must be a directory")
    spec_path = _confined_path(allowed_root, args.spec, "spec", must_exist=True)
    if spec_path.stat().st_size > MAX_SPEC_BYTES:
        raise AssetSpecError("visual asset spec exceeds byte budget")
    preview_path = _confined_path(allowed_root, args.preview_output, "preview output")
    runtime_path = _confined_path(allowed_root, args.runtime_output, "runtime output")
    metadata_path = _confined_path(allowed_root, args.metadata_output, "metadata output")
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    asset_id, width, height, background, supersample, shapes, spec_format = validate_spec(payload)
    canvas = Canvas(width, height, background, supersample)
    for shape in shapes:
        canvas.draw(shape)
    pixels = canvas.output_pixels()
    preview = png_bytes(width, height, pixels)
    requested_format = spec_format if args.runtime_format == "auto" and spec_format != "auto" else args.runtime_format
    runtime, selected_format, has_alpha = lvgl_bin_bytes(width, height, pixels, requested_format)
    if len(runtime) > args.max_runtime_bytes:
        raise AssetSpecError("runtime byte budget exceeded")
    _write(preview_path, preview)
    _write(runtime_path, runtime)
    canonical_spec = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    metadata = {
        "schema_version": "mpos-visual-asset-build-v1",
        "id": asset_id,
        "width": width,
        "height": height,
        "runtime_format": selected_format,
        "has_alpha": has_alpha,
        "spec_sha256": hashlib.sha256(canonical_spec).hexdigest(),
        "preview_sha256": hashlib.sha256(preview).hexdigest(),
        "runtime_sha256": hashlib.sha256(runtime).hexdigest(),
        "preview_bytes": len(preview),
        "runtime_bytes": len(runtime),
        "preview_path": str(preview_path),
        "runtime_path": str(runtime_path),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description="Build a constrained MPOS visual asset")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--preview-output", required=True)
    parser.add_argument("--runtime-output", required=True)
    parser.add_argument("--metadata-output", required=True)
    parser.add_argument("--allowed-root", required=True)
    parser.add_argument("--max-runtime-bytes", type=int, default=1_048_576)
    parser.add_argument("--format", dest="runtime_format", choices=["auto", *COLOR_FORMATS], default="auto")
    args = parser.parse_args()
    try:
        _integer(args.max_runtime_bytes, "max runtime bytes", 1, MAX_RUNTIME_BYTES)
        build(args)
    except (AssetSpecError, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
