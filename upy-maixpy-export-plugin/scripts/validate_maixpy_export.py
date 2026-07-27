#!/usr/bin/env python3
"""Validate generated sipeed_vision artifacts for stage A."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REQUIRED_JSONL_KEYS = ['"type"', '"label"', '"score"', '"x"', '"y"', '"w"', '"h"']
FORBIDDEN_MAIN_TOKENS = [
    "from machine import",
    "import machine",
    "mpremote",
    "esptool",
    "mip.install",
    "project-manifest.json",
    "firmware/",
    "image.Color.from_rgb",
]
README_BASE_REQUIRED = [
    "MaixCAM",
    "MaixPy",
    "MaixVision",
    "https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html",
    "https://wiki.sipeed.com/maixpy/",
    "https://wiki.sipeed.com/maixvision",
    "https://wiki.sipeed.com/maixpy/doc/zh/basic/maixvision.html",
    "https://github.com/sipeed/maixpy",
]
README_RUNTIME_REQUIRED = [
    "UART1",
    "A19",
    "A18",
    "115200",
    "JSON Lines",
    "3.3",
    "5 V",
]
README_REQUIRED_ONE_OF = [
    (
        "not the MicroPython master",
        "not on the MicroPython master",
    ),
]
FORBIDDEN_MISLEADING_PHRASES = [
    "maixpy does not support",
    "not supported by maixpy",
    "maixpy api does not exist",
    "official api does not exist",
    "official api is unavailable",
    "api not available in maixpy",
    "api unavailable in maixpy",
]
MODEL_BACKED_MARKERS = [
    "nn.YOLOv5(",
    "nn.YOLOv8(",
    "nn.YOLO11(",
    "nn.YOLOWorld(",
    "nn.FaceRecognizer(",
    "nn.PP_OCR(",
]
LINK_ONLY_MARKERS = [
    "no runnable maixpy code can be generated",
    "link-only",
    "link only",
    "not_codegen_ready",
    "unsupported in stage a",
]
LINK_ONLY_GUIDANCE_MARKERS = [
    "local skill reference",
    "manual guidance",
    "official documentation",
    "official api",
]
FIRMWARE_MARKERS = [
    "firmware flashing",
    "firmware flashed manually",
    "flash the latest maixpy firmware",
    "firmware",
    "os upgrade",
]
MANUAL_FLOW_MARKERS = [
    "manual",
    "external flow",
    "external flows",
]
MODEL_GUIDANCE_MARKERS = [
    "maixhub",
    "/root/models",
    "model path",
    "model files",
]


def has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def contains_required(text: str, token: str) -> bool:
    if token.startswith(('http://', 'https://')):
        return token in text
    return token.lower() in text.lower()

def is_link_only_output(main_text: str, readme_text: str) -> bool:
    combined = f"{main_text}\n{readme_text}".lower()
    return has_any(combined, tuple(LINK_ONLY_MARKERS))


def has_firmware_manual_guidance(readme_text: str) -> bool:
    text = readme_text.lower()
    return has_any(text, tuple(FIRMWARE_MARKERS)) and has_any(text, tuple(MANUAL_FLOW_MARKERS))


def has_model_guidance(readme_text: str) -> bool:
    return has_any(readme_text.lower(), tuple(MODEL_GUIDANCE_MARKERS))


def has_try_wrapped_call(text: str, call_token: str) -> bool:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped != "try:":
            continue
        try_indent = len(line) - len(line.lstrip())
        for child in lines[idx + 1 :]:
            if not child.strip():
                continue
            child_indent = len(child) - len(child.lstrip())
            if child_indent <= try_indent:
                break
            if call_token in child:
                return True
    return False


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def validate(project_root: Path) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    warnings: list[str] = []
    out_dir = project_root / "sipeed_vision"
    main_py = out_dir / "main.py"
    readme = out_dir / "README.md"

    if not main_py.exists():
        errors.append("missing sipeed_vision/main.py")
    if not readme.exists():
        errors.append("missing sipeed_vision/README.md")
    if errors:
        return errors, {"errors": errors, "warnings": warnings}

    main_text = read_text(main_py)
    readme_text = read_text(readme)
    link_only = is_link_only_output(main_text, readme_text)
    model_backed = has_any(main_text, tuple(MODEL_BACKED_MARKERS))

    for token in FORBIDDEN_MAIN_TOKENS:
        if token in main_text:
            errors.append(f"main.py contains forbidden token: {token}")

    if link_only:
        if "from maix import" in main_text or "import maix" in main_text:
            errors.append("link-only partial output must not include runnable MaixPy imports in main.py")
        combined_lower = f"{main_text}\n{readme_text}".lower()
        if not has_any(combined_lower, tuple(LINK_ONLY_GUIDANCE_MARKERS)):
            errors.append("link-only partial output must cite local Skill readiness and official/manual guidance")
    else:
        if "from maix import" not in main_text:
            errors.append("main.py must use MaixPy imports from maix")
        for token in ["UART", "A19", "A18", "115200"]:
            if token not in main_text:
                errors.append(f"main.py missing UART default token: {token}")
        for token in REQUIRED_JSONL_KEYS:
            if token not in main_text:
                errors.append(f"main.py missing JSONL field token: {token}")

    for token in README_BASE_REQUIRED:
        if not contains_required(readme_text, token):
            errors.append(f"README.md missing required text: {token}")
    if not link_only:
        for token in README_RUNTIME_REQUIRED:
            if not contains_required(readme_text, token):
                errors.append(f"README.md missing required text: {token}")
        for group in README_REQUIRED_ONE_OF:
            if not has_any(readme_text, group):
                errors.append("README.md missing one of required text options: " + " | ".join(group))

    combined_lower = f"{main_text}\n{readme_text}".lower()
    for phrase in FORBIDDEN_MISLEADING_PHRASES:
        if phrase in combined_lower:
            errors.append(
                "generated artifacts must not describe local reference gaps as official MaixPy API gaps: "
                + phrase
            )
    if model_backed:
        for token in ["input_width()", "input_height()", "input_format()"]:
            if token not in main_text:
                errors.append(f"model-backed vision code must initialize camera from model wrapper: missing {token}")
        if "camera.Camera(640, 480)" in main_text:
            errors.append("model-backed vision code must not hard-code camera.Camera(640, 480)")
    if "nn.FaceRecognizer(" in main_text:
        if "fs.exists(" not in main_text:
            errors.append("FaceRecognizer code must check fs.exists(face_db_path) before load_faces")
        if "load_faces(" in main_text and "err.check_raise" not in main_text:
            errors.append("FaceRecognizer load_faces result must be checked with err.check_raise")
        if has_try_wrapped_call(main_text, "load_faces("):
            warnings.append("FaceRecognizer load_faces should prefer fs.exists + err.check_raise over broad try/except")
    if not link_only and not has_firmware_manual_guidance(readme_text):
        warnings.append("README.md should mention firmware flashing is manual/external")
    if model_backed and not has_model_guidance(readme_text):
        warnings.append("README.md should include MaixHub/model preparation guidance when AI models are involved")

    summary = {
        "project_root": str(project_root),
        "validation_mode": "link_only" if link_only else "runnable",
        "files": [
            {"path": "sipeed_vision/main.py", "sha256": sha256(main_py)},
            {"path": "sipeed_vision/README.md", "sha256": sha256(readme)},
        ],
        "warnings": warnings,
        "errors": errors,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args(argv)

    errors, summary = validate(Path(args.project_root).resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())


