#!/usr/bin/env python3
"""Deploy-plugin wrapper for the shared serial port scanner."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def candidate_shared_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = os.environ.get("UPY_SHARED_PLUGIN_SCRIPTS")
    if env_root:
        roots.append(Path(env_root))
    for parent in Path(__file__).resolve().parents:
        roots.append(parent / "shared-plugin-scripts")
    return roots


def find_shared_script() -> Path:
    for root in candidate_shared_roots():
        candidates = [
            root / "mpremote" / "list_serial_ports.py",
            root / "shared-plugin-scripts" / "mpremote" / "list_serial_ports.py",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(
        "shared-plugin-scripts/mpremote/list_serial_ports.py was not found; "
        "set UPY_SHARED_PLUGIN_SCRIPTS or run from a checkout containing shared-plugin-scripts"
    )


if __name__ == "__main__":
    try:
        runpy.run_path(str(find_shared_script()), run_name="__main__")
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
