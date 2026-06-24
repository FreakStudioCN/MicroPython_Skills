#!/usr/bin/env python3
"""
Interactive local simulator for upy-analyze-plugin.
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
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    if not value and default is not None:
        return default
    return value


def choose_mode() -> str:
    print("\n选择模式")
    print("1. beginner")
    print("2. custom")
    value = prompt("输入编号", "1")
    return "custom" if value == "2" else "beginner"


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
    print("\n选择预选板卡")
    print("0. 不预选板卡")
    for index, board in enumerate(boards, start=1):
        print(f"{index}. {board['display_name']} ({board['mcu']})")
    raw = prompt("输入编号或板卡名", "0").strip()
    if not raw or raw == "0":
        return None
    try:
        choice = int(raw)
    except ValueError:
        choice = None
    if choice is not None:
        if 1 <= choice <= len(boards):
            return dict(boards[choice - 1])
        return None
    lowered = raw.lower()
    for board in boards:
        if lowered in board["display_name"].lower() or lowered == board["id"].lower():
            return dict(board)
    return None


def parse_existing_hardware(raw: str) -> list[str]:
    ignored = {"无", "没有", "none", "null", "n/a", "na"}
    result = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        if value.lower() in ignored or value in ignored:
            continue
        result.append(value)
    return result


def build_start_phase() -> dict[str, Any]:
    print("\n输入本次模拟用户需求")
    description = prompt("用户需求", "做一个温湿度监测仪，超过阈值蜂鸣器报警，并在 OLED 上显示数据")
    mode = choose_mode()
    board = choose_board()
    locale = prompt("语言 locale", "zh")
    existing_raw = prompt("已有器件(用逗号分隔，可留空)", "")

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
            "existing_hardware": parse_existing_hardware(existing_raw),
        },
    }


def write_temp_start_phase(start_msg: dict[str, Any]) -> Path:
    fd, path = tempfile.mkstemp(prefix="upy_analyze_start_", suffix=".json")
    os.close(fd)
    temp_path = Path(path)
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(start_msg, f, ensure_ascii=False, indent=2)
    return temp_path


def tee_stderr(src, prefix: str) -> None:
    for line in iter(src.readline, ""):
        if not line:
            break
        sys.stderr.write(f"{prefix}{line}")
        sys.stderr.flush()


def print_status(payload: dict[str, Any]) -> None:
    print(f"\n[状态] {payload.get('step_id')} | {payload.get('level')} | {payload.get('message')}")


def pick_selected_ids(items: list[dict[str, Any]], allow_multi: bool) -> list[str]:
    if not items:
        return []

    print("\n可选项：")
    for index, item in enumerate(items, start=1):
        mark = "Y" if item.get("selected") else "N"
        print(f"{index}. [{mark}] {item.get('name')} | {item.get('subtitle', '')} | {item.get('meta', '')}")

    if allow_multi:
        raw = prompt("输入保留项编号，逗号分隔；直接回车表示保留默认勾选", "")
        if not raw:
            return [item["id"] for item in items if item.get("selected")]
        selected_ids = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                idx = int(part)
            except ValueError:
                continue
            if 1 <= idx <= len(items):
                selected_ids.append(items[idx - 1]["id"])
        return selected_ids

    raw = prompt("输入单个编号；直接回车表示选第一个推荐项", "1")
    try:
        idx = int(raw)
    except ValueError:
        idx = 1
    idx = max(1, min(idx, len(items)))
    return [items[idx - 1]["id"]]


def prompt_added_items() -> list[dict[str, Any]]:
    raw = prompt("是否新增器件？输入器件名，多个用逗号分隔；留空表示不新增", "")
    if not raw:
        return []
    added_items: list[dict[str, Any]] = []
    for name in [part.strip() for part in raw.split(",") if part.strip()]:
        added_items.append(
            {
                "name": name,
                "type": "user_added",
                "interface": "unknown",
                "source": "user_specified",
            }
        )
    return added_items


def handle_approval_request_interactive(payload: dict[str, Any]) -> dict[str, Any]:
    approval_id = payload.get("approval_id", "")
    print(f"\n[确认卡片] {payload.get('header', '')}")
    print(payload.get("question", ""))

    if approval_id == "device_confirm":
        print("提示：这里确认的是器件方案。对于土壤类器件，可在这里改成 ADC / Modbus / I2C 等实现族。")

    selected_ids = pick_selected_ids(payload.get("items", []), payload.get("multi_select", False))
    added_items = prompt_added_items() if payload.get("allow_add", False) else []
    action_value = "confirm"

    actions = payload.get("actions", [])
    if actions:
        print("\n操作：")
        for index, action in enumerate(actions, start=1):
            print(f"{index}. {action.get('label', action.get('value', ''))}")
        raw = prompt("输入操作编号", "1")
        try:
            idx = int(raw)
        except ValueError:
            idx = 1
        idx = max(1, min(idx, len(actions)))
        action_value = actions[idx - 1].get("value", "confirm")

    notes = ""
    if approval_id == "device_confirm":
        revise = prompt("是否中途修改原始需求？输入新需求，留空表示不修改", "")
        if revise:
            notes = f"REVISE_REQUEST::{revise}"

    return {
        "type": "approval_response",
        "payload": {
            "approval_id": approval_id,
            "action": action_value,
            "selected_ids": selected_ids,
            "added_items": added_items,
            "notes": notes,
        },
    }


def handle_script_run(payload: dict[str, Any]) -> dict[str, Any]:
    script_id = payload.get("script_id", "")
    interpreter = payload.get("interpreter", "python")
    script = payload.get("script", "")
    args = payload.get("args", [])
    stdin_json = payload.get("stdin_json")
    stdin_content = payload.get("stdin_content")

    if stdin_json is not None:
        stdin_content = json.dumps(stdin_json, ensure_ascii=False)

    if interpreter != "python":
        return {
            "type": "script_result",
            "payload": {
                "script_id": script_id,
                "success": False,
                "stdout": "",
                "stderr": f"unsupported interpreter: {interpreter}",
                "exit_code": 1,
                "result_json": None,
            },
        }

    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = SKILL_DIR / script_path

    proc = subprocess.run(
        [sys.executable, str(script_path), *args],
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
            "script_id": script_id,
            "success": proc.returncode == 0,
            "stdout": "" if result_json is not None else proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "result_json": result_json,
        },
    }


def print_phase_complete(payload: dict[str, Any]) -> None:
    print("\n[阶段完成]")
    print(f"result: {payload.get('result')}")
    print(f"summary: {payload.get('summary')}")
    print(f"next_phase: {payload.get('next_phase')}")
    print(f"next_skill: {payload.get('next_skill')}")
    if payload.get("warnings"):
        print("warnings:")
        for item in payload["warnings"]:
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

    stderr_thread = threading.Thread(target=tee_stderr, args=(runner.stderr, "[runner] "), daemon=True)
    stderr_thread.start()

    rerun_start_msg: Optional[dict[str, Any]] = None

    try:
        for line in iter(runner.stdout.readline, ""):
            if not line:
                break
            msg = json.loads(line)
            msg_type = msg.get("type")
            payload = msg.get("payload", {})

            if msg_type == "status_update":
                print_status(payload)
                continue

            if msg_type == "approval_request":
                response = handle_approval_request_interactive(payload)
                notes = response["payload"].get("notes", "")
                if notes.startswith("REVISE_REQUEST::"):
                    revised_desc = notes.split("::", 1)[1]
                    rerun_start_msg = json.loads(json.dumps(start_msg))
                    rerun_start_msg["session_id"] = str(uuid.uuid4())
                    rerun_start_msg["payload"]["user_description"] = revised_desc
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
                print_phase_complete(payload)
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

    return rerun_start_msg


def main() -> int:
    print("upy-analyze-plugin 交互式本地模拟")
    current_start = build_start_phase()

    while True:
        rerun = run_single_session(current_start)
        if rerun is not None:
            print("\n检测到你在确认点修改了原始需求，将按新需求重新分析。")
            current_start = rerun
            continue

        again = prompt("\n是否再模拟一轮新的用户需求？(y/n)", "n").lower()
        if again != "y":
            break
        current_start = build_start_phase()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
