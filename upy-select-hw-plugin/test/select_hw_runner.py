#!/usr/bin/env python3
"""Local runner for upy-select-hw-plugin."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
REPO_ROOT = SKILL_DIR.parent
SAMPLE_DIR = SKILL_DIR / "sample"
BOARD_DIR = REPO_ROOT / "upy-analyze-plugin" / "boards"
RP2_LIKE_FAMILIES = {"rp2", "rp2040", "rp2350"}
PREFERRED_NO_MCU_FAMILIES = RP2_LIKE_FAMILIES | {"esp32", "esp32s2", "esp32s3", "esp32c3", "esp32c6"}
OFFICIAL_ARTIFACT_FILES = [
    ("select_hw_draft.json", "draft", "select-hw 草稿"),
    ("select_hw_validated.json", "manifest", "校验规范化后的 select-hw manifest"),
    ("phase_complete.select_hw.json", "phase_complete", "完整 select-hw 阶段完成消息"),
    ("pin_assignment_log.md", "log", "引脚分配日志"),
    ("select_hw_phase_log.md", "log", "select-hw 阶段日志"),
]


def artifact_paths(session_id: str, *, mode: str = "cwd") -> list[tuple[str, str, str]]:
    if mode == "session_root":
        return [(name, kind, desc) for name, kind, desc in OFFICIAL_ARTIFACT_FILES]
    return [
        (f"sessions/{session_id}/{name}", kind, desc)
        for name, kind, desc in OFFICIAL_ARTIFACT_FILES
    ]
DEFAULT_NO_MCU_ORDER = {
    "raspberry-pi-pico-w": 50,
    "raspberry-pi-pico": 48,
    "esp32-devkit-v1": 46,
    "esp32-s3-devkitc": 44,
    "esp32-c3-devkitm": 42,
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


WORKFLOW_TIME_SCRIPT = REPO_ROOT / "upy-project-gen-toolchain-spec" / "scripts" / "workflow_time.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def workflow_time() -> str:
    if WORKFLOW_TIME_SCRIPT.is_file():
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(WORKFLOW_TIME_SCRIPT), "--json"],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            return data["utc"]
    return utc_now()


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def send(msg: dict[str, Any]) -> None:
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def read_response(expected_type: str) -> dict[str, Any]:
    line = sys.stdin.readline()
    if not line:
        raise RuntimeError(f"expected {expected_type}, but stdin closed")
    msg = json.loads(line)
    if msg.get("type") != expected_type:
        raise RuntimeError(f"expected {expected_type}, got {msg.get('type')}")
    return msg


def envelope(
    msg_type: str,
    session_id: str,
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "msg_id": str(uuid.uuid4()),
        "session_id": session_id,
        "phase": "select-hw",
        "timestamp": workflow_time(),
        "type": msg_type,
        "idempotency_key": idempotency_key,
        "retry_of": None,
        "payload": payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local runner for upy-select-hw-plugin")
    parser.add_argument(
        "--start-file",
        default=str(SAMPLE_DIR / "start_phase.select_hw.json"),
        help="path to start_phase JSON",
    )
    parser.add_argument(
        "--analyze-file",
        default=str(SAMPLE_DIR / "analyze_phase_complete.input.json"),
        help="path to analyze phase_complete JSON",
    )
    return parser.parse_args()


def norm(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def load_board_library() -> list[dict[str, Any]]:
    boards: list[dict[str, Any]] = []
    for path in sorted(BOARD_DIR.glob("*.json")):
        if path.name.startswith("_") or path.name == "matching-rules.json":
            continue
        board = load_json(path)
        if board.get("id") and board.get("firmware"):
            boards.append(board)
    return boards


def board_text(board: dict[str, Any]) -> str:
    firmware = board.get("firmware", {})
    return " ".join(
        str(part)
        for part in [
            board.get("id", ""),
            board.get("display_name", ""),
            board.get("mcu", ""),
            board.get("chip_family", ""),
            firmware.get("board_name", ""),
            firmware.get("port", ""),
        ]
    )


def needs_wifi(requirements: dict[str, Any], devices: list[dict[str, Any]]) -> bool:
    outputs = requirements.get("output", [])
    return (
        requirements.get("network") == "wifi"
        or "cloud_http" in outputs
        or any(device.get("interface") == "WiFi" for device in devices)
    )


def score_board(board: dict[str, Any], manifest: dict[str, Any]) -> int:
    requirements = manifest["requirements"]
    devices = manifest.get("devices", [])
    mcu_specified = requirements.get("mcu_specified")
    family = str(board.get("chip_family", "")).lower()
    specs = board.get("specs", {})
    score = 0

    if board.get("pin_layout"):
        score += 20
    else:
        score -= 100

    if mcu_specified:
        target = norm(mcu_specified)
        text = norm(board_text(board))
        if target and target in text:
            score += 160
        elif target.startswith("esp32") and family.startswith("esp32"):
            score += 70
        elif target.startswith("pico") and family in RP2_LIKE_FAMILIES:
            score += 70
    else:
        score += 100 if family in PREFERRED_NO_MCU_FAMILIES else -100
        score += DEFAULT_NO_MCU_ORDER.get(board.get("id"), 0)

    if needs_wifi(requirements, devices) and specs.get("wifi"):
        score += 18
    if requirements.get("network") in {"ble", "wifi_ble"} and specs.get("ble"):
        score += 10
    if "voice_control" in requirements.get("special_requirements", []):
        if family == "esp32s3":
            score += 18
        elif family.startswith("esp32"):
            score += 8
    if requirements.get("power") in {"battery", "low_power"}:
        if family == "esp32c3":
            score += 15
        elif family in RP2_LIKE_FAMILIES:
            score += 8
    if requirements.get("experience") == "beginner":
        if board.get("beginner_friendly"):
            score += 10
        if family in RP2_LIKE_FAMILIES:
            score += 8
        elif family == "esp32":
            score += 5

    return score


def select_board_candidates(manifest: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    boards = load_board_library()
    scored = sorted(
        boards,
        key=lambda board: (score_board(board, manifest), -int(board.get("price_yuan", 9999))),
        reverse=True,
    )
    return scored[:limit]


def board_by_id(board_id: str) -> dict[str, Any] | None:
    for board in load_board_library():
        if board.get("id") == board_id:
            return board
    return None


def board_item(board: dict[str, Any], manifest: dict[str, Any], selected: bool) -> dict[str, Any]:
    requirements = manifest["requirements"]
    firmware = board.get("firmware", {})
    specs = board.get("specs", {})
    radios = [name for name in ["WiFi", "BLE"] if specs.get(name.lower())]
    radio_text = "/".join(radios) if radios else "no radio"
    meta = "匹配上游 MCU 偏好" if requirements.get("mcu_specified") else "未指定 MCU 时优先 Pico/RP2 与 ESP32 系列"
    if not selected:
        meta = "功能类似备选"
    return {
        "id": board["id"],
        "name": board.get("display_name", board["id"]),
        "subtitle": f"{radio_text}, MicroPython {firmware.get('board_name', 'unknown')}",
        "meta": meta,
        "selected": selected,
    }


def manual_wiring_schema() -> dict[str, Any]:
    return {
        "description": "手动描述每条连线，格式为 MCU 引脚 -> 器件引脚。",
        "fields": [
            {"name": "mcu_pin", "required": True, "example": "GPIO21"},
            {"name": "device", "required": True, "example": "AHT20"},
            {"name": "device_pin", "required": True, "example": "SDA"},
            {"name": "signal", "required": True, "example": "i2c_data"},
            {"name": "voltage", "required": False, "example": "3.3V"},
            {"name": "notes", "required": False, "example": "与其他 I2C 器件共享总线"},
        ],
        "examples": [
            {"mcu_pin": "GPIO21", "device": "AHT20", "device_pin": "SDA", "signal": "i2c_data", "voltage": "3.3V"},
            {"mcu_pin": "3V3", "device": "AHT20", "device_pin": "VCC", "signal": "power_3v3", "voltage": "3.3V"},
            {"mcu_pin": "GND", "device": "AHT20", "device_pin": "GND", "signal": "gnd", "voltage": "0V"},
        ],
    }


def board_unavailable_payload(manifest: dict[str, Any], requested_board: dict[str, Any]) -> dict[str, Any]:
    candidates = select_board_candidates(manifest)
    recommended = candidates[0] if candidates else {}
    return {
        "approval_id": "board_unavailable",
        "header": "指定板卡不在当前板卡库",
        "question": "当前板卡库没有找到用户指定板卡，请选择继续方式",
        "summary": {
            "project_name": manifest["project_name"],
            "requested_board": requested_board.get("id") or requested_board.get("display_name"),
            "requested_mcu_or_module": manifest["requirements"].get("mcu_specified"),
            "board_library": "upy-analyze-plugin/boards",
            "reason": "board_not_found",
        },
        "recommended_similar_board": board_item(recommended, manifest, True) if recommended else None,
        "known_board_options": [board_item(board, manifest, index == 0) for index, board in enumerate(candidates)],
        "manual_wiring_schema": manual_wiring_schema(),
        "multi_select": False,
        "actions": [
            {"label": "使用相似板卡", "value": "use_recommended_similar", "primary": True},
            {"label": "改选已知板卡", "value": "select_known_board"},
            {"label": "手动描述接线", "value": "manual_wiring_description"},
            {"label": "稍后继续", "value": "save_partial"},
        ],
    }


def board_select_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    requirements = manifest["requirements"]
    candidates = select_board_candidates(manifest)
    return {
        "approval_id": "board_select",
        "header": "确认主控板卡",
        "question": "请确认用于该项目的 MicroPython 开发板",
        "summary": {
            "project_name": manifest["project_name"],
            "mcu_specified": requirements.get("mcu_specified"),
            "source_phase": "analyze",
        },
        "items": [board_item(board, manifest, index == 0) for index, board in enumerate(candidates)],
        "multi_select": False,
        "actions": [
            {"label": "确认板卡", "value": "confirm", "primary": True},
            {"label": "稍后继续", "value": "save_partial"},
        ],
    }


def load_sample_draft(upstream_manifest: dict[str, Any]) -> dict[str, Any]:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    draft["upstream_manifest"] = upstream_manifest
    return draft


def parse_script_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result_json = payload.get("result_json")
    if isinstance(result_json, dict):
        return result_json
    stdout = payload.get("stdout") or ""
    if stdout:
        return json.loads(stdout)
    return {"status": "fail", "errors": ["empty script stdout"], "warnings": [], "manifest": None}


def file_list_artifact(session_id: str, *, mode: str = "cwd") -> dict[str, Any]:
    return {
        "type": "file_list",
        "title": "select-hw 直测产物",
        "files": [
            {
                "path": path,
                "status": "created",
                "kind": kind,
                "mime_type": "text/markdown" if path.endswith(".md") else "application/json",
                "description": description,
            }
            for path, kind, description in artifact_paths(session_id, mode=mode)
        ],
    }


def main() -> int:
    args = parse_args()
    start_msg = load_json(Path(args.start_file))
    analyze_msg = load_json(Path(args.analyze_file))
    session_id = start_msg["session_id"]
    upstream_manifest = analyze_msg["payload"]["manifest_content"]
    start_payload = start_msg.get("payload", {})

    send(
        envelope(
            "status_update",
            session_id,
            {
                "step_id": "upstream_manifest_loaded",
                "level": "info",
                "message": "已读取 analyze manifest_content",
            },
        )
    )
    send(
        envelope(
            "status_update",
            session_id,
            {
                "step_id": "board_matching",
                "level": "info",
                "message": "正在根据 MCU 偏好和需求匹配板卡",
            },
        )
    )

    pre_selected_board = start_payload.get("pre_selected_board")
    if isinstance(pre_selected_board, dict) and pre_selected_board.get("id") and board_by_id(pre_selected_board["id"]) is None:
        send(
            envelope(
                "status_update",
                session_id,
                {
                    "step_id": "board_unavailable",
                    "level": "warn",
                    "message": "预选板卡不在 upy-analyze-plugin/boards，正在推荐同系列或相似功能板卡",
                },
            )
        )
        send(
            envelope(
                "approval_request",
                session_id,
                board_unavailable_payload(upstream_manifest, pre_selected_board),
                idempotency_key=f"select-hw:{session_id}:board-unavailable:v1",
            )
        )
        unavailable_response = read_response("approval_response")
        unavailable_action = unavailable_response.get("payload", {}).get("action")
        if unavailable_action in {"manual_wiring_description", "save_partial"}:
            partial = load_json(SAMPLE_DIR / "phase_complete.select_hw.partial.json")
            send(partial)
            return 0

    send(
        envelope(
            "approval_request",
            session_id,
            board_select_payload(upstream_manifest),
            idempotency_key=f"select-hw:{session_id}:board-select:v1",
        )
    )
    approval = read_response("approval_response")
    action = approval.get("payload", {}).get("action")
    if action not in {"confirm", "accept"}:
        partial = load_json(SAMPLE_DIR / "phase_complete.select_hw.partial.json")
        send(partial)
        return 0

    for step_id, message in [
        ("board_selected", "已确认 ESP32-C3-DevKitM-1"),
        ("firmware_check", "正在核验 MicroPython 固件"),
        ("firmware_ok", "固件入口 ESP32_GENERIC_C3 可用"),
        ("pin_assignment", "正在分配 I2C/GPIO/I2S/电源引脚"),
        ("pin_assignment_done", "引脚分配完成"),
        ("bom_ready", "BOM 已生成"),
        ("manifest_validation", "正在运行 select_hw_manifest.py 校验"),
    ]:
        send(
            envelope(
                "status_update",
                session_id,
                {
                    "step_id": step_id,
                    "level": "success" if step_id in {"board_selected", "firmware_ok", "pin_assignment_done", "bom_ready"} else "info",
                    "message": message,
                },
            )
        )

    draft = load_sample_draft(upstream_manifest)
    send(
        envelope(
            "status_update",
            session_id,
            {
                "step_id": "pin_assignment_draft_ready",
                "level": "info",
                "message": "引脚方案草稿已生成，等待用户确认",
            },
        )
    )
    send(
        envelope(
            "approval_request",
            session_id,
            {
                "approval_id": "pin_plan_review",
                "header": "确认引脚分配",
                "summary": {
                    "board_id": draft["hardware_plan"]["mcu"]["board_id"],
                    "board_definition": f"upy-analyze-plugin/boards/{draft['hardware_plan']['mcu']['board_id']}.json",
                    "requires_schematic_review": True,
                },
                "pinout": draft["hardware_plan"].get("pinout", []),
                "pin_decisions": draft["hardware_plan"].get("pin_decisions", []),
                "warnings": draft.get("warnings", []),
                "actions": [
                    {"label": "确认引脚方案", "value": "confirm_pin_plan", "primary": True},
                    {"label": "重新分配引脚", "value": "revise_pin_plan"},
                    {"label": "手动描述接线", "value": "manual_wiring_description"},
                    {"label": "稍后继续", "value": "save_partial"},
                ],
            },
            idempotency_key=f"select-hw:{session_id}:pin-plan-review:v1",
        )
    )
    pin_review_response = read_response("approval_response")
    pin_review_action = pin_review_response.get("payload", {}).get("action")
    if pin_review_action not in {"confirm_pin_plan", "confirm", "accept"}:
        partial = load_json(SAMPLE_DIR / "phase_complete.select_hw.partial.json")
        send(partial)
        return 0
    draft["hardware_plan"]["pin_review"] = {
        "approval_id": "pin_plan_review",
        "confirmed": True,
        "confirmed_by": "mock_plugin",
        "confirmed_at": workflow_time(),
        "source": "approval_response",
        "action": pin_review_action,
    }
    send(
        envelope(
            "script_run",
            session_id,
            {
                "script_id": "select_hw_manifest",
                "interpreter": "python",
                "script": "upy-select-hw-plugin/scripts/select_hw_manifest.py",
                "args": ["--stdin", "--board-root", "upy-analyze-plugin/boards", "--strict-board-pins"],
                "stdin_json": draft,
                "timeout_ms": 30000,
                "on_timeout": "partial_checkpoint",
            },
            idempotency_key=f"select-hw:{session_id}:manifest-validation:v1",
        )
    )
    script_result = read_response("script_result")
    result = parse_script_payload(script_result["payload"])
    if result.get("status") != "ok":
        send(
            envelope(
                "phase_complete",
                session_id,
                {
                    "phase": "select-hw",
                    "result": "failed",
                    "summary": "select-hw manifest 校验失败",
                    "next_phase": None,
                    "manifest_content": None,
                    "artifacts": [],
                    "warnings": result.get("warnings", []),
                    "errors": result.get("errors", []),
                    "structured_errors": [
                        {
                            "code": "script_failed",
                            "message": "select_hw_manifest.py returned fail",
                            "severity": "error",
                            "recoverable": True,
                            "retryable": True,
                            "source": "select_hw_manifest.py",
                        }
                    ],
                },
            )
        )
        return 0

    manifest = result["manifest"]
    phase_timestamp = workflow_time()
    phase_complete = {
        "protocol_version": "1.0",
        "msg_id": str(uuid.uuid4()),
        "session_id": session_id,
        "phase": "select-hw",
        "timestamp": phase_timestamp,
        "type": "phase_complete",
        "idempotency_key": f"select-hw:{session_id}:phase-complete:v1",
        "retry_of": None,
        "payload": {
            "phase": "select-hw",
            "result": "success",
            "summary": "硬件选型完成：ESP32-C3-DevKitM-1，已生成固件、引脚和 BOM 方案",
            "next_phase": "upy-flash-mpy-firmware-plugin",
            "runtime_context": {
                "artifact_root": ".",
                "artifact_root_mode": "cwd",
                "session_root": f"sessions/{session_id}",
                "resource_root": str(REPO_ROOT),
            },
            "manifest_content": manifest,
            "artifacts": [
                {
                    "type": "table",
                    "title": "硬件选型结果",
                    "headers": ["项目", "值"],
                    "rows": [
                        ["板卡", manifest["mcu"]["display_name"]],
                        ["固件", manifest["mcu"]["firmware_board_name"]],
                        ["BOM 估算", f"{manifest['estimated_total_yuan']} CNY"],
                        ["下一阶段", "upy-flash-mpy-firmware-plugin"],
                    ],
                },
                file_list_artifact(session_id, mode="cwd"),
            ],
            "warnings": result.get("warnings", []) + ["BOM 价格为 V0 常识估算"],
            "errors": [],
            "structured_errors": [],
        },
    }
    send(phase_complete)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
