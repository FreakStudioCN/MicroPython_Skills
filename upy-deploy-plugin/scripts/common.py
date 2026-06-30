#!/usr/bin/env python3
"""Shared helpers for upy-deploy-plugin scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: str | Path, payload: Any) -> None:
    if str(path) == "-":
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def get_payload(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload")
    if isinstance(payload, dict):
        return payload
    return {}


def get_manifest(message: dict[str, Any]) -> dict[str, Any]:
    payload = get_payload(message)
    manifest = payload.get("manifest_content")
    if isinstance(manifest, dict):
        return manifest
    manifest = payload.get("manifest")
    if isinstance(manifest, dict):
        return manifest
    manifest = message.get("manifest_content")
    if isinstance(manifest, dict):
        return manifest
    return {}
