#!/usr/bin/env python3
"""Validate upy-flash-mpy-firmware-plugin protocol artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


PHASE = "upy-flash-mpy-firmware-plugin"
NEXT_PHASE = "upy-scaffold-plugin"
UPSTREAM_PHASE = "select-hw"
ARTIFACT_ROOT_MODES = {"cwd", "session_root"}
RESUME_STEPS = {
    "load_upstream_select_hw",
    "select_firmware_action",
    "resolve_firmware_page",
    "download_firmware",
    "scan_serial_ports",
    "confirm_esp32_flash",
    "run_esp32_flash",
    "wait_pico_uf2_copy",
    "manual_firmware_flash_confirm",
    "phase_complete_validation",
}
STATE_STATUSES = {"in_progress", "partial", "success", "failed", "cancelled"}
LEGACY_TOP_LEVEL_STATE_DETAIL_FIELDS = {
    "firmware_action",
    "board_name",
    "board_url",
    "firmware_url",
    "firmware_file",
    "serial_port",
    "chip",
    "flash_result",
}


def load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def is_relative(path: str) -> bool:
    return path and not os.path.isabs(path) and ".." not in Path(path).parts


def is_under_session_root(rel_path: str, session_root: str) -> bool:
    parts = Path(rel_path).parts
    session_parts = Path(session_root).parts
    return len(parts) > len(session_parts) and tuple(parts[: len(session_parts)]) == tuple(session_parts)


def path_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def normalize_rel(path: str) -> str:
    return Path(path).as_posix()


def looks_like_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def require_declared(
    path: str | None,
    declared: set[str],
    errors: list[str],
    field: str,
    *,
    required_on_disk: bool = True,
) -> None:
    if not path:
        return
    if looks_like_url(path):
        errors.append(f"{field} must be an artifact path, not URL: {path}")
        return
    if not is_relative(path):
        errors.append(f"{field} must be a relative artifact path: {path}")
        return
    normalized = normalize_rel(path)
    if normalized not in declared and path not in declared:
        errors.append(f"{field} must be declared in payload.artifacts: {path}")
    if required_on_disk and Path(path).is_absolute():
        errors.append(f"{field} must not be absolute: {path}")


def artifact_shape_hint(artifact: Any, index: int, errors: list[str]) -> None:
    if not isinstance(artifact, dict):
        errors.append(f"payload.artifacts[{index}] must be an object with type='file_list' and files[]")
        return
    if "path" in artifact:
        errors.append(
            "payload.artifacts must contain file_list groups; "
            f"payload.artifacts[{index}] looks like a flat file entry and must move under files[]"
        )
        return
    if artifact.get("type") != "file_list":
        errors.append(f"payload.artifacts[{index}].type must be file_list")
        return
    if not isinstance(artifact.get("files"), list):
        errors.append(f"payload.artifacts[{index}].files must be an array")


def validate_envelope(data: dict[str, Any], errors: list[str]) -> None:
    for field in ("protocol_version", "session_id", "phase", "type", "payload"):
        if field not in data:
            errors.append(f"missing envelope field {field}")
    if data.get("protocol_version") != "1.0":
        errors.append("protocol_version must be 1.0")


def validate_runtime_context(value: Any, errors: list[str], session_id: str | None, prefix: str) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return None
    mode = value.get("artifact_root_mode")
    if mode not in ARTIFACT_ROOT_MODES:
        errors.append(f"{prefix}.artifact_root_mode must be cwd or session_root")
    artifact_root = value.get("artifact_root")
    if not isinstance(artifact_root, str) or not artifact_root:
        errors.append(f"{prefix}.artifact_root is required")
    session_root = value.get("session_root")
    if not isinstance(session_root, str) or not session_root:
        errors.append(f"{prefix}.session_root is required")
    elif not is_relative(session_root):
        errors.append(f"{prefix}.session_root must be relative")
    elif mode == "cwd" and session_id:
        expected = f"sessions/{session_id}"
        if session_root != expected:
            errors.append(f"{prefix}.session_root must be {expected} when artifact_root_mode=cwd")
    resource_root = value.get("resource_root")
    if not isinstance(resource_root, str) or not resource_root:
        errors.append(f"{prefix}.resource_root is required")
    return value


def validate_start(data: dict[str, Any], errors: list[str]) -> None:
    validate_envelope(data, errors)
    if data.get("phase") != PHASE:
        errors.append(f"phase must be {PHASE}")
    if data.get("type") != "start_phase":
        errors.append("type must be start_phase")
    payload = data.get("payload") or {}
    if payload.get("phase") != PHASE:
        errors.append(f"payload.phase must be {PHASE}")
    if not payload.get("source_phase_complete_path") and not payload.get("source_phase_complete"):
        errors.append("payload must include source_phase_complete_path or source_phase_complete")
    validate_runtime_context(payload.get("runtime_context"), errors, data.get("session_id"), "runtime_context")


def board_facts_from_upstream(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.get("payload") or {}
    manifest = payload.get("manifest_content") or {}
    selected = ((manifest.get("hardware_selection") or {}).get("selected_board") or {})
    firmware = selected.get("firmware") or {}
    mcu = manifest.get("mcu") or {}
    board_name = firmware.get("board_name") or mcu.get("firmware_board_name")
    board_url = firmware.get("url") or mcu.get("firmware_url")
    port = firmware.get("port")
    chip_family = selected.get("chip_family") or mcu.get("chip_family")
    display_name = selected.get("display_name") or mcu.get("display_name")
    flash_tool = mcu.get("flash_tool")
    if str(board_name or "").upper().startswith("ESP32_") or port == "esp32" or str(chip_family or "").lower().startswith("esp32"):
        family = "esp32"
    elif str(board_name or "").upper().startswith("RPI_PICO"):
        family = "pico"
    else:
        family = "manual"
    return {
        "board_name": board_name,
        "board_url": board_url,
        "port": port,
        "chip_family": chip_family,
        "display_name": display_name,
        "flash_tool": flash_tool,
        "family": family,
    }


def validate_upstream(data: dict[str, Any], errors: list[str], allow_legacy: bool = False) -> dict[str, Any]:
    validate_envelope(data, errors)
    if data.get("phase") != UPSTREAM_PHASE or data.get("type") != "phase_complete":
        errors.append("upstream must be phase_complete(select-hw)")
    payload = data.get("payload") or {}
    if payload.get("result") != "success":
        errors.append("upstream payload.result must be success")
    valid_next = {PHASE}
    if allow_legacy:
        valid_next.add("flash-mpy-firmware")
    if payload.get("next_phase") not in valid_next:
        errors.append(f"upstream payload.next_phase must be {PHASE}")
    manifest = payload.get("manifest_content") or {}
    if manifest.get("phase") != "select-hw":
        errors.append("upstream manifest_content.phase must be select-hw")
    facts = board_facts_from_upstream(data)
    if not facts.get("board_name"):
        errors.append("upstream firmware board_name is required")
    return facts


def validate_state(data: dict[str, Any], errors: list[str]) -> None:
    for field in ("protocol_version", "session_id", "phase", "status", "source_phase_complete_path"):
        if field not in data:
            errors.append(f"missing state field {field}")
    if data.get("protocol_version") != "1.0":
        errors.append("state protocol_version must be 1.0")
    if data.get("phase") != PHASE:
        errors.append(f"state phase must be {PHASE}")
    status = data.get("status")
    if status == "phase_complete":
        errors.append('state status "phase_complete" is invalid; use status "success" and write type "phase_complete" only in the final phase_complete message')
    elif status not in STATE_STATUSES:
        errors.append("state status must be in_progress, partial, success, failed, or cancelled")
    if data.get("type") not in {None, "state"}:
        errors.append("state type must be state when present")
    source = data.get("source_phase_complete_path")
    if not isinstance(source, str) or not is_relative(source):
        errors.append("state source_phase_complete_path must be a relative path")
    legacy_fields = sorted(field for field in LEGACY_TOP_LEVEL_STATE_DETAIL_FIELDS if field in data)
    if legacy_fields:
        errors.append(f"state detail fields should be under payload, not top-level: {', '.join(legacy_fields)}")
    payload = data.get("payload")
    if payload is not None and not isinstance(payload, dict):
        errors.append("state payload must be an object")
    checkpoint = data.get("checkpoint")
    if checkpoint is not None:
        if not isinstance(checkpoint, dict):
            errors.append("state checkpoint must be an object")
        else:
            resume_step = checkpoint.get("resume_step")
            if resume_step not in RESUME_STEPS:
                errors.append(f"state checkpoint.resume_step invalid: {resume_step}")
            if not checkpoint.get("reason"):
                errors.append("state checkpoint.reason is required")
    for field in ("firmware", "approvals", "scripts"):
        if field in data and not isinstance(data[field], dict):
            errors.append(f"state {field} must be an object")


def validate_success_manifest_content(payload: dict[str, Any], firmware: dict[str, Any], errors: list[str]) -> None:
    manifest = payload.get("manifest_content")
    if not isinstance(manifest, dict):
        errors.append("success payload.manifest_content must be an object")
        return
    if manifest.get("phase") != PHASE:
        errors.append(f"payload.manifest_content.phase must be {PHASE}")
    if manifest.get("final_status") != "firmware_ready":
        errors.append('payload.manifest_content.final_status must be "firmware_ready"')
    if not manifest.get("updated_at"):
        errors.append("payload.manifest_content.updated_at is required")
    upstream_fields = ("project_name", "requirements", "devices", "mcu", "hardware_selection")
    for field in upstream_fields:
        if field not in manifest:
            errors.append(f"payload.manifest_content.{field} missing")
    flash = manifest.get("firmware_flash")
    if not isinstance(flash, dict):
        errors.append("payload.manifest_content.firmware_flash must be an object")
        return
    for field in ("status", "action", "board_name", "board_url", "latest_url", "file", "file_type", "source", "flash_method"):
        if field in firmware and firmware.get(field) is not None and flash.get(field) != firmware.get(field):
            errors.append(f"payload.manifest_content.firmware_flash.{field} must match payload.firmware.{field}")
    for field in ("latest_version", "latest_date"):
        if firmware.get("source") == "micropython_latest":
            if not firmware.get(field):
                errors.append(f"payload.firmware.{field} is required for micropython_latest success")
            if flash.get(field) != firmware.get(field):
                errors.append(f"payload.manifest_content.firmware_flash.{field} must match payload.firmware.{field}")
    firmware_flash_result = firmware.get("flash_result")
    if isinstance(firmware_flash_result, dict):
        manifest_flash_result = flash.get("flash_result")
        if not isinstance(manifest_flash_result, dict):
            errors.append("payload.manifest_content.firmware_flash.flash_result must be an object")
        elif manifest_flash_result != firmware_flash_result:
            errors.append("payload.manifest_content.firmware_flash.flash_result must match payload.firmware.flash_result")
        if firmware.get("flash_method") == "esptool.py":
            for field in ("baud", "chip", "write_offset"):
                if not firmware_flash_result.get(field):
                    errors.append(f"payload.firmware.flash_result.{field} is required for ESP32 success")


def validate_phase_complete(data: dict[str, Any], errors: list[str], artifact_root: str | None, expected: list[str]) -> None:
    validate_envelope(data, errors)
    if data.get("phase") != PHASE:
        errors.append(f"phase must be {PHASE}")
    if data.get("type") != "phase_complete":
        errors.append("type must be phase_complete")
    payload = data.get("payload") or {}
    result = payload.get("result")
    if payload.get("phase") != PHASE:
        errors.append(f"payload.phase must be {PHASE}")
    if result == "success":
        if payload.get("source_phase") != UPSTREAM_PHASE:
            errors.append(f"success payload.source_phase must be {UPSTREAM_PHASE}")
        source_path = payload.get("source_phase_complete_path")
        if not isinstance(source_path, str) or not is_relative(source_path):
            errors.append("success payload.source_phase_complete_path must be a relative path")
    runtime_context = validate_runtime_context(
        payload.get("runtime_context"),
        errors,
        data.get("session_id"),
        "runtime_context",
    )
    firmware = payload.get("firmware") or {}
    if result == "success":
        if payload.get("next_phase") != NEXT_PHASE:
            errors.append(f"success payload.next_phase must be {NEXT_PHASE}")
        for field in ("status", "action", "board_name", "board_url", "source", "flash_method"):
            if field not in firmware:
                errors.append(f"firmware.{field} missing")
        validate_success_manifest_content(payload, firmware, errors)
    elif result in {"partial", "failed"}:
        if payload.get("next_phase") is not None:
            errors.append("partial/failed payload.next_phase must be null")
    else:
        errors.append("payload.result must be success, partial, or failed")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        if isinstance(artifacts, dict) and "file_list" in artifacts:
            errors.append(
                "payload.artifacts must be an array of file_list objects, "
                "not an object like {'file_list': [...]}"
            )
        else:
            errors.append("payload.artifacts must be an array")
        artifacts = []
    declared = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict) or artifact.get("type") != "file_list" or not isinstance(artifact.get("files"), list):
            artifact_shape_hint(artifact, index, errors)
            continue
        for item in artifact["files"]:
            if not isinstance(item, dict):
                errors.append(f"payload.artifacts[{index}].files[] must contain objects")
                continue
            path = item.get("path")
            if not is_relative(path):
                errors.append(f"artifact path must be relative: {path}")
            elif runtime_context:
                mode = runtime_context.get("artifact_root_mode")
                session_root = runtime_context.get("session_root")
                if mode == "cwd" and isinstance(session_root, str) and not is_under_session_root(path, session_root):
                    errors.append(f"artifact path must be under {session_root}/ when artifact_root_mode=cwd: {path}")
                if mode == "session_root" and len(Path(path).parts) != 1:
                    errors.append(f"artifact path must be a bare filename when artifact_root_mode=session_root: {path}")
            declared.add(path)
            declared.add(normalize_rel(path))
            if artifact_root and path and not (Path(artifact_root) / path).exists():
                errors.append(f"artifact path missing on disk: {path}")
    for item in expected:
        if item not in declared:
            errors.append(f"expected artifact not declared: {item}")
    if not firmware:
        errors.append("payload.firmware must be an object")
        return
    require_declared(path_value(firmware.get("file")), declared, errors, "firmware.file")
    flash_result = firmware.get("flash_result")
    if isinstance(flash_result, dict):
        require_declared(path_value(flash_result.get("log")), declared, errors, "firmware.flash_result.log")
    checkpoint = payload.get("checkpoint")
    if result in {"partial", "failed"}:
        if not isinstance(checkpoint, dict):
            errors.append("partial/failed payload.checkpoint must be an object")
        else:
            resume_step = checkpoint.get("resume_step")
            if resume_step not in RESUME_STEPS:
                errors.append(f"payload.checkpoint.resume_step invalid: {resume_step}")
            require_declared(path_value(checkpoint.get("state_file")), declared, errors, "payload.checkpoint.state_file")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-start-phase", action="store_true")
    mode.add_argument("--validate-upstream", action="store_true")
    mode.add_argument("--validate-state", action="store_true")
    mode.add_argument("--validate-phase-complete", action="store_true")
    parser.add_argument("--input", required=True)
    parser.add_argument("--artifact-root")
    parser.add_argument("--expected-artifact", action="append", default=[])
    parser.add_argument("--allow-legacy-next-phase", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    data = load(args.input)
    errors: list[str] = []
    extra: dict[str, Any] = {}
    if args.validate_start_phase:
        validate_start(data, errors)
    elif args.validate_upstream:
        extra["board_facts"] = validate_upstream(data, errors, args.allow_legacy_next_phase)
    elif args.validate_state:
        validate_state(data, errors)
    else:
        validate_phase_complete(data, errors, args.artifact_root, args.expected_artifact)
    result = {"status": "ok" if not errors else "failed", "errors": errors, **extra}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
