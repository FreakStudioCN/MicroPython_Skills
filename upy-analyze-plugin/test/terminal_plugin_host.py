#!/usr/bin/env python3
"""
Terminal plugin-host simulator for upy-analyze-plugin.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Optional


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
BOARDS_DIR = SKILL_DIR / "boards"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")


def prompt(text: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{text}{suffix}: ").strip()
    if not value and default is not None:
        return default
    return value


def separator(title: str) -> None:
    print(f"\n{'=' * 16} {title} {'=' * 16}")


def load_board_choices() -> list[dict[str, Any]]:
    boards: list[dict[str, Any]] = []
    for path in sorted(BOARDS_DIR.glob("*.json")):
        if path.name in {"matching-rules.json", "_template.json"}:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        boards.append(
            {
                "id": data.get("id", path.stem),
                "display_name": data.get("display_name", path.stem),
                "mcu": data.get("mcu", ""),
                "chip_family": data.get("chip_family", ""),
                "firmware_url": data.get("firmware_url", ""),
            }
        )
    return boards


def choose_board() -> Optional[dict[str, Any]]:
    boards = load_board_choices()
    separator("Board Select")
    print("0. 不预选板卡")
    for index, board in enumerate(boards, start=1):
        print(f"{index}. {board['display_name']} ({board['mcu']})")
    raw = prompt("输入编号或板卡名", "0").strip()
    if not raw or raw == "0":
        return None
    try:
        idx = int(raw)
    except ValueError:
        idx = None
    if idx is not None:
        if 1 <= idx <= len(boards):
            return dict(boards[idx - 1])
        return None
    lowered = raw.lower()
    for board in boards:
        if lowered in board["display_name"].lower() or lowered == board["id"].lower():
            return dict(board)
    return None


def parse_existing_hardware(raw: str) -> list[str]:
    ignored = {"", "无", "没有", "none", "null", "n/a", "na"}
    values = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if item.lower() in ignored or item in ignored:
            continue
        values.append(item)
    return values


def build_start_phase() -> dict[str, Any]:
    separator("Start Phase")
    description = prompt("用户需求", "做一个温湿度监测仪，超过阈值蜂鸣器报警，并在 OLED 上显示数据")
    print("模式: 1.beginner  2.custom")
    mode = "custom" if prompt("输入模式编号", "1") == "2" else "beginner"
    board = choose_board()
    locale = prompt("locale", "zh")
    existing = parse_existing_hardware(prompt("已有器件(逗号分隔，可留空)", ""))
    return {
        "type": "start_phase",
        "phase": "analyze",
        "session_id": str(uuid.uuid4()),
        "payload": {
            "user_description": description,
            "pre_selected_board": board,
            "preferences": {
                "mode": mode,
                "locale": locale,
            },
            "existing_hardware": existing,
        },
    }


def write_temp_start_phase(start_msg: dict[str, Any]) -> Path:
    fd, path = tempfile.mkstemp(prefix="upy_plugin_host_", suffix=".json")
    os.close(fd)
    target = Path(path)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(start_msg, f, ensure_ascii=False, indent=2)
    return target


def tee_stderr(src) -> None:
    for line in iter(src.readline, ""):
        if not line:
            break
        sys.stderr.write(f"[runner] {line}")
        sys.stderr.flush()


def render_status(payload: dict[str, Any]) -> None:
    print(f"[status] {payload.get('step_id')} | {payload.get('level')} | {payload.get('message')}")


def render_summary(summary: dict[str, Any]) -> None:
    project_name = summary.get("project_name", "")
    description = summary.get("description", "")
    board = summary.get("board", {})
    board_status = board.get("status", "none")
    board_text = "未选择"
    if board_status == "selected":
        board_text = f"{board.get('display_name')} / {board.get('mcu')}"
    print(f"项目名: {project_name}")
    print(f"功能摘要: {description}")
    print(f"板卡状态: {board_text}")


def render_items(items: list[dict[str, Any]]) -> None:
    for index, item in enumerate(items, start=1):
        default_mark = "Y" if item.get("selected") else "N"
        print(f"{index}. [{default_mark}] {item.get('name')} | {item.get('subtitle', '')} | {item.get('meta', '')}")


def choose_selected_ids(items: list[dict[str, Any]], multi_select: bool) -> list[str]:
    if not items:
        return []
    if multi_select:
        raw = prompt("输入保留项编号，逗号分隔；直接回车保留默认勾选", "")
        if not raw:
            return [item["id"] for item in items if item.get("selected")]
        ids = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                idx = int(part)
            except ValueError:
                continue
            if 1 <= idx <= len(items):
                ids.append(items[idx - 1]["id"])
        return ids
    raw = prompt("输入单个编号；直接回车选第一个", "1")
    try:
        idx = int(raw)
    except ValueError:
        idx = 1
    idx = max(1, min(idx, len(items)))
    return [items[idx - 1]["id"]]


def choose_action(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "confirm"
    print("操作:")
    for index, action in enumerate(actions, start=1):
        print(f"{index}. {action.get('label', action.get('value', ''))}")
    raw = prompt("输入操作编号", "1")
    try:
        idx = int(raw)
    except ValueError:
        idx = 1
    idx = max(1, min(idx, len(actions)))
    return actions[idx - 1].get("value", "confirm")


def prompt_added_items(allow_add: bool) -> list[dict[str, Any]]:
    if not allow_add:
        return []
    raw = prompt("新增器件(逗号分隔，留空表示不新增)", "")
    if not raw:
        return []
    result = []
    for name in [part.strip() for part in raw.split(",") if part.strip()]:
        result.append(
            {
                "name": name,
                "type": "user_added",
                "interface": "GPIO",
                "source": "user_specified",
            }
        )
    return result


def render_approval_request(payload: dict[str, Any]) -> dict[str, Any]:
    separator(f"Approval: {payload.get('approval_id')}")
    print(payload.get("header", ""))
    print(payload.get("question", ""))
    if payload.get("approval_id") == "device_confirm":
        print("提示：土壤类器件建议在此确认实现族，例如 ADC / RS485 Modbus / I2C。")
    summary = payload.get("summary", {})
    if summary:
        render_summary(summary)
    items = payload.get("items", [])
    if items:
        print("\n选项列表:")
        render_items(items)
    selected_ids = choose_selected_ids(items, payload.get("multi_select", False))
    added_items = prompt_added_items(payload.get("allow_add", False))
    action = choose_action(payload.get("actions", []))
    notes = ""
    if payload.get("approval_id") == "device_confirm":
        revise = prompt("是否在此确认点重写原始需求？留空表示不改", "")
        if revise:
            notes = f"REVISE_REQUEST::{revise}"
    return {
        "type": "approval_response",
        "payload": {
            "approval_id": payload.get("approval_id"),
            "action": action,
            "selected_ids": selected_ids,
            "added_items": added_items,
            "notes": notes,
        },
    }


def handle_script_run(payload: dict[str, Any]) -> dict[str, Any]:
    stdin_json = payload.get("stdin_json")
    stdin_content = payload.get("stdin_content")
    if stdin_json is not None:
        stdin_content = json.dumps(stdin_json, ensure_ascii=False)
    script_path = Path(payload.get("script", ""))
    if not script_path.is_absolute():
        script_path = SKILL_DIR / script_path
    proc = subprocess.run(
        [sys.executable, str(script_path), *payload.get("args", [])],
        cwd=str(SKILL_DIR),
        input=stdin_content,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result_json = None
    if proc.stdout:
        try:
            result_json = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result_json = None
    return {
        "type": "script_result",
        "payload": {
            "script_id": payload.get("script_id"),
            "success": proc.returncode == 0,
            "stdout": "" if result_json is not None else proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "result_json": result_json,
        },
    }


def render_phase_complete(payload: dict[str, Any]) -> None:
    separator("Phase Complete")
    print(f"result: {payload.get('result')}")
    print(f"summary: {payload.get('summary')}")
    print(f"next_phase: {payload.get('next_phase')}")
    print(f"next_skill: {payload.get('next_skill')}")
    warnings = payload.get("warnings", [])
    if warnings:
        print("warnings:")
        for item in warnings:
            print(f"- {item}")


def run_single_session(start_msg: dict[str, Any]) -> Optional[dict[str, Any]]:
    temp_start = write_temp_start_phase(start_msg)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    runner = subprocess.Popen(
        [sys.executable, str(TEST_DIR / "analyze_runner.py"), "--start-file", str(temp_start)],
        cwd=str(SKILL_DIR),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    stderr_thread = threading.Thread(target=tee_stderr, args=(runner.stderr,), daemon=True)
    stderr_thread.start()

    rerun_start: Optional[dict[str, Any]] = None
    try:
        for line in iter(runner.stdout.readline, ""):
            if not line:
                break
            msg = json.loads(line)
            msg_type = msg.get("type")
            payload = msg.get("payload", {})
            if msg_type == "status_update":
                render_status(payload)
                continue
            if msg_type == "approval_request":
                response = render_approval_request(payload)
                notes = response["payload"].get("notes", "")
                if notes.startswith("REVISE_REQUEST::"):
                    revised_desc = notes.split("::", 1)[1]
                    rerun_start = json.loads(json.dumps(start_msg))
                    rerun_start["session_id"] = str(uuid.uuid4())
                    rerun_start["payload"]["user_description"] = revised_desc
                    if runner.stdin:
                        runner.stdin.close()
                    runner.terminate()
                    break
                if runner.stdin:
                    runner.stdin.write(json.dumps(response, ensure_ascii=False) + "\n")
                    runner.stdin.flush()
                continue
            if msg_type == "script_run":
                result = handle_script_run(payload)
                if runner.stdin:
                    runner.stdin.write(json.dumps(result, ensure_ascii=False) + "\n")
                    runner.stdin.flush()
                continue
            if msg_type == "phase_complete":
                render_phase_complete(payload)
                break
    finally:
        try:
            runner.wait(timeout=5)
        except subprocess.TimeoutExpired:
            runner.kill()
        stderr_thread.join(timeout=1)
        try:
            temp_start.unlink(missing_ok=True)
        except Exception:
            pass
    return rerun_start


def main() -> int:
    print("upy-analyze-plugin 终端插件宿主模拟")
    current_start = build_start_phase()
    while True:
        rerun = run_single_session(current_start)
        if rerun is not None:
            print("\n检测到你在确认点修改了原始需求，将重新分析。")
            current_start = rerun
            continue
        again = prompt("是否再启动一轮新的会话？(y/n)", "n").lower()
        if again != "y":
            break
        current_start = build_start_phase()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
