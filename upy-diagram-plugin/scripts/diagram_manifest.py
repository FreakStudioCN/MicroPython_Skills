#!/usr/bin/env python3
"""Validate upy-diagram-plugin phase_complete and file manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PHASE = "upy-diagram-plugin"
REQUIRED_SUCCESS_FILES = [
    ("docs/diagram.json", "diagram_json"),
    ("docs/architecture.md", "diagram_architecture_markdown"),
    ("docs/architecture.svg", "diagram_architecture_svg"),
    ("docs/architecture.png", "diagram_architecture_png"),
    ("docs/architecture.html", "diagram_architecture_html"),
    ("docs/flowchart.md", "diagram_flowchart_markdown"),
    ("docs/flowchart.svg", "diagram_flowchart_svg"),
    ("docs/flowchart.png", "diagram_flowchart_png"),
    ("docs/flowchart.html", "diagram_flowchart_html"),
    ("docs/data_flow.md", "diagram_data_flow_markdown"),
    ("docs/data_flow.svg", "diagram_data_flow_svg"),
    ("docs/data_flow.png", "diagram_data_flow_png"),
    ("docs/data_flow.html", "diagram_data_flow_html"),
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def error(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def warning_codes(payload: dict[str, Any]) -> set[str]:
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        return set()
    codes = set()
    for item in warnings:
        if isinstance(item, dict) and isinstance(item.get("code"), str):
            codes.add(item["code"])
    return codes


def is_direct_test(payload: dict[str, Any]) -> bool:
    return (
        payload.get("mode") == "direct_test"
        or payload.get("invocation_mode") == "local_skill_test"
        or payload.get("local_test") is True
        or payload.get("source_phase") == "test_only"
    )


def manifest_file_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        normalize_rel(str(item.get("path", ""))),
        item.get("type"),
        item.get("required"),
        item.get("bytes"),
        item.get("sha256"),
    )


def validate_structured_errors(payload: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    raw_errors = payload.get("errors", [])
    if not isinstance(raw_errors, list):
        errors.append(error("ERRORS_NOT_ARRAY", "payload.errors must be an array"))
        return
    for idx, item in enumerate(raw_errors):
        if not isinstance(item, dict):
            errors.append(error("ERROR_NOT_OBJECT", f"errors[{idx}] must be an object"))
            continue
        for key in ("code", "message", "step_id", "severity"):
            if key not in item:
                errors.append(error("ERROR_FIELD_MISSING", f"errors[{idx}].{key} is required"))
        if "retryable" in item and not isinstance(item["retryable"], bool):
            errors.append(error("ERROR_RETRYABLE_TYPE", f"errors[{idx}].retryable must be boolean"))
        if "recoverable" in item and not isinstance(item["recoverable"], bool):
            errors.append(error("ERROR_RECOVERABLE_TYPE", f"errors[{idx}].recoverable must be boolean"))


def validate_file_manifest(payload: dict[str, Any], artifact_root: Path | None, errors: list[dict[str, Any]]) -> None:
    manifest = payload.get("file_manifest")
    result = payload.get("result")
    if not isinstance(manifest, dict):
        errors.append(error("FILE_MANIFEST_MISSING", "payload.file_manifest is required"))
        return
    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append(error("FILE_MANIFEST_FILES_MISSING", "payload.file_manifest.files must be an array"))
        return
    seen: set[str] = set()
    for idx, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(error("FILE_ENTRY_NOT_OBJECT", f"file_manifest.files[{idx}] must be an object"))
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            errors.append(error("FILE_ENTRY_PATH_MISSING", f"file_manifest.files[{idx}].path is required"))
            continue
        rel = normalize_rel(path)
        if rel in seen:
            errors.append(error("FILE_ENTRY_DUPLICATE", f"duplicate file_manifest path: {rel}"))
        seen.add(rel)
        for key in ("type", "required", "bytes", "sha256"):
            if key not in item:
                errors.append(error("FILE_ENTRY_FIELD_MISSING", f"{rel}: {key} is required"))
        if artifact_root is not None:
            target = artifact_root / rel
            if not target.is_file():
                errors.append(error("FILE_ENTRY_MISSING_ON_DISK", f"{rel} does not exist under artifact_root"))
                continue
            actual_size = target.stat().st_size
            if "bytes" in item and item["bytes"] != actual_size:
                errors.append(error("FILE_ENTRY_SIZE_MISMATCH", f"{rel}: expected {item['bytes']} bytes, got {actual_size}"))
            actual_hash = sha256_file(target)
            if "sha256" in item and item["sha256"] != actual_hash:
                errors.append(error("FILE_ENTRY_SHA256_MISMATCH", f"{rel}: sha256 mismatch"))
    if result == "success":
        required_paths = {path for path, _kind in REQUIRED_SUCCESS_FILES}
        missing = sorted(required_paths - seen)
        if missing:
            errors.append(error("SUCCESS_FILES_MISSING", "success result missing required files: " + ", ".join(missing)))


def validate_manifest_sidecar(payload: dict[str, Any], session_root: Path | None, errors: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    if session_root is None:
        return
    sidecar_path = session_root / "diagram_file_manifest.json"
    if not sidecar_path.exists():
        return
    if not sidecar_path.is_file():
        errors.append(error("SIDECAR_FILE_MANIFEST_INVALID", f"sidecar manifest is not a file: {sidecar_path}"))
        return
    try:
        sidecar = load_json(sidecar_path)
    except Exception as exc:
        errors.append(error("SIDECAR_FILE_MANIFEST_INVALID", f"sidecar manifest cannot be read: {exc}"))
        return
    payload_manifest = payload.get("file_manifest", {})
    payload_files = payload_manifest.get("files") if isinstance(payload_manifest, dict) else None
    sidecar_files = sidecar.get("files")
    if not isinstance(payload_files, list) or not isinstance(sidecar_files, list):
        errors.append(error("SIDECAR_FILE_MANIFEST_INVALID", "sidecar and payload file_manifest must both contain files arrays"))
        return
    payload_keys = sorted(manifest_file_key(item) for item in payload_files if isinstance(item, dict))
    sidecar_keys = sorted(manifest_file_key(item) for item in sidecar_files if isinstance(item, dict))
    if payload_keys != sidecar_keys:
        errors.append(error("SIDECAR_FILE_MANIFEST_MISMATCH", "diagram_file_manifest.json must match payload.file_manifest files by path/type/required/bytes/sha256"))


def validate_invocation_contract(payload: dict[str, Any], result: Any, errors: list[dict[str, Any]]) -> None:
    direct = is_direct_test(payload)
    manifest = payload.get("manifest_content")
    if direct:
        if result == "success":
            errors.append(error("DIRECT_TEST_SUCCESS_INVALID", "direct_test/local_skill_test/test_only must not report success"))
        if "LOCAL_TEST_ONLY" not in warning_codes(payload):
            errors.append(error("DIRECT_TEST_WARNING_MISSING", "direct_test/local_skill_test/test_only must include LOCAL_TEST_ONLY warning"))
        if isinstance(manifest, dict) and "diagrams" in manifest:
            errors.append(error("DIRECT_TEST_MANIFEST_DIAGRAMS_INVALID", "direct_test must not use formal manifest_content.diagrams"))
    if result == "success":
        if payload.get("mode") != "full":
            errors.append(error("SUCCESS_MODE_INVALID", "success requires payload.mode=full"))
        if payload.get("invocation_mode") != "plugin_protocol":
            errors.append(error("SUCCESS_INVOCATION_MODE_INVALID", "success requires payload.invocation_mode=plugin_protocol"))
        if payload.get("local_test") is True:
            errors.append(error("SUCCESS_LOCAL_TEST_INVALID", "success must not be local_test"))
        if payload.get("source_phase") != "upy-generate-plugin":
            errors.append(error("SUCCESS_SOURCE_PHASE_INVALID", "success requires source_phase=upy-generate-plugin"))
        if not payload.get("source_phase_complete_path"):
            errors.append(error("SUCCESS_SOURCE_PHASE_COMPLETE_MISSING", "success requires source_phase_complete_path"))


def validate_phase_complete(path: Path, artifact_root: Path | None, session_root: Path | None) -> dict[str, Any]:
    data = load_json(path)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if data.get("protocol_version") != "1.0":
        errors.append(error("PROTOCOL_VERSION_INVALID", "top-level protocol_version must be 1.0"))
    if data.get("type") != "phase_complete":
        errors.append(error("TYPE_INVALID", "top-level type must be phase_complete"))
    if data.get("phase") != PHASE:
        errors.append(error("PHASE_INVALID", f"top-level phase must be {PHASE}"))
    if not data.get("session_id"):
        errors.append(error("SESSION_ID_MISSING", "top-level session_id is required"))
    payload = data.get("payload")
    if not isinstance(payload, dict):
        errors.append(error("PAYLOAD_MISSING", "payload object is required"))
        return {"status": "fail", "errors": errors, "warnings": warnings}
    if payload.get("protocol_version") != "1.0":
        errors.append(error("PAYLOAD_PROTOCOL_VERSION_INVALID", "payload.protocol_version must be 1.0"))
    if payload.get("phase") != PHASE:
        errors.append(error("PAYLOAD_PHASE_INVALID", f"payload.phase must be {PHASE}"))
    if payload.get("session_id") != data.get("session_id"):
        errors.append(error("SESSION_ID_MISMATCH", "payload.session_id must match top-level session_id"))
    result = payload.get("result")
    if result not in ("success", "partial", "failed", "cancelled"):
        errors.append(error("RESULT_INVALID", "payload.result must be success, partial, failed, or cancelled"))
    if payload.get("next_phase") is not None:
        errors.append(error("NEXT_PHASE_INVALID", "diagram phase_complete must not auto-route next_phase"))
    if not payload.get("checkpoint"):
        errors.append(error("CHECKPOINT_MISSING", "payload.checkpoint is required"))
    validate_invocation_contract(payload, result, errors)
    if result == "success":
        manifest = payload.get("manifest_content")
        if not isinstance(manifest, dict):
            errors.append(error("MANIFEST_CONTENT_MISSING", "success requires payload.manifest_content"))
        elif not isinstance(manifest.get("diagrams"), dict):
            errors.append(error("DIAGRAMS_MISSING", "success manifest_content.diagrams is required"))
        checks = payload.get("checks", {})
        if not isinstance(checks, dict) or not checks.get("diagram_schema", {}).get("ok"):
            errors.append(error("SCHEMA_CHECK_MISSING", "success requires checks.diagram_schema.ok=true"))
        if not isinstance(checks, dict) or not checks.get("render_diagram", {}).get("ok"):
            errors.append(error("RENDER_CHECK_MISSING", "success requires checks.render_diagram.ok=true"))
        session_state = payload.get("session_state", {})
        if not isinstance(session_state, dict) or session_state.get("checkpoint") != "phase_completed":
            errors.append(error("SESSION_STATE_INVALID", "success requires session_state.checkpoint=phase_completed"))
    if result in ("partial", "failed", "cancelled") and "checkpoint_info" not in payload:
        errors.append(error("CHECKPOINT_INFO_MISSING", "non-success result requires checkpoint_info"))
    validate_structured_errors(payload, errors)
    validate_file_manifest(payload, artifact_root, errors)
    validate_manifest_sidecar(payload, session_root, errors, warnings)
    if session_root is not None and not session_root.exists():
        warnings.append(error("SESSION_ROOT_MISSING", f"session_root does not exist: {session_root}"))
    return {
        "status": "ok" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
    }


def build_file_manifest(artifact_root: Path, output: Path | None) -> dict[str, Any]:
    files = []
    for rel, kind in REQUIRED_SUCCESS_FILES:
        path = artifact_root / rel
        if path.is_file():
            files.append({
                "path": rel,
                "type": kind,
                "required": True,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "source": "diagram_manifest.py",
            })
    result = {"files": files}
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or build upy-diagram-plugin manifests")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-phase-complete", action="store_true")
    mode.add_argument("--build-file-manifest", action="store_true")
    parser.add_argument("--input", help="phase_complete JSON path")
    parser.add_argument("--artifact-root", help="project artifact root")
    parser.add_argument("--session-root", help="session root")
    parser.add_argument("--output", help="output path for --build-file-manifest")
    args = parser.parse_args()

    try:
        artifact_root = Path(args.artifact_root) if args.artifact_root else None
        session_root = Path(args.session_root) if args.session_root else None
        if args.validate_phase_complete:
            if not args.input:
                raise ValueError("--input is required for --validate-phase-complete")
            result = validate_phase_complete(Path(args.input), artifact_root, session_root)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if result["status"] == "ok" else 1
        if args.build_file_manifest:
            if artifact_root is None:
                raise ValueError("--artifact-root is required for --build-file-manifest")
            result = build_file_manifest(artifact_root, Path(args.output) if args.output else None)
            print(json.dumps({"status": "ok", "file_manifest": result}, ensure_ascii=False, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "errors": [error("DIAGRAM_MANIFEST_ERROR", str(exc))]}, ensure_ascii=False, sort_keys=True))
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
