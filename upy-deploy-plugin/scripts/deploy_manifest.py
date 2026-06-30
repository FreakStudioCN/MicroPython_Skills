#!/usr/bin/env python3
"""Validate upy-deploy-plugin start, state, and phase_complete JSON files."""

from __future__ import annotations

import argparse
from typing import Any

from common import configure_stdio, get_manifest, get_payload, load_json, print_json


PHASE = "upy-deploy-plugin"
UPSTREAM_PHASE = "upy-generate-plugin"
SUCCESS_REQUIRED_ARTIFACT_BASENAMES = {
    "deploy_result.json",
    "upload_summary.json",
    "clean_result.json",
    "mip_install_result.json",
    "device_tests_result.json",
}
SUCCESS_REQUIRED_ARTIFACT_KEYWORDS = {
    "serial": ("serial", "repl", "capture"),
    "log": ("log", "device_log", "log_report"),
}


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def validate_start(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    payload = get_payload(data)
    require(data.get("type") == "start_phase", errors, "type must be start_phase")
    require(data.get("phase") == PHASE or payload.get("phase") == PHASE, errors, f"phase must be {PHASE}")
    runtime = payload.get("runtime_context")
    require(isinstance(runtime, dict), errors, "payload.runtime_context object is required")
    if isinstance(runtime, dict):
        for field in ("session_root", "project_root", "resource_root"):
            require(bool(runtime.get(field)), errors, f"runtime_context.{field} is required")
    capabilities = payload.get("capabilities", {})
    for field in ("approval_request", "script_run", "file_operation"):
        require(capabilities.get(field) is True, errors, f"capabilities.{field}=true is required")
    source = payload.get("source_phase_complete")
    source_path = payload.get("source_phase_complete_path")
    require(isinstance(source, dict) or bool(source_path), errors, "source_phase_complete or source_phase_complete_path is required")
    strategy = payload.get("deploy_strategy", "upload_only")
    require(strategy in {"upload_only", "clean_then_upload", "erase_then_upload"}, errors, "deploy_strategy is invalid")
    return {"status": "ok" if not errors else "failed", "errors": errors}


def validate_upstream(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    payload = get_payload(data)
    require(data.get("type") == "phase_complete", errors, "upstream type must be phase_complete")
    require(payload.get("result") == "success", errors, "upstream result must be success")
    require(payload.get("next_phase") == PHASE, errors, f"upstream next_phase must be {PHASE}")
    manifest = get_manifest(data)
    require(bool(manifest), errors, "upstream manifest_content is required")
    require(manifest.get("phase") == "generate", errors, "upstream manifest_content.phase must be generate")
    for field in ("requirements", "devices", "mcu", "generate"):
        require(field in manifest, errors, f"manifest_content.{field} is required")
    return {"status": "ok" if not errors else "failed", "errors": errors}


def validate_phase_complete(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    payload = get_payload(data)
    require(data.get("type") == "phase_complete", errors, "type must be phase_complete")
    require(data.get("phase") == PHASE or payload.get("phase") == PHASE, errors, f"phase must be {PHASE}")
    require(payload.get("phase") == PHASE, errors, f"payload.phase must be {PHASE}")
    require(payload.get("result") in {"success", "failed", "partial"}, errors, "payload.result is invalid")
    manifest = payload.get("manifest_content")
    if payload.get("result") == "success":
        require(isinstance(manifest, dict), errors, "success payload.manifest_content is required")
        if isinstance(manifest, dict):
            require(manifest.get("phase") == PHASE, errors, f"manifest_content.phase must be {PHASE}")
            require(manifest.get("deploy") or manifest.get("deploy_result"), errors, "manifest_content.deploy or deploy_result is required")
    artifacts = payload.get("artifacts")
    require(isinstance(artifacts, list), errors, "payload.artifacts must be a list")
    artifact_paths = artifact_file_paths(artifacts) if isinstance(artifacts, list) else []
    deploy_result = payload.get("deploy_result")
    require(isinstance(deploy_result, dict), errors, "payload.deploy_result object is required")
    if isinstance(deploy_result, dict):
        require("status" in deploy_result, errors, "deploy_result.status is required")
        if "status" in deploy_result:
            require(
                deploy_result.get("status") in {"PASS", "PASS_WITH_WARNINGS", "FAIL", "PARTIAL", "NEEDS_USER_CONFIRMATION"},
                errors,
                "deploy_result.status is invalid",
            )
        require("strategy" in deploy_result, errors, "deploy_result.strategy is required")
    if payload.get("result") == "success":
        require(not payload.get("structured_errors"), errors, "success payload.structured_errors must be empty")
        require(
            has_artifact_basename(artifact_paths, "deploy_result.json"),
            errors,
            "success payload.artifacts must include deploy_result.json",
        )
        for basename in sorted(SUCCESS_REQUIRED_ARTIFACT_BASENAMES - {"deploy_result.json"}):
            require(
                has_artifact_basename(artifact_paths, basename),
                errors,
                f"success payload.artifacts must include {basename}",
            )
        for label, keywords in SUCCESS_REQUIRED_ARTIFACT_KEYWORDS.items():
            require(
                has_artifact_keyword(artifact_paths, keywords),
                errors,
                f"success payload.artifacts must include {label} capture/report artifact",
            )
    elif payload.get("result") in {"failed", "partial"}:
        require(
            has_artifact_basename(artifact_paths, "deploy_result.json") or payload.get("checkpoint"),
            errors,
            "failed/partial payload.artifacts must include deploy_result.json or a checkpoint",
        )
    return {"status": "ok" if not errors else "failed", "errors": errors}


def artifact_file_paths(artifacts: list[Any]) -> list[str]:
    paths: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("path")
        if isinstance(path, str):
            paths.append(path.replace("\\", "/"))
        files = artifact.get("files")
        if isinstance(files, list):
            for item in files:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    paths.append(item["path"].replace("\\", "/"))
    return paths


def has_artifact_basename(paths: list[str], basename: str) -> bool:
    return any(path.rstrip("/").split("/")[-1] == basename for path in paths)


def has_artifact_keyword(paths: list[str], keywords: tuple[str, ...]) -> bool:
    lowered = [path.lower() for path in paths]
    return any(any(keyword in path for keyword in keywords) for path in lowered)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--validate-start-phase", action="store_true")
    parser.add_argument("--validate-upstream", action="store_true")
    parser.add_argument("--validate-phase-complete", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    data = load_json(args.input)
    if args.validate_start_phase:
        result = validate_start(data)
    elif args.validate_upstream:
        result = validate_upstream(data)
    elif args.validate_phase_complete:
        result = validate_phase_complete(data)
    else:
        result = {"status": "failed", "errors": ["choose a validation mode"]}
    print_json(result)
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
