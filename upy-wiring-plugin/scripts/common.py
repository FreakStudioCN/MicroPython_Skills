#!/usr/bin/env python3
"""Shared helpers for upy-wiring-plugin scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def configure_stdio() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def payload_of(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else {}


def manifest_of(data: dict[str, Any]) -> dict[str, Any]:
    payload = payload_of(data)
    manifest = payload.get("manifest_content")
    if isinstance(manifest, dict):
        return manifest
    if "schema_version" in data or "phase" in data:
        return data
    return {}
