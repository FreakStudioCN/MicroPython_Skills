#!/usr/bin/env python3
"""Validate mpos-plan-app plan_state.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mpos-plan-app-v1"
RESULTS = {"planned", "success", "partial", "failed", "blocked"}
ARTIFACT_KEYS = {
    "analysis_result",
    "dependency_handoff",
    "generation_result",
    "app_test_result",
    "package_result",
    "deploy_result",
    "publish_result",
}
NEXT_SKILLS = {
    None,
    "mpos-analyze-app",
    "mpos-prepare-deps",
    "mpos-gen-app",
    "mpos-test-app",
    "mpos-package-app",
    "mpos-deploy-app",
    "mpos-publish-app",
    "mpos-plan-app",
}


def load_json(path: str | None) -> Any:
    if path == "-" or path is None:
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def require_object(value: Any, name: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return {}
    return value


def require_array(value: Any, name: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{name} must be an array")
        return []
    return value


def check_string(value: Any, name: str, errors: list[str], *, allow_empty: bool = False) -> None:
    if not isinstance(value, str):
        errors.append(f"{name} must be a string")
        return
    if not allow_empty and not value.strip():
        errors.append(f"{name} must not be empty")


def validate(root: Any) -> list[str]:
    errors: list[str] = []
    obj = require_object(root, "root", errors)
    if not obj:
        return errors
    if obj.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    check_string(obj.get("phase"), "phase", errors)
    if obj.get("result") not in RESULTS:
        errors.append(f"result must be one of {sorted(RESULTS)}")
    check_string(obj.get("updated_at_utc"), "updated_at_utc", errors)

    app = require_object(obj.get("app"), "app", errors)
    for key in ("fullname", "name", "version", "app_dir"):
        check_string(app.get(key), f"app.{key}", errors)

    intent = require_object(obj.get("intent"), "intent", errors)
    check_string(intent.get("goal"), "intent.goal", errors)
    if not isinstance(intent.get("publish"), bool):
        errors.append("intent.publish must be boolean")
    if not isinstance(intent.get("deploy_record_required"), bool):
        errors.append("intent.deploy_record_required must be boolean")
    check_string(intent.get("deploy_record_policy"), "intent.deploy_record_policy", errors)

    artifacts = require_object(obj.get("artifacts"), "artifacts", errors)
    missing_keys = sorted(ARTIFACT_KEYS - set(artifacts))
    if missing_keys:
        errors.append("artifacts missing keys: " + ", ".join(missing_keys))
    for key, value in artifacts.items():
        if key not in ARTIFACT_KEYS:
            errors.append(f"artifacts.{key} is not a known artifact key")
        if value is not None and not isinstance(value, str):
            errors.append(f"artifacts.{key} must be string or null")

    require_object(obj.get("artifact_status", {}), "artifact_status", errors)
    require_array(obj.get("invalidated", []), "invalidated", errors)
    require_array(obj.get("pending_confirmations", []), "pending_confirmations", errors)
    require_array(obj.get("blocking_questions", []), "blocking_questions", errors)
    require_object(obj.get("last_event"), "last_event", errors)
    if obj.get("next_skill") not in NEXT_SKILLS:
        errors.append("next_skill must be null or a known mpos skill")
    handoff = require_object(obj.get("handoff"), "handoff", errors)
    if handoff.get("next_skill") not in NEXT_SKILLS:
        errors.append("handoff.next_skill must be null or a known mpos skill")
    if handoff.get("reason") is not None:
        check_string(handoff.get("reason"), "handoff.reason", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", nargs="?", default="-", help="plan_state.json path, or '-' for stdin")
    parser.add_argument("--quiet", action="store_true", help="Only print errors")
    args = parser.parse_args()
    try:
        data = load_json(args.json_path)
    except Exception as exc:  # noqa: BLE001 - CLI should report parse/read failures.
        print(f"ERROR: failed to read JSON: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if not args.quiet:
        source = "stdin" if args.json_path == "-" else str(Path(args.json_path))
        print(f"OK: {source} is a valid {SCHEMA_VERSION} plan state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
