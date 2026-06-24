#!/usr/bin/env python3
"""Validate generate_plan.json before code generation or final success."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


REQUIRED_SECTIONS = {
    "scheduler_mode",
    "tasks",
    "drivers",
    "config_constants",
    "main_assembly",
    "tests",
}
CLOUD_KEYWORDS = ("cloud", "api", "llm", "asr", "tts", "mqtt", "webhook", "iot", "speech", "voice")
DATA_FLOW_KEYWORDS = (
    "voice",
    "audio",
    "mic",
    "microphone",
    "record",
    "asr",
    "tts",
    "llm",
    "cloud",
    "sensor",
    "threshold",
    "state_machine",
    "state machine",
    "pipeline",
)
VALID_SCHEDULER_MODES = {"timer", "async", "thread"}
FILE_SECTIONS = ("tasks", "drivers", "tests", "middleware")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def infer_plan_path(project_dir: Path, plan_path: str = "") -> Path:
    if plan_path:
        return Path(plan_path)
    return project_dir / "generate_plan.json"


def has_cloud_need(plan: dict[str, Any]) -> bool:
    text = json.dumps(plan, ensure_ascii=False).lower()
    return any(keyword in text for keyword in CLOUD_KEYWORDS)


def has_data_flow_need(plan: dict[str, Any]) -> bool:
    text = json.dumps(
        {
            "requirements": plan.get("requirements"),
            "tasks": plan.get("tasks"),
            "drivers": plan.get("drivers"),
            "cloud_integrations": plan.get("cloud_integrations"),
            "behavior_spec": plan.get("behavior_spec"),
        },
        ensure_ascii=False,
    ).lower()
    return any(keyword in text for keyword in DATA_FLOW_KEYWORDS)


def validate_data_flow_contract(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    contracts = plan.get("data_flow_contract")
    if not has_data_flow_need(plan):
        if contracts is not None and not isinstance(contracts, list):
            errors.append(
                {
                    "code": "GENERATE_PLAN_DATA_FLOW_CONTRACT_INVALID",
                    "message": "data_flow_contract must be a list when present",
                }
            )
        return errors, warnings
    if not isinstance(contracts, list) or not contracts:
        errors.append(
            {
                "code": "GENERATE_PLAN_DATA_FLOW_CONTRACT_MISSING",
                "message": "voice/sensor/cloud/state-machine generation must declare data_flow_contract[]",
            }
        )
        return errors, warnings
    seen_names: list[str] = []
    for index, item in enumerate(contracts):
        if not isinstance(item, dict):
            errors.append(
                {
                    "code": "GENERATE_PLAN_DATA_FLOW_CONTRACT_INVALID",
                    "index": index,
                    "message": "data_flow_contract item must be an object",
                }
            )
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(
                {
                    "code": "GENERATE_PLAN_DATA_FLOW_NAME_MISSING",
                    "index": index,
                    "message": "data_flow_contract item requires name",
                }
            )
        else:
            seen_names.append(name)
        for field in ("producer", "consumer", "invariant"):
            if not isinstance(item.get(field), str) or not item.get(field, "").strip():
                errors.append(
                    {
                        "code": "GENERATE_PLAN_DATA_FLOW_FIELD_MISSING",
                        "index": index,
                        "field": field,
                        "name": name,
                        "message": f"data_flow_contract item requires {field}",
                    }
                )
        producer = str(item.get("producer", ""))
        consumer = str(item.get("consumer", ""))
        cross_stage = any(marker in producer + consumer for marker in (".", "->", "LISTENING", "PROCESSING", "READY", "SPEAKING"))
        if cross_stage and not isinstance(item.get("storage"), str):
            warnings.append(
                {
                    "code": "GENERATE_PLAN_DATA_FLOW_STORAGE_UNSPECIFIED",
                    "index": index,
                    "name": name,
                    "message": "cross-stage data flow should declare storage such as state field, queue, or buffer",
                }
            )
        coverage = item.get("covered_by_tests") or item.get("test_path")
        if not coverage:
            errors.append(
                {
                    "code": "GENERATE_PLAN_DATA_FLOW_TEST_MISSING",
                    "index": index,
                    "name": name,
                    "message": "data_flow_contract must identify contract test coverage",
                }
            )
    duplicates = sorted(name for name in set(seen_names) if seen_names.count(name) > 1)
    if duplicates:
        errors.append(
            {
                "code": "GENERATE_PLAN_DATA_FLOW_DUPLICATE",
                "names": duplicates,
                "message": "data_flow_contract names must be unique",
            }
        )
    return errors, warnings


def validate_plan(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    missing = sorted(section for section in REQUIRED_SECTIONS if section not in plan)
    if missing:
        errors.append({"code": "GENERATE_PLAN_SECTION_MISSING", "missing": missing, "message": "generate_plan.json is missing required sections"})
    mode = plan.get("scheduler_mode")
    if mode not in VALID_SCHEDULER_MODES:
        errors.append(
            {
                "code": "GENERATE_PLAN_SCHEDULER_INVALID",
                "scheduler_mode": mode,
                "message": "scheduler_mode must be timer, async, or thread",
            }
        )
    for section in ("tasks", "drivers", "tests"):
        value = plan.get(section)
        if not isinstance(value, list) or not value:
            errors.append({"code": "GENERATE_PLAN_LIST_EMPTY", "section": section, "message": f"{section} must be a non-empty list"})
    constants = plan.get("config_constants")
    if not isinstance(constants, list) or not constants:
        errors.append({"code": "GENERATE_PLAN_CONFIG_EMPTY", "message": "config_constants must be a non-empty list"})
    else:
        names = []
        for index, item in enumerate(constants):
            if not isinstance(item, dict):
                errors.append({"code": "GENERATE_PLAN_CONFIG_INVALID", "index": index, "message": "config_constants item must be an object"})
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                errors.append({"code": "GENERATE_PLAN_CONFIG_NAME_MISSING", "index": index, "message": "config constant missing name"})
                continue
            names.append(name)
            if "value" not in item and "source" not in item:
                warnings.append({"code": "GENERATE_PLAN_CONFIG_VALUE_UNSPECIFIED", "constant": name, "message": "config constant has no value/source"})
        duplicates = sorted(name for name in set(names) if names.count(name) > 1)
        if duplicates:
            errors.append({"code": "GENERATE_PLAN_CONFIG_DUPLICATE", "constants": duplicates, "message": "config_constants contains duplicate names"})
    assembly = plan.get("main_assembly")
    if not isinstance(assembly, dict):
        errors.append({"code": "GENERATE_PLAN_MAIN_ASSEMBLY_INVALID", "message": "main_assembly must be an object"})
    else:
        for key in ("imports", "drivers", "tasks"):
            if key not in assembly:
                warnings.append({"code": "GENERATE_PLAN_MAIN_ASSEMBLY_FIELD_MISSING", "field": key, "message": f"main_assembly.{key} should be explicit"})
    resource_plan = plan.get("resource_plan")
    if "i2s" in json.dumps(plan.get("drivers", []), ensure_ascii=False).lower() and not isinstance(resource_plan, dict):
        errors.append({"code": "GENERATE_PLAN_RESOURCE_PLAN_MISSING", "message": "I2S/SPI/UART-like shared resources require resource_plan"})
    cloud_integrations = plan.get("cloud_integrations")
    if has_cloud_need(plan) and not isinstance(cloud_integrations, list):
        errors.append({"code": "GENERATE_PLAN_CLOUD_PLAN_MISSING", "message": "Cloud/API/LLM/ASR/TTS needs require cloud_integrations[] in generate_plan.json"})
    data_flow_errors, data_flow_warnings = validate_data_flow_contract(plan)
    errors.extend(data_flow_errors)
    warnings.extend(data_flow_warnings)
    return errors, warnings


def planned_file_entries(plan: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for section in FILE_SECTIONS:
        value = plan.get(section)
        if not isinstance(value, list):
            continue
        for index, item in enumerate(value):
            paths: list[str] = []
            if isinstance(item, str):
                paths.append(item)
            elif isinstance(item, dict):
                for key in ("path", "file", "adapter_path"):
                    path = item.get(key)
                    if isinstance(path, str) and path:
                        paths.append(path)
                files = item.get("files")
                if isinstance(files, list):
                    paths.extend(path for path in files if isinstance(path, str) and path)
            if not paths:
                entries.append({"section": section, "index": index, "path": None})
            else:
                for path in paths:
                    entries.append({"section": section, "index": index, "path": path})
    return entries


def validate_planned_files(project_dir: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for entry in planned_file_entries(plan):
        path_value = entry.get("path")
        if not isinstance(path_value, str) or not path_value:
            errors.append(
                {
                    "code": "GENERATE_PLAN_FILE_PATH_MISSING",
                    "section": entry["section"],
                    "index": entry["index"],
                    "message": "Final generate_plan entries must declare project-relative generated file paths",
                }
            )
            continue
        rel = Path(path_value)
        if rel.is_absolute() or rel.drive or ".." in rel.parts:
            errors.append(
                {
                    "code": "GENERATE_PLAN_FILE_PATH_INVALID",
                    "section": entry["section"],
                    "index": entry["index"],
                    "path": path_value,
                    "message": "generate_plan file paths must stay project-relative",
                }
            )
            continue
        target = project_dir / rel
        if not target.exists():
            errors.append(
                {
                    "code": "GENERATE_PLAN_FILE_MISSING",
                    "section": entry["section"],
                    "index": entry["index"],
                    "path": path_value,
                    "message": "generate_plan declares a generated file that does not exist in the project",
                }
            )
    return errors


def check_project(project_dir: Path, plan_path: str = "", require_plan: bool = False, check_files: bool = False) -> dict[str, Any]:
    path = infer_plan_path(project_dir, plan_path)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not path.exists():
        record = {"code": "GENERATE_PLAN_MISSING", "path": str(path), "message": "generate_plan.json is missing"}
        if require_plan:
            errors.append(record)
        else:
            warnings.append(record)
        return {
            "check": "generate_plan",
            "project_dir": str(project_dir),
            "plan_path": str(path),
            "errors": errors,
            "warnings": warnings,
            "ok": not errors,
        }
    try:
        plan = load_json(path)
    except json.JSONDecodeError as exc:
        errors.append({"code": "GENERATE_PLAN_JSON_INVALID", "path": str(path), "message": str(exc)})
        plan = {}
    if not isinstance(plan, dict):
        errors.append({"code": "GENERATE_PLAN_INVALID", "path": str(path), "message": "generate_plan.json must contain an object"})
        plan = {}
    if plan:
        plan_errors, plan_warnings = validate_plan(plan)
        errors.extend(plan_errors)
        warnings.extend(plan_warnings)
        if check_files:
            errors.extend(validate_planned_files(project_dir, plan))
    return {
        "check": "generate_plan",
        "project_dir": str(project_dir),
        "plan_path": str(path),
        "check_files": check_files,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Validate upy-generate-plugin generate_plan.json")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--plan", default="")
    parser.add_argument("--require-plan", action="store_true")
    parser.add_argument("--check-files", action="store_true", help="Require planned tasks/drivers/tests/middleware files to exist")
    args = parser.parse_args()
    result = check_project(Path(args.project_dir), args.plan, require_plan=args.require_plan, check_files=args.check_files)
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
