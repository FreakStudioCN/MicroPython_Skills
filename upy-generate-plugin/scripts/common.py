#!/usr/bin/env python3
"""Shared helpers for upy-generate-plugin scripts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def load_json_path_or_stdin(value: str) -> Any:
    if value == "-":
        return json.loads(sys.stdin.read())
    with Path(value).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def unwrap_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("manifest input must be a JSON object")
    payload = data.get("payload")
    if isinstance(payload, dict):
        manifest_content = payload.get("manifest_content")
        if isinstance(manifest_content, dict):
            return manifest_content
        manifest = payload.get("manifest")
        if isinstance(manifest, dict):
            return manifest
    manifest_content = data.get("manifest_content")
    if isinstance(manifest_content, dict):
        return manifest_content
    manifest = data.get("manifest")
    if isinstance(manifest, dict):
        return manifest
    return data


def load_manifest_arg(path_or_stdin: str) -> dict[str, Any]:
    return unwrap_manifest(load_json_path_or_stdin(path_or_stdin))


def json_dump(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def safe_name(value: str, fallback: str = "device") -> str:
    name = value.strip().lower()
    mapping = {
        "有源蜂鸣器": "buzzer",
        "无源蜂鸣器": "buzzer",
        "蜂鸣器": "buzzer",
        "温湿度传感器": "temperature_humidity_sensor",
        "温湿度": "temperature_humidity",
        "气压传感器": "pressure_sensor",
        "显示屏": "display",
        "按键": "button",
        "按钮": "button",
        "继电器": "relay",
        "指示灯": "led",
    }
    for cn, en in mapping.items():
        if cn in value:
            return en
    ascii_name = name.encode("ascii", errors="ignore").decode("ascii")
    ascii_name = re.sub(r"[^a-z0-9_]+", "_", ascii_name)
    ascii_name = re.sub(r"_+", "_", ascii_name).strip("_")
    return ascii_name or fallback


def validate_relative_posix_path(path: str) -> None:
    if not path or path.startswith("/") or "\\" in path:
        raise ValueError(f"path must be relative POSIX style: {path}")
    if len(path) >= 2 and path[1] == ":":
        raise ValueError(f"path must not contain a drive prefix: {path}")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError(f"path must not contain empty, '.', or '..' parts: {path}")


def target_path(project_dir: Path, rel_path: str) -> Path:
    validate_relative_posix_path(rel_path)
    root = project_dir.resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes project directory: {rel_path}")
    return target


def add_manifest_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--manifest",
        default="-",
        help="Manifest JSON or phase_complete path. Use '-' to read JSON from stdin.",
    )
