#!/usr/bin/env python3
"""
upy-analyze-plugin 的最小 mock 插件。

用途：
- 模拟插件侧对 analyze 消息的响应
- 不依赖真实 VS Code 插件
- 用于本机先验证协议链是否顺畅

当前支持：
- approval_request
- status_update
- script_run
- phase_complete
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
PROJECT_DIR = SKILL_DIR


def sanitize_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [sanitize_text(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_text(val) for key, val in value.items()}
    return value


def send(msg: dict[str, Any]) -> None:
    clean_msg = sanitize_text(msg)
    print(json.dumps(clean_msg, ensure_ascii=False), flush=True)


def handle_approval_request(payload: dict[str, Any]) -> None:
    approval_id = payload.get("approval_id", "")
    items = payload.get("items", [])

    if approval_id == "alternative_device":
        selected_ids = [items[0]["id"]] if items else []
        action = "accept_alt1"
    else:
        selected_ids = [item["id"] for item in items if item.get("selected")]
        action = "confirm"

    send(
        {
            "type": "approval_response",
            "payload": {
                "approval_id": approval_id,
                "action": action,
                "selected_ids": selected_ids,
                "added_items": [],
                "notes": "",
            },
        }
    )


def handle_status_update(payload: dict[str, Any]) -> None:
    level = payload.get("level", "info")
    message = payload.get("message", "")
    step_id = payload.get("step_id", "")
    print(f"[STATUS] {level} {step_id} {message}", file=sys.stderr, flush=True)


def handle_script_run(payload: dict[str, Any]) -> None:
    script_id = payload.get("script_id", "")
    interpreter = payload.get("interpreter", "python")
    script = payload.get("script", "")
    args = payload.get("args", [])
    stdin_content = payload.get("stdin_content", None)
    stdin_json = payload.get("stdin_json", None)

    if stdin_json is not None:
        stdin_content = json.dumps(sanitize_text(stdin_json), ensure_ascii=False)

    if stdin_content is not None:
        stdin_content = sanitize_text(stdin_content)

    if interpreter != "python":
        send(
            {
                "type": "script_result",
                "payload": {
                    "script_id": script_id,
                    "success": False,
                    "stdout": "",
                    "stderr": f"unsupported interpreter: {interpreter}",
                    "exit_code": 1,
                },
            }
        )
        return

    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = PROJECT_DIR / script_path

    cmd = [sys.executable, str(script_path), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_DIR),
        input=stdin_content,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    result_json = None
    stdout_text = proc.stdout
    if stdout_text:
        try:
            result_json = json.loads(stdout_text)
        except json.JSONDecodeError:
            result_json = None

    send(
        {
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
    )


def handle_phase_complete(payload: dict[str, Any]) -> None:
    result = payload.get("result")
    summary = payload.get("summary", "")
    next_phase = payload.get("next_phase")
    next_skill = payload.get("next_skill")
    print(
        f"[PHASE COMPLETE] result={result} next_phase={next_phase} next_skill={next_skill}",
        file=sys.stderr,
        flush=True,
    )
    print(f"[SUMMARY] {summary}", file=sys.stderr, flush=True)


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        msg = json.loads(line)
        msg_type = msg.get("type")
        payload = msg.get("payload", {})

        if msg_type == "approval_request":
            handle_approval_request(payload)
        elif msg_type == "status_update":
            handle_status_update(payload)
        elif msg_type == "script_run":
            handle_script_run(payload)
        elif msg_type == "phase_complete":
            handle_phase_complete(payload)
        else:
            print(f"[MOCK] ignore unsupported message type: {msg_type}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
