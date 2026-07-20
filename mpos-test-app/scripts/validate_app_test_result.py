#!/usr/bin/env python3
"""Validate an mpos-test-app app_test_result JSON file."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def validate(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}")

    require(isinstance(data, dict), "top-level JSON must be an object")
    require(data.get("schema_version") == "mpos-test-app-v1", "schema_version must be mpos-test-app-v1")
    require(data.get("phase") == "test-app", "phase must be test-app")
    require(data.get("result") in {"success", "partial", "failed", "blocked"}, "result must be success, partial, failed, or blocked")

    app = data.get("app")
    require(isinstance(app, dict), "app must be an object")
    fullname = app.get("fullname")
    require(isinstance(fullname, str) and fullname, "app.fullname is required")
    app_dir = app.get("app_dir")
    require(isinstance(app_dir, str) and app_dir.endswith(fullname), "app.app_dir must end with app.fullname")

    checks = data.get("checks")
    require(isinstance(checks, list), "checks must be a list")
    by_name = {}
    for index, check in enumerate(checks):
        require(isinstance(check, dict), f"checks[{index}] must be an object")
        name = check.get("name")
        require(isinstance(name, str) and name, f"checks[{index}].name is required")
        by_name[name] = check
        require(isinstance(check.get("ok"), bool), f"{name}: ok must be boolean")
        if data["result"] == "success" and check.get("required", True):
            require(check["ok"] is True, f"{name}: required check must pass for success")

    for required_name in ("generation_result_static_gates", "desktop_runner_launch", "desktop_smoke"):
        require(required_name in by_name, f"missing required check: {required_name}")
    if "web_port" in by_name:
        require(by_name["web_port"].get("required") is False, "web_port must remain an optional check with required=false")

    artifacts = data.get("artifacts", [])
    require(isinstance(artifacts, list), "artifacts must be a list")
    for index, artifact in enumerate(artifacts):
        require(isinstance(artifact, dict), f"artifacts[{index}] must be an object")
        kind = artifact.get("kind")
        require(bool(kind), f"artifacts[{index}].kind is required")
        path_value = artifact.get("path")
        require(isinstance(path_value, str) and path_value, f"artifacts[{index}].path is required")
        require("__pycache__" not in path_value and not path_value.endswith(".pyc"), "artifacts must not include Python cache files")
        if kind == "screenshot":
            require(artifact.get("format") == "png", f"artifacts[{index}] publish screenshot must be PNG")
            require(artifact.get("publish_ready") is True, f"artifacts[{index}] publish screenshot must be publish_ready=true")

    manual_commands = data.get("manual_preview_commands")
    require(isinstance(manual_commands, dict), "manual_preview_commands must be an object")
    for key in ("release_elf_desktop", "local_build_desktop", "web_port_optional"):
        commands = manual_commands.get(key)
        require(isinstance(commands, list) and commands, f"manual_preview_commands.{key} must be a non-empty list")
        for index, command in enumerate(commands):
            require(isinstance(command, str) and command, f"manual_preview_commands.{key}[{index}] must be a string")

    handoff = data.get("handoff")
    require(isinstance(handoff, dict), "handoff must be an object")
    next_skill = handoff.get("next_skill")
    require(next_skill in {None, "mpos-gen-app"}, "handoff.next_skill must be null or mpos-gen-app")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_app_test_result.py <app_test_result.json>", file=sys.stderr)
        return 2
    validate(Path(argv[1]))
    print("App test result is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
