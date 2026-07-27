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


def run_python_capture(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


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
                "- https://wiki.sipeed.com/maixvision",
                "- https://wiki.sipeed.com/maixpy/doc/zh/basic/maixvision.html",
                "- https://github.com/sipeed/maixpy",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_bad_face_project(project_root: Path) -> None:
    out_dir = project_root / "sipeed_vision"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "main.py").write_text(
        "\n".join(
            [
                "import json",
                "from maix import camera, display, uart, pinmap, err, app, nn, image, time",
                "err.check_raise(pinmap.set_pin_function('A19', 'UART1_TX'), 'tx')",
                "err.check_raise(pinmap.set_pin_function('A18', 'UART1_RX'), 'rx')",
                "serial = uart.UART('/dev/ttyS1', 115200)",
                "recognizer = nn.FaceRecognizer(detect_model='/root/models/yolov8n_face.mud', feature_model='/root/models/face_feature.mud', dual_buff=True)",
                "try:",
                "    recognizer.load_faces('/root/models/faces.bin')",
                "except Exception:",
                "    pass",
                "cam = camera.Camera(640, 480)",
                "disp = display.Display()",
                "payload = {'type': 'face', 'label': 'unknown', 'score': 0.0, 'x': 0, 'y': 0, 'w': 0, 'h': 0}",
                "serial.write_str(json.dumps(payload) + '\\n')",
                "while not app.need_exit():",
                "    img = cam.read()",
                "    img.draw_rect(0, 0, 1, 1, image.Color.from_rgb(0, 255, 0), 1)",
                "    disp.show(img)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# Sipeed vision module",
                "main.py runs on MaixCAM Pro with MaixPy/MaixVision, not on the MicroPython master board.",
                "UART1 A19 A18 115200 JSON Lines 3.3 V 5 V.",
                "Firmware flashing, OS upgrade, model training, MaixHub, MaixVision connection, and deployment are manual external flows.",
                "https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html",
                "https://wiki.sipeed.com/maixpy/",
                "https://wiki.sipeed.com/maixvision",
                "https://wiki.sipeed.com/maixpy/doc/zh/basic/maixvision.html",
                "https://github.com/sipeed/maixpy",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_link_only_project(project_root: Path) -> None:
    out_dir = project_root / "sipeed_vision"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "main.py").write_text(
        "\n".join(
            [
                "# Unsupported in stage A.",
                "# No runnable MaixPy code can be generated for this task.",
                "# The local Skill reference is not codegen-ready for network streaming.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# Network / Streaming / WebRTC",
                "",
                "This task is unsupported in stage A and remains link-only.",
                "The local Skill reference is not codegen-ready for network or streaming codegen.",
                "Use the official documentation and manual guidance instead of generated runnable code.",
                "Firmware and OS upgrade remain manual external flows.",
                "",
                "Runtime context:",
                "- MaixCAM Pro",
                "- MaixPy",
                "- MaixVision",
                "",
                "Official links:",
                "- https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html",
                "- https://wiki.sipeed.com/maixpy/",
                "- https://wiki.sipeed.com/maixvision",
                "- https://wiki.sipeed.com/maixpy/doc/zh/basic/maixvision.html",
                "- https://github.com/sipeed/maixpy",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    official_links = (ROOT / "references/official_links.json").read_text(encoding="utf-8")
    assert "https://wiki.sipeed.com/maixvision" in official_links
    assert "https://wiki.sipeed.com/maixpy/doc/zh/basic/maixvision.html" in official_links
    sample_phase = (ROOT / "sample/phase_complete.maixpy_export.success.json").read_text(encoding="utf-8")
    assert "https://wiki.sipeed.com/maixvision" in sample_phase
    run_python("scripts/validate_reference_index.py", "--skill-root", str(ROOT))
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp)
        write_sample_project(project_root)
        run_python("scripts/validate_maixpy_export.py", "--project-root", str(project_root))
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp)
        write_bad_face_project(project_root)
        result = run_python_capture("scripts/validate_maixpy_export.py", "--project-root", str(project_root))
        assert result.returncode != 0
        assert "image.Color.from_rgb" in result.stdout
        assert "input_width()" in result.stdout
        assert "fs.exists" in result.stdout
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp)
        write_link_only_project(project_root)
        result = run_python_capture("scripts/validate_maixpy_export.py", "--project-root", str(project_root))
        assert result.returncode == 0, result.stdout
        assert '"validation_mode": "link_only"' in result.stdout
        assert '"warnings": []' in result.stdout
    print("smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
