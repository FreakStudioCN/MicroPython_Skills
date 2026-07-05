#!/usr/bin/env python3
"""Validate upy-gen-driver-plugin phase_complete artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


PHASE = "upy-gen-driver-plugin"
DOMAIN_PHASE = "gen-driver"
RESULTS = {"success", "partial", "failed"}


def is_relative_path(value: str) -> bool:
    if not value or os.path.isabs(value):
        return False
    parts = Path(value).parts
    return ".." not in parts and not (len(value) > 1 and value[1] == ":")


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("phase_complete must be a JSON object")
    return data


def validate(data: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for field in ("protocol_version", "msg_id", "session_id", "phase", "timestamp", "type", "payload"):
        if field not in data:
            errors.append(f"missing envelope field {field}")
    if data.get("protocol_version") != "1.0":
        errors.append("protocol_version must be 1.0")
    if data.get("phase") != PHASE:
        errors.append(f"phase must be {PHASE}")
    if data.get("type") != "phase_complete":
        errors.append("type must be phase_complete")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        return False, errors
    if payload.get("phase") != DOMAIN_PHASE:
        errors.append(f"payload.phase must be {DOMAIN_PHASE}")
    if payload.get("domain_phase") != DOMAIN_PHASE:
        errors.append(f"payload.domain_phase must be {DOMAIN_PHASE}")
    if payload.get("result") not in RESULTS:
        errors.append("payload.result must be success, partial, or failed")
    if not payload.get("summary"):
        errors.append("payload.summary is required")
    runtime = payload.get("runtime_context")
    if not isinstance(runtime, dict):
        errors.append("payload.runtime_context must be an object")
    else:
        for field in ("artifact_root", "session_root", "resource_root"):
            if not runtime.get(field):
                errors.append(f"payload.runtime_context.{field} is required")
        for field in ("session_root", "project_root", "file_operation_root"):
            value = runtime.get(field)
            if value and not is_relative_path(str(value)):
                errors.append(f"payload.runtime_context.{field} must be relative: {value}")
    checkpoint = payload.get("checkpoint")
    if not isinstance(checkpoint, dict):
        errors.append("payload.checkpoint must be an object")
    else:
        for field in ("checkpoint_id", "resume_phase", "resume_step"):
            if not checkpoint.get(field):
                errors.append(f"payload.checkpoint.{field} is required")
        if checkpoint.get("resume_phase") != PHASE:
            errors.append(f"payload.checkpoint.resume_phase must be {PHASE}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("payload.artifacts must be an array")
    elif not any(isinstance(item, dict) and item.get("type") == "file_list" for item in artifacts):
        errors.append("payload.artifacts must include a file_list artifact")
    file_manifest = payload.get("file_manifest")
    if not isinstance(file_manifest, dict):
        errors.append("payload.file_manifest must be an object")
    else:
        files = file_manifest.get("files")
        if not isinstance(files, list):
            errors.append("payload.file_manifest.files must be an array")
        else:
            for index, item in enumerate(files):
                if not isinstance(item, dict):
                    errors.append(f"file_manifest.files[{index}] must be an object")
                    continue
                path = item.get("path")
                if not isinstance(path, str) or not is_relative_path(path):
                    errors.append(f"file_manifest.files[{index}].path must be relative")
                if not item.get("role"):
                    errors.append(f"file_manifest.files[{index}].role is required")
    structured = payload.get("structured_errors")
    if not isinstance(structured, list):
        errors.append("payload.structured_errors must be an array")
    else:
        for index, item in enumerate(structured):
            if not isinstance(item, dict):
                errors.append(f"structured_errors[{index}] must be an object")
                continue
            for field in ("code", "severity", "phase_step", "retryable", "message", "details", "next_action"):
                if field not in item:
                    errors.append(f"structured_errors[{index}].{field} is required")
    if payload.get("result") == "success" and structured:
        errors.append("success must not contain structured_errors")
    if payload.get("result") in {"partial", "failed"} and not structured:
        errors.append("partial/failed must include structured_errors")
    permissions = payload.get("permissions")
    if permissions is not None and not isinstance(permissions, list):
        errors.append("payload.permissions must be an array")
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        data = load(Path(args.input))
        ok, errors = validate(data)
    except Exception as exc:
        ok, errors = False, [str(exc)]
    print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
