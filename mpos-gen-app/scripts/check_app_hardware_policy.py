#!/usr/bin/env python3
"""Reject board-specific hardware access in generated MicroPythonOS Apps."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


FULLNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
MACHINE_TYPES = {"Pin", "I2C", "SPI", "UART", "I2S", "ADC"}
DIRECT_MODULES = {"adc_mic", "pdm_mic", "webcam"}


def app_files(app_dir: Path) -> list[Path]:
    roots = [app_dir / "assets"] if (app_dir / "assets").is_dir() else [app_dir]
    return sorted(
        path
        for root in roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        if base:
            return base + "." + node.attr
    return None


def violation(path: Path, node: ast.AST, symbol: str, message: str) -> dict[str, object]:
    return {
        "code": "DIRECT_HARDWARE_ACCESS_FORBIDDEN",
        "path": str(path),
        "line": getattr(node, "lineno", 0),
        "symbol": symbol,
        "message": message,
    }


def scan_file(path: Path) -> list[dict[str, object]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    errors: list[dict[str, object]] = []
    machine_aliases = {"machine"}
    neopixel_aliases = {"neopixel"}
    direct_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                alias = item.asname or item.name
                if item.name == "machine":
                    machine_aliases.add(alias)
                elif item.name == "neopixel":
                    neopixel_aliases.add(alias)
                elif item.name.startswith("mpos.board"):
                    errors.append(violation(path, node, item.name, "Board modules are not portable App APIs."))
                elif item.name in DIRECT_MODULES:
                    errors.append(violation(path, node, item.name, "Use the corresponding MPOS manager instead of a native hardware module."))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("mpos.board"):
                errors.append(violation(path, node, module, "Board modules are not portable App APIs."))
            elif module == "machine":
                for item in node.names:
                    if item.name in MACHINE_TYPES:
                        direct_names.add(item.asname or item.name)
                        errors.append(violation(path, node, "machine." + item.name, "Use an MPOS manager instead of direct board hardware."))
            elif module == "neopixel":
                for item in node.names:
                    if item.name == "NeoPixel":
                        direct_names.add(item.asname or item.name)
                        errors.append(violation(path, node, "neopixel.NeoPixel", "Use LightsManager instead of direct NeoPixel access."))
            elif module in DIRECT_MODULES:
                errors.append(violation(path, node, module, "Use the corresponding MPOS manager instead of a native hardware module."))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if not name:
            continue
        if name in direct_names:
            continue
        parts = name.split(".")
        if len(parts) == 2 and parts[0] in machine_aliases and parts[1] in MACHINE_TYPES:
            errors.append(violation(path, node, name, "Use an MPOS manager instead of direct board hardware."))
        elif len(parts) == 2 and parts[0] in neopixel_aliases and parts[1] == "NeoPixel":
            errors.append(violation(path, node, name, "Use LightsManager instead of direct NeoPixel access."))

    unique: dict[tuple[object, ...], dict[str, object]] = {}
    for item in errors:
        key = (item["path"], item["line"], item["symbol"])
        unique[key] = item
    return list(unique.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--app-fullname", required=True)
    parser.add_argument("--allow-direct-hardware", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    if not FULLNAME_RE.fullmatch(args.app_fullname):
        parser.error("invalid app fullname")
    repo = Path(args.repo).expanduser().resolve()
    app_dir = repo / "internal_filesystem" / "apps" / args.app_fullname
    if not app_dir.is_dir():
        parser.error("App directory not found: %s" % app_dir)

    errors: list[dict[str, object]] = []
    for path in app_files(app_dir):
        for item in scan_file(path):
            item["path"] = str(path.relative_to(repo))
            errors.append(item)

    result = {
        "schema_version": "mpos-hardware-policy-v1",
        "app_fullname": args.app_fullname,
        "allow_direct_hardware": args.allow_direct_hardware,
        "result": "success" if not errors or args.allow_direct_hardware else "failed",
        "errors": errors,
    }
    text = json.dumps(result, ensure_ascii=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["result"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
