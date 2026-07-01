#!/usr/bin/env python3
"""
Local runner for upy-analyze-plugin.

This runner owns the workflow shell:
- read start_phase
- call llm_analyze interface layer
- emit approval/status/script_run/phase_complete messages
"""

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from llm_analyze import analyze_with_llm_contract
from pkg_guide_adapter import resolve_driver

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
SAMPLE_DIR = SKILL_DIR / "sample"


def emit(msg_type: str, phase: str, payload: dict[str, Any], session_id: str) -> dict[str, Any]:
    return {
        "msg_id": str(uuid.uuid4()),
        "session_id": session_id,
        "phase": phase,
        "type": msg_type,
        "payload": payload,
    }


def send(msg: dict[str, Any]) -> None:
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def read_response(expected_type: Optional[str] = None) -> dict[str, Any]:
    line = sys.stdin.readline()
    if not line:
        raise RuntimeError("runner expected plugin response but stdin closed")
    msg = json.loads(line)
    if expected_type and msg.get("type") != expected_type:
        raise RuntimeError(f"expected {expected_type}, got {msg.get('type')}")
    return msg


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local runner for upy-analyze-plugin")
    parser.add_argument(
        "--start-file",
        default=str(SAMPLE_DIR / "start_phase.analyze.json"),
        help="path to start_phase JSON",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    return (text or "").lower()


def needs_requirement_supplement(start_payload: dict[str, Any], llm_result: dict[str, Any]) -> bool:
    mode = start_payload.get("preferences", {}).get("mode", "beginner")
    if mode not in {"beginner", "custom"}:
        return False

    requirements = llm_result.get("requirements", {})
    output = requirements.get("output")
    fields = [
        requirements.get("scene"),
        requirements.get("power"),
        output,
        requirements.get("sample_rate"),
        requirements.get("precision"),
        requirements.get("response_time"),
    ]
    return any(value in (None, "", []) for value in fields)


def enrich_devices_for_runner(llm_devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for index, item in enumerate(llm_devices, start=1):
        device = dict(item)
        device["id"] = f"d{index}"
        if not device.get("subtitle"):
            device["subtitle"] = f"{device.get('interface', 'unknown')} {device.get('name', '')}"
        devices.append(device)
    return devices


def build_device_confirm_payload(
    start_payload: dict[str, Any],
    project_name: str,
    devices: list[dict[str, Any]],
) -> dict[str, Any]:
    board = start_payload.get("pre_selected_board")
    board_summary = {"status": "none"}
    if board:
        board_summary = {
            "status": "selected",
            "display_name": board.get("display_name"),
            "mcu": board.get("mcu"),
        }

    return {
        "approval_id": "device_confirm",
        "header": "确认项目方案",
        "question": "请确认以下器件是否正确",
        "summary": {
            "project_name": project_name,
            "description": start_payload.get("user_description", ""),
            "board": board_summary,
        },
        "items": [
            {
                "id": item["id"],
                "name": item["name"],
                "subtitle": item["subtitle"],
                "meta": "用户指定" if item["source"] == "user_specified" else "系统推荐",
                "selected": True,
            }
            for item in devices
        ],
        "allow_add": True,
        "allow_remove": True,
        "multi_select": True,
        "actions": [
            {"label": "确认，开始搜索驱动", "value": "confirm", "primary": True},
        ],
    }


def build_manifest_draft(
    start_payload: dict[str, Any],
    llm_result: dict[str, Any],
    inferred_devices: list[dict[str, Any]],
    device_confirm_response: dict[str, Any],
) -> dict[str, Any]:
    selected_ids = set(device_confirm_response.get("payload", {}).get("selected_ids", []))
    added_items = device_confirm_response.get("payload", {}).get("added_items", [])
    mode = start_payload.get("preferences", {}).get("mode", "beginner")

    devices = []
    for item in inferred_devices:
        if item["id"] in selected_ids:
            devices.append(
                {
                    "name": item["name"],
                    "type": item["type"],
                    "interface": item["interface"],
                    "source": item["source"],
                    "driver": item["driver"],
                }
            )

    for item in added_items:
        name = item.get("name", "").strip()
        if not name:
            continue
        devices.append(
            {
                "name": name,
                "type": item.get("type", "user_added"),
                "interface": item.get("interface", "GPIO"),
                "source": "user_specified",
                "driver": {"source": "none"},
            }
        )

    return {
        "project_name": llm_result["project_name"],
        "requirements": {
            "description": llm_result["requirements"]["description"],
            "experience": "beginner" if mode == "beginner" else "experienced",
            "output": ["serial"],
            "existing_hardware": start_payload.get("existing_hardware", []),
            "mcu_specified": (start_payload.get("pre_selected_board") or {}).get("mcu"),
        },
        "devices": devices,
    }


def resolve_device_drivers(manifest_draft: dict[str, Any]) -> None:
    for device in manifest_draft["devices"]:
        device["driver"] = resolve_driver(device)


def apply_requirement_supplement(manifest_draft: dict[str, Any], supplement_response: Optional[dict[str, Any]]) -> None:
    if not supplement_response:
        return
    selected_ids = set(supplement_response.get("payload", {}).get("selected_ids", []))
    requirements = manifest_draft["requirements"]
    if "scene_indoor" in selected_ids:
        requirements["scene"] = "indoor"
    if "power_usb" in selected_ids:
        requirements["power"] = "usb"
    if "perf_normal" in selected_ids:
        requirements["sample_rate"] = "normal_1hz"
        requirements["precision"] = "normal"
        requirements["response_time"] = "1s"
    if "output_serial_oled" in selected_ids:
        requirements["output"] = ["serial", "display_oled", "buzzer"]


def maybe_trigger_alternative_device(start_payload: dict[str, Any], manifest_draft: dict[str, Any]) -> bool:
    description = normalize_text(start_payload.get("user_description", ""))
    if "generic-sensor-no-driver" in description:
        return True
    return any(
        device["source"] == "system_recommended" and device["driver"]["source"] == "none"
        for device in manifest_draft["devices"]
    )


def maybe_trigger_cold_driver(start_payload: dict[str, Any], manifest_draft: dict[str, Any]) -> bool:
    description = normalize_text(start_payload.get("user_description", ""))
    if "sht30-no-driver" in description:
        return True
    return any(
        device["source"] == "user_specified" and device["driver"]["source"] == "none"
        for device in manifest_draft["devices"]
    )


def parse_script_result(payload: dict[str, Any]) -> dict[str, Any]:
    result_json = payload.get("result_json")
    stdout = (payload.get("stdout") or "").strip()
    stderr = (payload.get("stderr") or "").strip()
    exit_code = payload.get("exit_code", 1)
    if isinstance(result_json, dict):
        result = result_json
    else:
        try:
            result = json.loads(stdout) if stdout else {"status": "fail", "errors": ["empty stdout"], "manifest": None}
        except json.JSONDecodeError:
            result = {"status": "fail", "errors": ["invalid json from stdout"], "manifest": None}
    result["_exit_code"] = exit_code
    result["_stderr"] = stderr
    return result


def pick_first_device_by_name(manifest_draft: dict[str, Any], names: list[str]) -> Optional[dict[str, Any]]:
    for device in manifest_draft["devices"]:
        if device["name"] in names:
            return device
    return manifest_draft["devices"][0] if manifest_draft["devices"] else None


def emit_device_driver_progress(device: dict[str, Any], phase: str, session_id: str) -> None:
    name = device["name"]
    interface = device["interface"]
    driver = device["driver"]
    source = driver["source"]

    if source == "builtin_runtime":
        module = driver.get("module", "builtin runtime")
        send(
            emit(
                "status_update",
                phase,
                {
                    "step_id": "driver_found",
                    "level": "success",
                    "message": f"底层能力 OK {name} -> builtin_runtime ({module})",
                },
                session_id,
            )
        )
        if interface in {"I2C", "SPI", "UART"}:
            send(
                emit(
                    "status_update",
                    phase,
                    {
                        "step_id": "driver_search",
                        "level": "info",
                        "message": f"{name} 属于 {interface} 具体器件，仍应继续优先检查 upypi",
                    },
                    session_id,
                )
            )
        return

    if source == "micropython_lib":
        pkg_name = driver.get("package_name", "micropython-lib package")
        send(
            emit(
                "status_update",
                phase,
                {
                    "step_id": "driver_found",
                    "level": "success",
                    "message": f"官方生态库 OK {name} -> micropython_lib ({pkg_name})",
                },
                session_id,
            )
        )
        return

    if source in {"upypi", "awesome-micropython", "github"}:
        send(
            emit(
                "status_update",
                phase,
                {
                    "step_id": "driver_found",
                    "level": "success",
                    "message": f"具体器件驱动 OK {name} -> {source}",
                },
                session_id,
            )
        )
        return

    if source == "cold-driver":
        send(
            emit(
                "status_update",
                phase,
                {
                    "step_id": "driver_cold",
                    "level": "warn",
                    "message": f"提示 {name} -> 需进入冷门驱动路径",
                },
                session_id,
            )
        )
        return

    send(
        emit(
            "status_update",
            phase,
            {
                "step_id": "driver_none",
                "level": "warn",
                "message": f"提示 {name} -> 暂无现成驱动",
            },
            session_id,
        )
    )


def artifact_status_text(device: dict[str, Any]) -> str:
    driver = device["driver"]
    source = driver["source"]
    if source == "builtin_runtime":
        return f"OK ({driver.get('module', 'builtin runtime')})"
    if source == "micropython_lib":
        return f"OK ({driver.get('package_name', 'micropython-lib')})"
    if source in {"upypi", "awesome-micropython", "github"}:
        return "OK"
    if source == "cold-driver":
        return "需后续冷门驱动生成与验证"
    return "暂无现成驱动"


def main() -> None:
    args = parse_args()
    start_msg = load_json(Path(args.start_file))
    session_id = start_msg.get("session_id", str(uuid.uuid4()))
    phase = start_msg.get("phase", "analyze")
    start_payload = start_msg["payload"]

    llm_result = analyze_with_llm_contract(start_payload)
    inferred_devices = enrich_devices_for_runner(llm_result["devices"])
    device_names = ", ".join(item["name"] for item in inferred_devices[:5])

    send(emit("status_update", phase, {"step_id": "intent_extraction", "level": "info", "message": "正在分析需求..."}, session_id))
    send(
        emit(
            "status_update",
            phase,
            {
                "step_id": "intent_done",
                "level": "success",
                "message": f"提取到 {len(inferred_devices)} 个器件: {device_names}",
            },
            session_id,
        )
    )

    send(
        {
            "msg_id": str(uuid.uuid4()),
            "session_id": session_id,
            "phase": phase,
            "type": "approval_request",
            "payload": build_device_confirm_payload(start_payload, llm_result["project_name"], inferred_devices),
        }
    )
    approval_response = read_response("approval_response")

    supplement_response = None
    if needs_requirement_supplement(start_payload, llm_result):
        supplement_msg = load_json(SAMPLE_DIR / "approval_request.requirement_supplement.json")
        supplement_msg["session_id"] = session_id
        supplement_msg["phase"] = phase
        supplement_msg["msg_id"] = str(uuid.uuid4())
        send(supplement_msg)
        supplement_response = read_response("approval_response")

    manifest_draft = build_manifest_draft(start_payload, llm_result, inferred_devices, approval_response)
    apply_requirement_supplement(manifest_draft, supplement_response)
    resolve_device_drivers(manifest_draft)

    total_devices = max(1, len(manifest_draft["devices"]))
    send(emit("status_update", phase, {"step_id": "driver_search", "level": "info", "message": f"正在搜索驱动... (1/{total_devices})"}, session_id))
    for device in manifest_draft["devices"]:
        emit_device_driver_progress(device, phase, session_id)

    if maybe_trigger_alternative_device(start_payload, manifest_draft):
        alt_msg = load_json(SAMPLE_DIR / "approval_request.alternative_device.json")
        alt_msg["session_id"] = session_id
        alt_msg["phase"] = phase
        alt_msg["msg_id"] = str(uuid.uuid4())
        send(alt_msg)
        alt_response = read_response("approval_response")
        target = pick_first_device_by_name(manifest_draft, ["SHT30", "土壤湿度传感器", "通用传感器"])
        if target:
            action = alt_response.get("payload", {}).get("action")
            if action == "accept_alt1":
                target["name"] = "HDC1080"
                target["type"] = "temperature_humidity_sensor"
                target["interface"] = "I2C"
                target["driver"] = resolve_driver(target)
            elif action == "accept_alt2":
                target["name"] = "AHT20"
                target["type"] = "temperature_humidity_sensor"
                target["interface"] = "I2C"
                target["driver"] = resolve_driver(target)
            else:
                target["driver"] = {
                    "source": "cold-driver",
                    "search_provider": "pkg_guide_adapter",
                    "search_mode": "mock",
                    "mock": True,
                    "query": f"{target['name']} {target['interface']} {target['type']} MicroPython driver",
                    "notes": "mock local runner: user kept original device after no ready driver path",
                }

    if maybe_trigger_cold_driver(start_payload, manifest_draft):
        target = pick_first_device_by_name(manifest_draft, ["SHT30", "土壤湿度传感器", "通用传感器"])
        if target:
            target["source"] = "user_specified"
            target["driver"] = {
                "source": "cold-driver",
                "search_provider": "pkg_guide_adapter",
                "search_mode": "mock",
                "mock": True,
                "query": f"{target['name']} {target['interface']} {target['type']} MicroPython driver",
                "notes": "mock local runner: forced cold-driver branch",
            }

    send(
        emit(
            "script_run",
            phase,
            {
                "script_id": "init_manifest",
                "interpreter": "python",
                "script": str(SKILL_DIR / "scripts" / "init_manifest.py"),
                "args": ["--stdin"],
                "stdin_json": manifest_draft,
            },
            session_id,
        )
    )

    script_result = read_response("script_result")
    if not script_result["payload"].get("success"):
        send(
            emit(
                "phase_complete",
                phase,
                {
                    "phase": "analyze",
                    "result": "failed",
                    "summary": "manifest 校验脚本执行失败",
                    "next_phase": None,
                    "next_skill": None,
                    "manifest_content": None,
                    "artifacts": [],
                    "warnings": [],
                    "errors": [script_result["payload"].get("stderr", "script failed")],
                },
                session_id,
            )
        )
        return

    validation = parse_script_result(script_result["payload"])
    if validation.get("status") != "ok":
        send(
            emit(
                "phase_complete",
                phase,
                {
                    "phase": "analyze",
                    "result": "failed",
                    "summary": "manifest 校验失败",
                    "next_phase": None,
                    "next_skill": None,
                    "manifest_content": None,
                    "artifacts": [],
                    "warnings": validation.get("warnings", []),
                    "errors": validation.get("errors", []),
                },
                session_id,
            )
        )
        return

    warnings = list(validation.get("warnings", []))
    artifact_rows = []
    for device in validation["manifest"]["devices"]:
        driver_source = device["driver"]["source"]
        if driver_source == "cold-driver":
            warnings.append(f"{device['name']} 暂无现成驱动，后续应进入冷门驱动流程")
        artifact_rows.append([device["name"], device["interface"], driver_source, artifact_status_text(device)])

    summary = f"器件分析完成，识别到 {len(validation['manifest']['devices'])} 个器件"
    send(
        emit(
            "phase_complete",
            phase,
            {
                "phase": "analyze",
                "result": "success",
                "summary": summary,
                "next_phase": "select-hw",
                "next_skill": "/upy-select-hw-plugin",
                "manifest_content": validation["manifest"],
                "artifacts": [
                    {
                        "type": "table",
                        "title": "器件驱动状态",
                        "headers": ["器件", "接口", "驱动来源", "状态"],
                        "rows": artifact_rows,
                    }
                ],
                "warnings": warnings,
                "errors": [],
            },
            session_id,
        )
    )


if __name__ == "__main__":
    main()
