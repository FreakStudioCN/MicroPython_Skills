#!/usr/bin/env python3
"""Smoke tests for upy-maixpy-export-plugin bundled resources."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_python(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def write_sample_project(project_root: Path) -> None:
    out_dir = project_root / "sipeed_vision"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "examples/uart_jsonl_bridge.py", out_dir / "main.py")
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# Sipeed vision module",
                "",
                "sipeed_vision/main.py runs on MaixCAM Pro with MaixPy/MaixVision, not the MicroPython master board.",
                "UART wiring uses UART1: A19 TX to master RX, A18 RX to master TX, and GND to GND.",
                "Use 115200 baud and JSON Lines with type/label/score/x/y/w/h fields.",
                "MaixCAM Pro IO is 3.3 V and not 5 V tolerant.",
                "UART0 is not preferred because it can be related to logs, maix protocol, or boot behavior.",
                "Firmware flashing, OS upgrade, model training, MaixHub, MaixVision connection, and deployment are manual external flows.",
                "If AI models are involved, put model files under /root/models first.",
                "",
                "Official links:",
                "- https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html",
                "- https://wiki.sipeed.com/maixpy/",
                "- https://github.com/sipeed/maixpy",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    run_python("scripts/validate_reference_index.py", "--skill-root", str(ROOT))
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp)
        write_sample_project(project_root)
        run_python("scripts/validate_maixpy_export.py", "--project-root", str(project_root))
    print("smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
