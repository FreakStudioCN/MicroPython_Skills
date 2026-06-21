#!/usr/bin/env python3
"""Minimal mock plugin for upy-select-hw-plugin local tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
REPO_ROOT = SKILL_DIR.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def send(msg: dict[str, Any]) -> None:
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def handle_approval_request(payload: dict[str, Any]) -> None:
    approval_id = payload.get("approval_id")
    items = payload.get("items", [])
    selected_ids = [item["id"] for item in items if item.get("selected")]
    action = "confirm_pin_plan" if approval_id == "pin_plan_review" else "confirm"
    send(
        {
            "type": "approval_response",
            "payload": {
                "approval_id": approval_id,
                "action": action,
                "selected_ids": selected_ids,
                "notes": "",
            },
        }
    )


def handle_status_update(payload: dict[str, Any]) -> None:
    print(
        f"[STATUS] {payload.get('level', 'info')} {payload.get('step_id', '')} {payload.get('message', '')}",
        file=sys.stderr,
        flush=True,
    )


def handle_script_run(payload: dict[str, Any]) -> None:
    script_id = payload.get("script_id", "")
    interpreter = payload.get("interpreter", "python")
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

    script = payload.get("script")
    script_path = (REPO_ROOT / script).resolve()
    allowed_script = (SKILL_DIR / "scripts" / "select_hw_manifest.py").resolve()
    if script_path != allowed_script:
        send(
            {
                "type": "script_result",
                "payload": {
                    "script_id": script_id,
                    "success": False,
                    "stdout": "",
                    "stderr": f"script not whitelisted: {script}",
                    "exit_code": 1,
                },
            }
        )
        return

    stdin_json = payload.get("stdin_json")
    stdin_text = json.dumps(stdin_json, ensure_ascii=False) if stdin_json is not None else None
    proc = subprocess.run(
        [sys.executable, str(script_path), *payload.get("args", [])],
        cwd=str(REPO_ROOT),
        input=stdin_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    result_json = None
    if proc.stdout:
        try:
            result_json = json.loads(proc.stdout)
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
    runtime_context = payload.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise RuntimeError("phase_complete missing runtime_context")
    mode = runtime_context.get("artifact_root_mode", "cwd")
    session_root = runtime_context.get("session_root", "")

    file_paths: list[str] = []
    for artifact in payload.get("artifacts", []):
        if not isinstance(artifact, dict) or artifact.get("type") != "file_list":
            continue
        for item in artifact.get("files", []):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                file_paths.append(item["path"])

    required_basenames = {"pin_assignment_log.md", "select_hw_phase_log.md"}
    if mode == "cwd":
        found_basenames = {Path(p).name for p in file_paths}
        if any(Path(p).parts == (p,) for p in file_paths):
            raise RuntimeError(f"artifact_root_mode=cwd requires session-relative paths: {file_paths}")
    else:
        found_basenames = set(file_paths)

    missing = required_basenames - found_basenames
    if missing:
        raise RuntimeError(f"phase_complete missing file artifacts: {sorted(missing)}")
    print(
        f"[PHASE COMPLETE] result={payload.get('result')} next_phase={payload.get('next_phase')} files={','.join(file_paths)}",
        file=sys.stderr,
        flush=True,
    )


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
            print(f"[MOCK] ignore {msg_type}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
