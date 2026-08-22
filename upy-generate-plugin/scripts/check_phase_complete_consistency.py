#!/usr/bin/env python3
"""Validate upy-generate-plugin phase_complete success consistency."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump
from driver_ready_gate import driver_ready_gate_errors
from run_quality_gates import PYLINT_KNOWN_BITS, PYLINT_STRONG_FAIL_BITS, pylint_exit_categories


STRONG_CHECKS = {
    "py_compile",
    "generate_plan",
    "conf_contract",
    "driver_source_compile",
    "mpy_imports",
    "dead_config",
    "task_no_machine_import",
    "device_unittest_subset",
    "runtime_dependencies",
    "doc_evidence",
    "skeleton_compliance",
    "generated_semantics",
    "cloud_integrations",
    "session_state_checkpoint",
}
STRONG_LINT = {"flake8", "pylint"}
STRONG_TESTS = {"pc_unittest"}
REQUIRED_MANIFEST_KEYS = {"requirements", "devices", "mcu", "generate"}
GATE_SOURCE_KEY = "results_path"
GATE_SOURCE_MAX_BYTES = 500_000
# The permission entry types that satisfy GIT_PERMISSION_RECORD_MISSING. Named in the error
# so the model is not asked for a record whose shape appears nowhere in the message.
GIT_PERMISSION_TYPES = {"git_commit", "git_operation"}
REQUIRED_OPTIONAL_PHASES = {"upy-diagram-plugin", "upy-wiring-plugin"}
SESSION_STATE_FILE = "session_state.upy_generate_plugin.json"
GIT_SHA40_LENGTH = 40
DEPLOY_TOOL_REQUIREMENTS = {
    "flash_device.py": [
        ("--json-summary", "missing --json-summary CLI option"),
        ("--summary-file", "missing --summary-file CLI option"),
        ("def _ensure_remote_dirs", "missing recursive remote directory helper"),
        ("def _remote_parent_dirs", "missing parent directory expansion helper"),
        ("SOURCE_ONLY_FILES", "missing source-only entry/config upload policy"),
        ("COMPILE_EXCLUDE_PATTERNS", "missing compile exclusion policy"),
        ("UPLOAD_EXCLUDE_PATTERNS", "missing upload exclusion policy"),
        ("compiled_files", "summary must record compiled files"),
        ("uploaded_files", "summary must record uploaded files"),
        ("skipped_files", "summary must record skipped files"),
        ('["resume", "fs", "cp"', "upload must use mpremote resume fs cp"),
        ('["resume", "fs", "mkdir", remote_dir]', "directory creation must use resume fs mkdir"),
    ],
    "read_device_log.py": [
        ("encoding", "missing explicit subprocess encoding"),
        ("utf-8", "missing UTF-8 subprocess decoding"),
        ("errors", "missing subprocess decode error policy"),
        ("replace", "missing errors=replace decode policy"),
    ],
}
DEPLOY_SOURCE_ONLY_REQUIRED = {"firmware/main.py", "firmware/boot.py", "firmware/conf.py"}
DEPLOY_MOCK_EXCLUDE_PATTERNS = {
    "firmware/drivers/**/mock.py",
    "firmware/drivers/*/mock.py",
}
DEPLOY_MOCK_MPY_EXCLUDE_PATTERNS = {
    "firmware/drivers/**/mock.mpy",
    "firmware/drivers/*/mock.mpy",
}
UPSTREAM_HARDWARE_FIELDS = ("mcu", "board", "devices", "pinout")
UPSTREAM_PHASE_FILENAMES = (
    "phase_complete.upy_scaffold_plugin.json",
    "phase_complete.select_hw.json",
    "phase_complete.upy_flash_mpy_firmware_plugin.json",
)


def is_python_cache_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.endswith(".pyc") or "/__pycache__/" in normalized or normalized.startswith("__pycache__/")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def unwrap_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    payload = data.get("payload")
    if isinstance(payload, dict):
        for key in ("manifest_content", "manifest"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
    for key in ("manifest_content", "manifest"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


def normalized_json(value: Any) -> str:
    return json.dumps(normalize_hardware_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_hardware_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_hardware_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [normalize_hardware_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_git_sha(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != GIT_SHA40_LENGTH:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value)


def run_cmd(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    payload: Any = None
    if result.stdout.strip().startswith("{"):
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = None
    return {
        "command": " ".join(cmd),
        "cwd": str(cwd) if cwd else "",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "payload": payload,
    }


def infer_session_dir(project_dir: Path | None) -> Path | None:
    if project_dir is not None:
        return project_dir.parent
    return None


def hardware_error_code(field: str) -> str:
    if field == "devices":
        return "NEW_HARDWARE_REQUIRES_UPSTREAM_SELECTION"
    if field == "pinout":
        return "PINOUT_CHANGE_REQUIRES_SELECT_HW_OR_SCAFFOLD"
    if field in {"mcu", "board"}:
        return "HARDWARE_SELECTION_CHANGED_IN_GENERATE"
    return "HARDWARE_FACT_CHANGED_IN_GENERATE"


def resolve_relative_path(raw_path: str, anchors: list[Path]) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    for anchor in anchors:
        candidate = anchor / path
        if candidate.exists():
            return candidate
    return anchors[0] / path if anchors else path


def source_phase_complete_values(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    source = payload.get("source")
    if isinstance(source, dict):
        for key in ("source_phase_complete_path", "upstream_phase_complete_path", "phase_complete_path", "path"):
            value = source.get(key)
            if isinstance(value, str) and value:
                values.append(value)
        nested = source.get("source_phase_complete")
        if isinstance(nested, dict):
            value = nested.get("path")
            if isinstance(value, str) and value:
                values.append(value)
    for key in ("source_phase_complete_path", "upstream_phase_complete_path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            values.append(value)
    return values


def infer_upstream_phase_complete_path(
    payload: dict[str, Any],
    phase_complete_path: Path | None,
    project_dir: Path | None,
    session_dir: Path | None,
    explicit_path: Path | None,
) -> tuple[Path | None, bool]:
    if explicit_path is not None:
        return explicit_path, True
    anchors: list[Path] = []
    if phase_complete_path is not None:
        anchors.append(phase_complete_path.parent)
    if session_dir is not None:
        anchors.append(session_dir)
        anchors.append(session_dir.parent)
        anchors.append(session_dir.parent.parent)
    if project_dir is not None:
        anchors.append(project_dir.parent)
        anchors.append(project_dir.parent.parent)
    source_values = source_phase_complete_values(payload)
    for value in source_values:
        candidate = resolve_relative_path(value, anchors)
        if candidate.exists():
            return candidate, False
    search_dirs: list[Path] = []
    for directory in [session_dir, phase_complete_path.parent if phase_complete_path else None, project_dir.parent if project_dir else None]:
        if directory is not None and directory not in search_dirs:
            search_dirs.append(directory)
    for directory in search_dirs:
        for filename in UPSTREAM_PHASE_FILENAMES:
            candidate = directory / filename
            if candidate.exists():
                return candidate, False
    return None, bool(source_values)


def upstream_difference_detail(field: str, upstream_value: Any, manifest_value: Any) -> str:
    """Where the two values differ, not merely that they do."""
    if isinstance(upstream_value, dict) and isinstance(manifest_value, dict):
        differs = ", ".join(sorted(
            key for key in set(upstream_value) | set(manifest_value)
            if normalized_json(upstream_value.get(key)) != normalized_json(manifest_value.get(key))
        ))
        return f"{field} differs at: {differs}"
    if isinstance(upstream_value, list) and isinstance(manifest_value, list):
        return f"{field} differs (upstream has {len(upstream_value)} item(s), payload has {len(manifest_value)})"
    return f"{field} differs (upstream={upstream_value!r}, payload={manifest_value!r})"


def upstream_hardware_boundary_errors(
    payload: dict[str, Any],
    phase_complete_path: Path | None,
    project_dir: Path | None,
    session_dir: Path | None,
    upstream_phase_complete_path: Path | None,
) -> list[dict[str, Any]]:
    manifest = payload.get("manifest_content")
    if not isinstance(manifest, dict):
        return []
    upstream_path, explicit_or_declared = infer_upstream_phase_complete_path(
        payload,
        phase_complete_path,
        project_dir,
        session_dir,
        upstream_phase_complete_path,
    )
    if upstream_path is None:
        return []
    if not upstream_path.exists():
        if not explicit_or_declared:
            return []
        return [
            {
                "code": "UPSTREAM_HARDWARE_BASELINE_MISSING",
                "path": str(upstream_path),
                "message": "declared upstream phase_complete is missing; cannot verify generate did not change hardware facts",
            }
        ]
    try:
        upstream_data = load_json(upstream_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [
            {
                "code": "UPSTREAM_HARDWARE_BASELINE_UNREADABLE",
                "path": str(upstream_path),
                "message": str(exc),
            }
        ]
    upstream_manifest = unwrap_manifest(upstream_data)
    if not upstream_manifest:
        return [
            {
                "code": "UPSTREAM_HARDWARE_BASELINE_INVALID",
                "path": str(upstream_path),
                "message": "upstream phase_complete does not contain manifest_content",
            }
        ]
    errors: list[dict[str, Any]] = []
    for field in UPSTREAM_HARDWARE_FIELDS:
        if field not in upstream_manifest and field not in manifest:
            continue
        upstream_value = upstream_manifest.get(field)
        manifest_value = manifest.get(field)
        if normalized_json(upstream_value) == normalized_json(manifest_value):
            continue
        detail = upstream_difference_detail(field, upstream_value, manifest_value)
        errors.append(
            {
                "code": hardware_error_code(field),
                "field": field,
                "differs": detail,
                "upstream_phase_complete": str(upstream_path),
                "message": (
                    f"generate success must preserve upstream hardware facts ({detail}). "
                    "Copy the upstream value back unless the hardware truly changed. "
                    "New/replaced devices, MCU/board changes, and pinout changes must go back through "
                    "analyze/select-hw/scaffold; scaffold incremental output is valid only when it is the upstream baseline."
                ),
            }
        )
    return errors


def gate_ok(name: str, result: Any, strict_pylint: bool) -> tuple[bool, dict[str, Any] | None]:
    # A reference on the GATE rather than on the section. The model generalises the documented
    # payload.checks = {"results_path": ...} down one level, which reads as reasonable and is
    # not resolved here, so say where the key belongs instead of describing the value it lacks.
    if isinstance(result, dict) and GATE_SOURCE_KEY in result:
        return False, {
            "code": "GATE_SOURCE_MISPLACED",
            "gate": name,
            "source": "scripts/run_quality_gates.py",
            "message": (
                f'{GATE_SOURCE_KEY} belongs on the SECTION, not on one gate: set payload.checks = '
                f'{{"{GATE_SOURCE_KEY}": "quality_gates_result.json"}} (and payload.lint and '
                f"payload.tests to that same file), which covers {name} along with every other "
                "gate in it. A per-gate reference is not read, because separate files could "
                "disagree about the same gate."
            ),
        }
    if not isinstance(result, dict):
        # Name the source and the destination; this value is copied from run_quality_gates.py.
        return False, {
            "code": "GATE_RESULT_MISSING",
            "gate": name,
            "source": "scripts/run_quality_gates.py",
            "message": (
                f"the {name} gate result object is missing. Preferred: run scripts/run_quality_gates.py "
                f"--project-dir <project_root> --session-dir <session_root> "
                f'--output-json quality_gates_result.json and set payload.<section> = {{"{GATE_SOURCE_KEY}": '
                f'"quality_gates_result.json"}} for lint, tests and checks alike. Otherwise copy its '
                f"checks.{name} object VERBATIM into payload.<section>.{name} (this error's 'section' field "
                "names the section: lint, tests, or checks). Either way the value comes from that script; "
                "do not compose it by hand."
            ),
        }
    if name == "pylint":
        raw_returncode = result.get("returncode")
        status = str(result.get("status", "")).lower()
        policy = str(result.get("policy", "")).lower()
        reason = str(result.get("reason", "")).lower()
        if raw_returncode is None or "skip" in status or "skip" in policy or "skip" in reason:
            return False, {
                "code": "PYLINT_SKIPPED_ON_SUCCESS",
                "gate": name,
                "returncode": raw_returncode,
                "status": result.get("status"),
                "policy": result.get("policy"),
                "reason": result.get("reason"),
                "message": "pylint must run before generate success; use ensure_pylintrc.py instead of skipping",
            }
        try:
            returncode = int(raw_returncode)
        except (TypeError, ValueError):
            return False, {
                "code": "PYLINT_RETURN_CODE_INVALID",
                "gate": name,
                "returncode": raw_returncode,
                "message": "pylint returncode must be an integer",
            }
        unknown_bits = returncode & ~PYLINT_KNOWN_BITS
        strong_fail = returncode != 0 if strict_pylint else (returncode & PYLINT_STRONG_FAIL_BITS) != 0 or unknown_bits != 0
        if strong_fail:
            return False, {
                "code": "PYLINT_STRONG_FAILURE",
                "gate": name,
                "returncode": returncode,
                "categories": pylint_exit_categories(returncode),
                "message": "pylint fatal/error/usage messages block generate success",
            }
        if returncode != 0 and result.get("ok") is not True:
            return False, {
                "code": "PYLINT_POLICY_NOT_CONFIRMED",
                "gate": name,
                "returncode": returncode,
                "categories": pylint_exit_categories(returncode),
                "accepted_policy": "fail_on_fatal_error_usage",
                "blocking_categories": ["fatal", "error", "usage", "unknown-bit"],
                "accepted_result_shape": {
                    "ok": True,
                    "returncode": returncode,
                    "policy": "fail_on_fatal_error_usage",
                    "categories": pylint_exit_categories(returncode),
                },
                "source_of_truth": "copy the pylint gate result from scripts/run_quality_gates.py; do not hand-invent a thin success record",
                "message": (
                    "nonzero pylint can pass only when the embedded pylint gate result records "
                    "ok=true under policy fail_on_fatal_error_usage. Fatal/error/usage or unknown "
                    "pylint categories still block generate success; copy returncode, policy, "
                    "categories, and ok from run_quality_gates.py."
                ),
            }
        return True, None
    if result.get("ok") is False:
        return False, {
            "code": "GATE_NOT_OK",
            "gate": name,
            "returncode": result.get("returncode"),
            "message": f"{name} reported ok=false",
        }
    if result.get("returncode") not in (0, None):
        return False, {
            "code": "GATE_RETURN_CODE_FAILED",
            "gate": name,
            "returncode": result.get("returncode"),
            "message": f"{name} returned {result.get('returncode')}",
        }
    return True, None


def resolve_gate_section(section: Any, project_dir: Path | None) -> tuple[Any, dict[str, Any] | None]:
    if not isinstance(section, dict):
        return section, None
    reference = section.get(GATE_SOURCE_KEY)
    if not isinstance(reference, str) or not reference:
        return section, None
    ref_path = Path(reference)
    if ref_path.is_absolute() or ".." in ref_path.parts:
        return None, {
            "code": "GATE_SOURCE_UNREADABLE",
            "source": "scripts/run_quality_gates.py",
            "path": reference,
            "message": "gate results_path must be a project-relative path and must not contain '..'",
        }
    base = project_dir or Path(".")
    target = base / ref_path
    if not target.is_file():
        return None, {
            "code": "GATE_SOURCE_UNREADABLE",
            "source": "scripts/run_quality_gates.py",
            "path": reference,
            "message": (
                f"gate results_path {reference!r} was not found under {base}; run "
                "scripts/run_quality_gates.py --output-json <path> and reference that same file"
            ),
        }
    try:
        raw = target.read_bytes()
        if len(raw) > GATE_SOURCE_MAX_BYTES:
            raise ValueError(f"file is larger than {GATE_SOURCE_MAX_BYTES} bytes")
        loaded = json.loads(raw.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, {
            "code": "GATE_SOURCE_UNREADABLE",
            "source": "scripts/run_quality_gates.py",
            "path": reference,
            "message": f"gate results_path {reference!r} could not be read as JSON: {exc}",
        }
    gates = loaded.get("checks") if isinstance(loaded, dict) else None
    return (gates if isinstance(gates, dict) else loaded), None


def collect_gate_errors(payload: dict[str, Any], strict_pylint: bool, project_dir: Path | None = None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    sections = [
        ("lint", STRONG_LINT),
        ("tests", STRONG_TESTS),
        ("checks", STRONG_CHECKS),
    ]
    referenced = {
        name: payload[name][GATE_SOURCE_KEY]
        for name in ("lint", "tests", "checks")
        if isinstance(payload.get(name), dict) and isinstance(payload[name].get(GATE_SOURCE_KEY), str)
    }
    # Partial adoption is the hole the same-file rule missed: reference the real gates file for
    # checks and lint, leave tests embedded as {"pc_unittest": {"ok": true}}, and the payload
    # validates clean while the file it named says that gate failed. Needs no forged file at all.
    if referenced and len(referenced) != len(sections):
        errors.append(
            {
                "code": "GATE_SOURCE_SPLIT",
                "source": "scripts/run_quality_gates.py",
                "message": (
                    "payload.lint, payload.tests and payload.checks must all use results_path when any "
                    f"one section does; got references for {', '.join(sorted(referenced))}. Pure embedded "
                    "gate objects are still accepted only when none of the three sections uses results_path."
                ),
            }
        )
    if len(set(referenced.values())) > 1:
        errors.append(
            {
                "code": "GATE_SOURCE_SPLIT",
                "source": "scripts/run_quality_gates.py",
                "message": (
                    "payload.lint, payload.tests and payload.checks must reference the same "
                    f"{GATE_SOURCE_KEY} file; got "
                    + ", ".join(f"{key}={value}" for key, value in sorted(referenced.items()))
                ),
            }
        )
    for section_name, names in sections:
        section, reference_error = resolve_gate_section(payload.get(section_name), project_dir)
        if reference_error is not None:
            reference_error["section"] = section_name
            errors.append(reference_error)
            continue
        if not isinstance(section, dict):
            errors.append(
                {
                    "code": "GATE_SECTION_MISSING",
                    "section": section_name,
                    "required_gates": sorted(names),
                    "source": "scripts/run_quality_gates.py",
                    "message": (
                        f"payload.{section_name} is required for generate success. Preferred: set "
                        f'payload.{section_name} = {{"{GATE_SOURCE_KEY}": "quality_gates_result.json"}} '
                        "after running scripts/run_quality_gates.py --output-json quality_gates_result.json; "
                        "the embedded gate-object form is still accepted."
                    ),
                }
            )
            continue
        for name in sorted(names):
            ok, error = gate_ok(name, section.get(name), strict_pylint)
            if not ok and error:
                error["section"] = section_name
                errors.append(error)
    return errors


def shape_message(path: str, expected: str, value: Any, example: str) -> str:
    """Explain both the expected JSON shape and the actual shape that was found."""
    if value is None:
        seen = "it is absent"
    elif isinstance(value, (dict, list, str)) and not value:
        seen = f"it is an empty {type(value).__name__}"
    else:
        seen = f"it is a {type(value).__name__}"
    return f"{path} must be {expected}, and {seen}. Example: {example}"


def deploy_plan_errors(deploy_plan: Any) -> list[dict[str, Any]]:
    if not isinstance(deploy_plan, dict):
        return [
            {
                "code": "MANIFEST_DEPLOY_PLAN_MISSING",
                "message": shape_message(
                    "manifest_content.generate.deploy_plan",
                    "an object",
                    deploy_plan,
                    '{"source_only": ["firmware/main.py", "firmware/boot.py", "firmware/conf.py"], '
                    '"upload_exclude": ["firmware/drivers/**/mock.py", "firmware/drivers/**/mock.mpy"]}',
                ),
            }
        ]
    errors: list[dict[str, Any]] = []
    source_only = deploy_plan.get("source_only")
    source_only_set = {str(item).replace("\\", "/") for item in source_only} if isinstance(source_only, list) else set()
    missing_source_only = sorted(DEPLOY_SOURCE_ONLY_REQUIRED - source_only_set)
    if missing_source_only:
        errors.append(
            {
                "code": "DEPLOY_PLAN_SOURCE_ONLY_MISSING",
                "missing": missing_source_only,
                "message": "deploy_plan.source_only must keep main.py, boot.py, and conf.py as uploaded .py files, not compiled .mpy",
            }
        )
    upload_exclude = deploy_plan.get("upload_exclude")
    upload_exclude_set = {str(item).replace("\\", "/") for item in upload_exclude} if isinstance(upload_exclude, list) else set()
    if not (upload_exclude_set & DEPLOY_MOCK_EXCLUDE_PATTERNS):
        errors.append(
            {
                "code": "DEPLOY_PLAN_MOCK_UPLOAD_EXCLUDE_MISSING",
                "message": "deploy_plan.upload_exclude must exclude firmware/drivers/**/mock.py from production uploads",
            }
        )
    if not (upload_exclude_set & DEPLOY_MOCK_MPY_EXCLUDE_PATTERNS):
        errors.append(
            {
                "code": "DEPLOY_PLAN_MOCK_MPY_UPLOAD_EXCLUDE_MISSING",
                "message": "deploy_plan.upload_exclude must exclude firmware/drivers/**/mock.mpy stale build artifacts",
            }
        )
    return errors


def comparable_manifest_value(key: str, value: Any) -> Any:
    """The part of a manifest field that must match the tracked project-manifest.json.

    `generate.git.commit` is excluded because it cannot match and be true at the same time:
    final_git_consistency_errors() requires it to equal HEAD, and project-manifest.json is
    tracked, so writing HEAD into it produces a NEW head and invalidates what was just
    written. The commit is still verified against HEAD in final_git_consistency_errors,
    just not against the tracked manifest copy.
    """
    if key != "generate" or not isinstance(value, dict):
        return value
    return {inner: item for inner, item in value.items() if inner != "git"}


def manifest_difference_detail(payload_value: Any, project_value: Any) -> str:
    """Where the payload copy and the tracked file diverge, as a message suffix."""
    if isinstance(payload_value, dict) and isinstance(project_value, dict):
        inner = sorted(
            key for key in set(payload_value) | set(project_value)
            if payload_value.get(key) != project_value.get(key)
        )
        return f" (differs at: {', '.join(inner)})" if inner else ""
    if isinstance(payload_value, list) and isinstance(project_value, list):
        if len(payload_value) != len(project_value):
            return f" (payload has {len(payload_value)} entries, project has {len(project_value)})"
        at = next((i for i, (a, b) in enumerate(zip(payload_value, project_value)) if a != b), None)
        return f" (differs at index {at})" if at is not None else ""
    if isinstance(payload_value, (str, int, float, bool)) or payload_value is None:
        return f" (payload={payload_value!r}, project={project_value!r})"
    return ""


def manifest_errors(payload: dict[str, Any], project_dir: Path | None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    manifest = payload.get("manifest_content")
    if not isinstance(manifest, dict):
        return [{"code": "MANIFEST_CONTENT_MISSING", "message": "payload.manifest_content must be a JSON object"}]
    if manifest.get("phase") != "generate":
        errors.append(
            {
                "code": "MANIFEST_PHASE_NOT_GENERATE",
                "phase": manifest.get("phase"),
                "message": "payload.manifest_content.phase must be generate on success",
            }
        )
    if manifest.get("domain_phase") not in (None, "generate"):
        errors.append(
            {
                "code": "MANIFEST_DOMAIN_PHASE_NOT_GENERATE",
                "domain_phase": manifest.get("domain_phase"),
                "message": "payload.manifest_content.domain_phase must be generate when present",
            }
        )
    if manifest.get("final_status") not in (None, "generated"):
        errors.append(
            {
                "code": "MANIFEST_FINAL_STATUS_NOT_GENERATED",
                "final_status": manifest.get("final_status"),
                "message": "payload.manifest_content.final_status must be generated when present",
            }
        )
    missing = sorted(key for key in REQUIRED_MANIFEST_KEYS if key not in manifest)
    if missing:
        errors.append(
            {
                "code": "MANIFEST_REQUIRED_FIELD_MISSING",
                "keys": sorted(manifest.keys()),
                "missing": missing,
                "message": "payload.manifest_content must carry the updated full project manifest, not a thin generate summary",
            }
        )
    devices = manifest.get("devices")
    if not isinstance(devices, list) or not devices:
        errors.append({"code": "MANIFEST_DEVICES_MISSING", "message": "manifest_content.devices must be a non-empty list on success"})
    else:
        errors.extend(driver_ready_gate_errors(manifest))
    requirements = manifest.get("requirements")
    if not isinstance(requirements, dict) or not requirements.get("description"):
        errors.append({"code": "MANIFEST_REQUIREMENTS_MISSING", "message": "manifest_content.requirements.description is required on success"})
    if "pinout" not in manifest and not manifest.get("pinout_not_required"):
        errors.append({"code": "MANIFEST_PINOUT_MISSING", "message": "manifest_content.pinout is required unless pinout_not_required is explicit"})
    if "scaffold" not in manifest and "scaffold_mode" not in manifest:
        errors.append({"code": "MANIFEST_SCAFFOLD_CONTEXT_MISSING", "message": "manifest_content must preserve scaffold context"})
    generate = manifest.get("generate")
    if not isinstance(generate, dict):
        errors.append(
            {
                "code": "MANIFEST_GENERATE_SECTION_MISSING",
                "message": shape_message(
                    "manifest_content.generate",
                    "an object",
                    generate,
                    '{"behavior_spec": {...}, "deploy_plan": {...}, "simulation_hints": {...}}',
                ),
            }
        )
    else:
        errors.extend(deploy_plan_errors(generate.get("deploy_plan")))
        if not isinstance(generate.get("behavior_spec"), dict):
            errors.append(
                {
                    "code": "MANIFEST_BEHAVIOR_SPEC_MISSING",
                    "message": shape_message(
                        "manifest_content.generate.behavior_spec",
                        "an object",
                        generate.get("behavior_spec"),
                        '{"description": "Toggle the onboard LED every 1000 ms"}',
                    ),
                }
            )
        if not isinstance(generate.get("simulation_hints"), dict):
            errors.append(
                {
                    "code": "MANIFEST_SIMULATION_HINTS_MISSING",
                    "message": shape_message(
                        "manifest_content.generate.simulation_hints",
                        "an object",
                        generate.get("simulation_hints"),
                        '{"mock_devices": ["led"]}',
                    ),
                }
            )
        manifest_git = generate.get("git")
        if isinstance(manifest_git, dict) and isinstance(manifest_git.get("commit"), str) and manifest_git.get("commit"):
            if not isinstance(manifest_git.get("commit_role"), str) or not manifest_git.get("commit_role"):
                errors.append(
                    {
                        "code": "MANIFEST_GIT_COMMIT_ROLE_MISSING",
                        "commit": manifest_git.get("commit"),
                        "message": "manifest_content.generate.git.commit must declare commit_role or use code_commit to avoid final-HEAD self-reference ambiguity",
                    }
                )
        errors.extend(cloud_integration_errors(generate, payload.get("next_phase")))
    if project_dir:
        manifest_path = project_dir / "project-manifest.json"
        if not manifest_path.exists():
            errors.append({"code": "PROJECT_MANIFEST_MISSING", "path": str(manifest_path), "message": "project-manifest.json is missing"})
        else:
            try:
                project_manifest = load_json(manifest_path)
            except json.JSONDecodeError as exc:
                errors.append({"code": "PROJECT_MANIFEST_JSON_INVALID", "path": str(manifest_path), "message": str(exc)})
            else:
                if not isinstance(project_manifest, dict) or project_manifest.get("phase") != "generate":
                    errors.append(
                        {
                            "code": "PROJECT_MANIFEST_PHASE_NOT_GENERATE",
                            "path": str(manifest_path),
                            "phase": project_manifest.get("phase") if isinstance(project_manifest, dict) else None,
                            "message": "project/project-manifest.json must advance to phase=generate on success",
                        }
                    )
                elif isinstance(project_manifest, dict):
                    if project_manifest.get("domain_phase") not in (None, "generate"):
                        errors.append(
                            {
                                "code": "PROJECT_MANIFEST_DOMAIN_PHASE_NOT_GENERATE",
                                "path": str(manifest_path),
                                "domain_phase": project_manifest.get("domain_phase"),
                                "message": "project/project-manifest.json domain_phase must be generate when present",
                            }
                        )
                    if project_manifest.get("final_status") not in (None, "generated"):
                        errors.append(
                            {
                                "code": "PROJECT_MANIFEST_FINAL_STATUS_NOT_GENERATED",
                                "path": str(manifest_path),
                                "final_status": project_manifest.get("final_status"),
                                "message": "project/project-manifest.json final_status must be generated when present",
                            }
                        )
                    for key in REQUIRED_MANIFEST_KEYS | {"pinout"}:
                        if key not in project_manifest:
                            continue
                        payload_value = comparable_manifest_value(key, manifest.get(key))
                        project_value = comparable_manifest_value(key, project_manifest.get(key))
                        if payload_value != project_value:
                            where = manifest_difference_detail(payload_value, project_value)
                            errors.append(
                                {
                                    "code": "MANIFEST_PROJECT_MISMATCH",
                                    "field": key,
                                    "path": str(manifest_path),
                                    "message": (
                                        f"payload.manifest_content.{key} must match project-manifest.json{where}. "
                                        "Copy the tracked file's value rather than regenerating it."
                                    ),
                                }
                            )
    return errors


def cloud_integration_errors(generate: dict[str, Any], next_phase: Any) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    integrations = generate.get("cloud_integrations", [])
    if integrations in (None, []):
        return errors
    if not isinstance(integrations, list):
        return [{"code": "CLOUD_INTEGRATIONS_INVALID", "message": "generate.cloud_integrations must be a list"}]
    for index, item in enumerate(integrations):
        if not isinstance(item, dict):
            errors.append({"code": "CLOUD_INTEGRATION_INVALID", "index": index, "message": "cloud integration item must be an object"})
            continue
        provider_id = item.get("provider_id") or item.get("provider")
        if not provider_id:
            errors.append(
                {
                    "code": "CLOUD_PROVIDER_ID_MISSING",
                    "index": index,
                    "accepted_keys": ["provider_id", "provider"],
                    "message": "cloud integration requires provider_id; provider is also accepted on the same entry",
                }
            )
        category = item.get("category")
        services = item.get("services")
        if not category:
            errors.append({"code": "CLOUD_CATEGORY_MISSING", "index": index, "provider_id": provider_id, "message": "cloud integration requires category"})
        if not isinstance(services, list) or not services:
            errors.append(
                {
                    "code": "CLOUD_SERVICES_MISSING",
                    "index": index,
                    "provider_id": provider_id,
                    "message": shape_message("cloud_integrations[].services", "a non-empty list", services, '["asr", "tts"]'),
                }
            )
        if provider_id != "custom_http_proxy":
            links = item.get("official_links")
            if not isinstance(links, dict) or not (links.get("docs") or links.get("product")) or not links.get("console"):
                errors.append(
                    {
                        "code": "CLOUD_OFFICIAL_LINKS_MISSING",
                        "index": index,
                        "provider_id": provider_id,
                        "message": "provider docs/product and console links are required for user setup prompts",
                    }
                )
        credential = item.get("credential_management")
        if not isinstance(credential, dict):
            errors.append(
                {
                    "code": "CLOUD_CREDENTIAL_MANAGEMENT_MISSING",
                    "index": index,
                    "provider_id": provider_id,
                    "message": shape_message(
                        "cloud_integrations[].credential_management",
                        "an object",
                        credential,
                        '{"status": "deferred_to_deploy", "storage": "env", "keys": ["OPENAI_API_KEY"]}',
                    ),
                }
            )
            continue
        status = credential.get("status")
        if status not in {"ready", "deferred_to_deploy", "mock_only", "not_required"}:
            errors.append(
                {
                    "code": "CLOUD_CREDENTIAL_STATUS_INVALID",
                    "index": index,
                    "provider_id": provider_id,
                    "status": status,
                    "message": "success cannot contain blocked or unknown cloud credential status",
                }
            )
        if next_phase == "upy-deploy-plugin" and status == "mock_only":
            errors.append(
                {
                    "code": "CLOUD_MOCK_ONLY_CANNOT_DEPLOY",
                    "index": index,
                    "provider_id": provider_id,
                    "message": "mock_only cloud integration cannot proceed directly to deploy",
                }
            )
        if next_phase == "upy-deploy-plugin" and status not in {"ready", "deferred_to_deploy", "not_required"}:
            errors.append(
                {
                    "code": "CLOUD_CREDENTIALS_REQUIRED",
                    "index": index,
                    "provider_id": provider_id,
                    "status": status,
                    "message": "deploy handoff requires cloud credentials ready, deferred_to_deploy, or not_required",
                }
            )
    return errors


def next_phase_decision_errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("next_phase") is not None:
        return []
    decision = payload.get("next_phase_decision")
    if not isinstance(decision, dict):
        return [
            {
                "code": "NEXT_PHASE_NULL_WITHOUT_DECISION",
                "message": shape_message(
                    "payload.next_phase_decision",
                    "an object with value=null and a reason string (a bare sentence is not enough, "
                    "the explanation goes inside reason)",
                    decision,
                    '{"value": null, "reason": "the user asked to stop after generate"}',
                ),
            }
        ]
    errors: list[dict[str, Any]] = []
    if decision.get("value") is not None:
        errors.append(
            {
                "code": "NEXT_PHASE_DECISION_VALUE_INVALID",
                "value": decision.get("value"),
                "message": "next_phase_decision.value must be null when payload.next_phase is null",
            }
        )
    reason = decision.get("reason")
    if not isinstance(reason, str) or not reason.strip() or reason.strip().lower() == "unknown":
        errors.append(
            {
                "code": "NEXT_PHASE_DECISION_REASON_MISSING",
                "message": "next_phase_decision.reason must explain why success does not advance to deploy or simulate",
            }
        )
    return errors


def deploy_tool_compat_errors(project_dir: Path | None, next_phase: Any) -> list[dict[str, Any]]:
    if project_dir is None or next_phase != "upy-deploy-plugin":
        return []
    tools_dir = project_dir / "tools"
    missing: list[dict[str, str]] = []
    for filename, checks in DEPLOY_TOOL_REQUIREMENTS.items():
        path = tools_dir / filename
        if not path.exists():
            missing.append({"path": f"tools/{filename}", "requirement": "file is missing"})
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            missing.append({"path": f"tools/{filename}", "requirement": f"file is not UTF-8 readable: {exc}"})
            continue
        for needle, message in checks:
            if needle not in text:
                missing.append({"path": f"tools/{filename}", "requirement": message})
    if not missing:
        return []
    return [
        {
            "code": "DEPLOY_TOOL_INCOMPATIBLE",
            "message": "next_phase=upy-deploy-plugin requires scaffold-rendered project deploy tools with the stable deploy-plugin interface",
            "missing": missing,
            "source_of_truth": "tools/flash_device.py is rendered by apply_scaffold when the flash_device module is selected; do not author it by hand.",
            "script_run_scope": "generic script_run resolves bundled plugin/shared scripts only, not project/tools/*.py",
            "accepted_resolutions": [
                "restore or re-run scaffold/apply_scaffold with the flash_device module selected, then preserve the scaffold-rendered tools/flash_device.py",
                "set payload.next_phase=null and record next_phase_decision for code-only/manual-flash delivery",
            ],
        }
    ]


def optional_next_phase_errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    optional = payload.get("optional_next_phases")
    if not isinstance(optional, list):
        return [{"code": "OPTIONAL_NEXT_PHASES_MISSING", "message": "success must expose optional_next_phases[]"}]
    phases = set()
    for item in optional:
        if isinstance(item, dict) and isinstance(item.get("phase"), str):
            phases.add(item["phase"])
        elif isinstance(item, str):
            phases.add(item)
    missing = sorted(REQUIRED_OPTIONAL_PHASES - phases)
    if missing:
        return [
            {
                "code": "OPTIONAL_NEXT_PHASE_MISSING",
                "missing": missing,
                "message": "success must offer diagram and wiring plugins as optional post-generate artifacts",
            }
        ]
    return []


def file_manifest_errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    file_manifest = payload.get("file_manifest")
    files = file_manifest.get("files") if isinstance(file_manifest, dict) else None
    if not isinstance(files, list):
        return [
            {
                "code": "FILE_MANIFEST_MISSING",
                "message": shape_message(
                    "file_manifest.files",
                    "a list of file entries",
                    files,
                    '[{"path": "project-manifest.json", "role": "manifest"}, '
                    '{"path": "generate_plan.json", "role": "plan"}, '
                    '{"path": "session_state.upy_generate_plugin.json", "role": "artifact"}]',
                ),
            }
        ]
    errors: list[dict[str, Any]] = []
    has_project_manifest = any(
        isinstance(item, dict) and item.get("role") == "manifest" and item.get("path") == "project-manifest.json"
        for item in files
    )
    if not has_project_manifest:
        errors.append(
            {
                "code": "FILE_MANIFEST_MISSING_PROJECT_MANIFEST",
                "message": "file_manifest.files must include project-manifest.json with role=manifest",
            }
        )
    has_generate_plan = any(
        isinstance(item, dict) and item.get("role") == "plan" and item.get("path") == "generate_plan.json"
        for item in files
    )
    if not has_generate_plan:
        errors.append(
            {
                "code": "FILE_MANIFEST_MISSING_GENERATE_PLAN",
                "message": "file_manifest.files must include generate_plan.json with role=plan",
            }
        )
    has_session_state = any(
        isinstance(item, dict)
        and item.get("role") == "artifact"
        and isinstance(item.get("path"), str)
        and item.get("path", "").endswith(SESSION_STATE_FILE)
        for item in files
    )
    if not has_session_state:
        errors.append(
            {
                "code": "FILE_MANIFEST_MISSING_SESSION_STATE",
                "message": f"file_manifest.files must include {SESSION_STATE_FILE} with role=artifact",
            }
        )
    for item in files:
        if isinstance(item, dict) and isinstance(item.get("path"), str) and is_python_cache_path(item["path"]):
            errors.append(
                {
                    "code": "FILE_MANIFEST_PYTHON_CACHE_PRESENT",
                    "path": item["path"],
                    "message": "file_manifest must not include __pycache__ or .pyc artifacts",
                }
            )
    return errors


def unwrap_gate_payload(gate: Any) -> Any:
    if isinstance(gate, dict) and "state" not in gate and isinstance(gate.get("payload"), dict):
        return gate["payload"]
    return gate


def session_state_check_errors(
    payload: dict[str, Any],
    phase_complete_path: Path | None,
    project_dir: Path | None,
    session_dir: Path | None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if payload.get("checkpoint") != "phase_completed":
        errors.append(
            {
                "code": "CHECKPOINT_NOT_PHASE_COMPLETED",
                "checkpoint": payload.get("checkpoint"),
                "message": (
                    'payload.checkpoint must be the string "phase_completed" (a top-level payload field, '
                    "distinct from checks.session_state_checkpoint). Record the checkpoint first with "
                    "update_session_state.py --checkpoint phase_completed --status completed, then mirror it here."
                ),
            }
        )
    # Which form the payload used decides what the remedy below can legally be. In the
    # referenced form the checkpoint gate is a SNAPSHOT inside quality_gates_result.json, so
    # "embed the --check output under checks.session_state_checkpoint" is not performable:
    # a per-gate object there is now GATE_SOURCE_MISPLACED, and mixing forms is
    # GATE_SOURCE_SPLIT. The only way to refresh it is to re-run the gates.
    raw_checks = payload.get("checks")
    gates_reference = (
        raw_checks.get(GATE_SOURCE_KEY)
        if isinstance(raw_checks, dict) and isinstance(raw_checks.get(GATE_SOURCE_KEY), str)
        else None
    )
    checks, reference_error = resolve_gate_section(raw_checks, project_dir)
    if reference_error is not None:
        reference_error["section"] = "checks"
        errors.append(reference_error)
    if not isinstance(checks, dict):
        checks = {}
    state_check = unwrap_gate_payload(checks.get("session_state_checkpoint"))
    if not isinstance(state_check, dict):
        errors.append(
            {
                "code": "SESSION_STATE_CHECKPOINT_MISSING",
                "message": (
                    "success must include checks.session_state_checkpoint. It is one gate INSIDE the "
                    "checks object, so produce it with the same command as the rest: run "
                    "scripts/run_quality_gates.py --project-dir <project_root> --session-dir <session_root> "
                    "--output-json quality_gates_result.json. Without --session-dir that file has 18 gates "
                    "and no session_state_checkpoint, and referencing it can never satisfy this check. Keep "
                    "the checks object WHOLE: replacing it with only this gate drops the other 18."
                ),
            }
        )
    elif state_check.get("ok") is not True:
        errors.append(
            {
                "code": "SESSION_STATE_CHECKPOINT_NOT_OK",
                "returncode": state_check.get("returncode"),
                "message": "session state checkpoint check must pass before success",
            }
        )
    else:
        state = state_check.get("state")
        if not isinstance(state, dict):
            errors.append(
                {
                    "code": "SESSION_STATE_CHECKPOINT_STATE_MISSING",
                    "source": "scripts/update_session_state.py --check",
                    "message": (
                        "checks.session_state_checkpoint.state is missing. checks.session_state_checkpoint "
                        "must be the whole JSON object printed by scripts/update_session_state.py --check; "
                        "embed that output instead of composing the block."
                    ),
                }
            )
        else:
            for field in (
                "protocol_version",
                "session_id",
                "phase",
                "checkpoint",
                "status",
                "attempt",
                "idempotency_key",
                "manifest_hash",
                "git_commit",
                "usage",
            ):
                if field not in state:
                    errors.append(
                        {
                            "code": "SESSION_STATE_CHECKPOINT_FIELD_MISSING",
                            "field": field,
                            "source": "scripts/update_session_state.py --check",
                            "message": (
                                f"checks.session_state_checkpoint.state must record {field}. Re-run "
                                "scripts/update_session_state.py --check and copy its output whole; "
                                "do not hand-compose the state object."
                            ),
                        }
                    )
            if state.get("manifest_hash") == "unknown":
                errors.append(
                    {
                        "code": "SESSION_STATE_CHECKPOINT_MANIFEST_HASH_UNKNOWN",
                        "message": (
                            "success session_state checkpoint must record the manifest hash. Re-run "
                            "update_session_state.py with --project-dir set (it computes the SHA256 of "
                            "project-manifest.json itself), then --check, and embed that output."
                        ),
                    }
                )
            if state.get("manifest_hash") == state.get("git_commit") and looks_like_git_sha(state.get("manifest_hash")):
                errors.append(
                    {
                        "code": "SESSION_STATE_CHECKPOINT_MANIFEST_HASH_IS_GIT_COMMIT",
                        "message": "success session_state manifest_hash must be project-manifest.json SHA256, not git commit",
                    }
                )
            git_commit = state.get("git_commit")
            if not isinstance(git_commit, str) or not git_commit.strip():
                errors.append(
                    {
                        "code": "SESSION_STATE_CHECKPOINT_GIT_COMMIT_MISSING",
                        "message": (
                            "success session_state checkpoint must record the generate git commit. Record it via "
                            "update_session_state.py --git-commit <sha>, then re-run --check and embed that output."
                        ),
                    }
                )
            usage = state.get("usage")
            if not isinstance(usage, dict) or "token_budget_status" not in usage or "remaining_budget" not in usage:
                errors.append(
                    {
                        "code": "SESSION_STATE_CHECKPOINT_USAGE_INVALID",
                        "message": (
                            "success session_state checkpoint must record usage.token_budget_status and "
                            'usage.remaining_budget. Record them via update_session_state.py --usage-json '
                            '\'{"token_budget_status": "ok", "remaining_budget": <n>}\', then re-run --check '
                            "and embed that output; do not add the keys by hand."
                        ),
                    }
                )
    _ = phase_complete_path
    disk_session_dir = session_dir or infer_session_dir(project_dir)
    if disk_session_dir is not None:
        state_path = disk_session_dir / SESSION_STATE_FILE
        if not state_path.exists():
            errors.append(
                {
                    "code": "SESSION_STATE_DISK_FILE_MISSING",
                    "path": str(state_path),
                    "message": f"{SESSION_STATE_FILE} must exist beside phase_complete or in --session-dir",
                }
            )
        else:
            cmd = [
                sys.executable,
                str(Path(__file__).resolve().parent / "update_session_state.py"),
                "--session-dir",
                str(disk_session_dir),
                "--check",
            ]
            if project_dir is not None:
                cmd.extend(["--project-dir", str(project_dir)])
            disk_check = run_cmd(cmd)
            disk_payload = disk_check.get("payload")
            if disk_check["returncode"] != 0 or not isinstance(disk_payload, dict) or disk_payload.get("ok") is not True:
                errors.append(
                    {
                        "code": "SESSION_STATE_DISK_CHECK_FAILED",
                        "path": str(state_path),
                        "returncode": disk_check["returncode"],
                        "errors": disk_payload.get("errors", []) if isinstance(disk_payload, dict) else [],
                        "message": "disk session_state.upy_generate_plugin.json must pass update_session_state.py --check",
                    }
                )
            elif isinstance(state_check, dict):
                embedded_state = state_check.get("state")
                disk_state = disk_payload.get("state") if isinstance(disk_payload, dict) else None
                if isinstance(embedded_state, dict) and isinstance(disk_state, dict):
                    for field in ("session_id", "checkpoint", "status", "idempotency_key", "manifest_hash", "git_commit", "usage"):
                        if embedded_state.get(field) != disk_state.get(field):
                            errors.append(
                                {
                                    "code": "SESSION_STATE_PHASE_COMPLETE_MISMATCH",
                                    "field": field,
                                    "embedded": embedded_state.get(field),
                                    "disk": disk_state.get(field),
                                    # Which side to change was never stated, so a run can
                                    # "fix" it by editing the file and drift again on the
                                    # next write. Disk is authoritative: it is what
                                    # update_session_state.py --check just validated.
                                    "authoritative": "disk",
                                    "results_path": gates_reference,
                                    "message": (
                                        f"phase_complete embedded session_state_checkpoint.state.{field} "
                                        "does not match the disk session_state. The DISK value is "
                                        "authoritative. "
                                        + (
                                            # The referenced form cannot be fixed by embedding:
                                            # the gate is a snapshot taken when the gates ran, so
                                            # anything that touched project-manifest.json or the
                                            # session state afterwards stales it, and only a fresh
                                            # gate run rewrites the file.
                                            f"payload.checks references {gates_reference!r}, and the gate "
                                            "inside it is a SNAPSHOT from when that file was written, "
                                            "which a later manifest edit or update_session_state.py run "
                                            "has since staled. Re-run scripts/run_quality_gates.py "
                                            "--project-dir <project_root> --session-dir <session_root> "
                                            f"--output-json {gates_reference} so the file is rewritten, "
                                            "then validate again. Do NOT embed the gate under "
                                            "payload.checks instead: a per-gate object there is refused as "
                                            "GATE_SOURCE_MISPLACED, and mixing the two forms is refused as "
                                            "GATE_SOURCE_SPLIT."
                                            if gates_reference
                                            else "Re-run update_session_state.py --check and embed its "
                                            "result under checks.session_state_checkpoint rather than "
                                            "editing the payload by hand."
                                        )
                                    ),
                                }
                            )
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append(
            {
                "code": "ARTIFACTS_MISSING",
                "message": "payload.artifacts must be present on success",
            }
        )
    elif not any(
        isinstance(item, dict)
        and item.get("type") == "session_state"
        and isinstance(item.get("path"), str)
        and item.get("path", "").endswith(SESSION_STATE_FILE)
        for item in artifacts
    ):
        errors.append(
            {
                "code": "SESSION_STATE_ARTIFACT_MISSING",
                "expected_entry": {"type": "session_state", "path": f"<session dir>/{SESSION_STATE_FILE}"},
                "message": (
                    f"payload.artifacts must include an entry with type=\"session_state\" whose path ends in "
                    f"{SESSION_STATE_FILE}; a path-only entry without that type does not count."
                ),
            }
        )
    if isinstance(artifacts, list) and not any(
        isinstance(item, dict)
        and item.get("type") == "file_manifest"
        and isinstance(item.get("path"), str)
        for item in artifacts
    ):
        errors.append(
            {
                "code": "FILE_MANIFEST_ARTIFACT_MISSING",
                "expected_entry": {"type": "file_manifest", "path": "<path of the file manifest json>"},
                "message": (
                    'payload.artifacts must include an entry with type="file_manifest" and a string path; '
                    "an entry with another type does not count."
                ),
            }
        )
    return errors


def recorded_generate_git(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the generate git record from either accepted payload location."""
    payload_generate = payload.get("generate") if isinstance(payload.get("generate"), dict) else {}
    git_info = payload_generate.get("git") if isinstance(payload_generate.get("git"), dict) else None
    if not git_info:
        manifest = payload.get("manifest_content") if isinstance(payload.get("manifest_content"), dict) else {}
        manifest_generate = manifest.get("generate") if isinstance(manifest.get("generate"), dict) else {}
        if isinstance(manifest_generate.get("git"), dict):
            git_info = manifest_generate.get("git")
    return git_info if isinstance(git_info, dict) else {}


def final_git_consistency_errors(payload: dict[str, Any], project_dir: Path | None, session_dir: Path | None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if project_dir is None or not (project_dir / ".git").exists():
        return errors
    head = git_head(project_dir)
    if not head:
        return errors
    git_info = recorded_generate_git(payload)
    recorded_commit = git_info.get("commit")
    if not isinstance(recorded_commit, str) or not recorded_commit.strip():
        errors.append(
            {
                "code": "GIT_COMMIT_MISSING",
                "accepted_locations": ["payload.generate.git.commit", "payload.manifest_content.generate.git.commit"],
                "message": (
                    "the recorded generate git commit must equal the final project HEAD; record it at "
                    "payload.generate.git.commit. manifest_content.generate.git.commit is also read."
                ),
            }
        )
    elif recorded_commit != head:
        errors.append(
            {
                "code": "GIT_COMMIT_NOT_HEAD",
                "recorded": recorded_commit,
                "head": head,
                "message": (
                    "the recorded generate git commit must equal the final project HEAD "
                    "(payload.generate.git.commit; manifest_content.generate.git.commit is also read)"
                ),
            }
        )
    disk_session_dir = session_dir or infer_session_dir(project_dir)
    if disk_session_dir is not None:
        state_path = disk_session_dir / SESSION_STATE_FILE
        if state_path.exists():
            try:
                state = load_json(state_path)
            except json.JSONDecodeError:
                return errors
            state_commit = state.get("git_commit") if isinstance(state, dict) else None
            if state_commit != head:
                errors.append(
                    {
                        "code": "SESSION_STATE_GIT_COMMIT_NOT_HEAD",
                        "recorded": state_commit,
                        "head": head,
                        "message": "disk session_state.git_commit must record the final project HEAD",
                    }
                )
    return errors


def git_commit_errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    git_info = recorded_generate_git(payload)
    commit = git_info.get("commit")
    if not isinstance(commit, str) or not commit.strip():
        errors.append(
            {
                "code": "GIT_COMMIT_MISSING",
                "accepted_locations": ["payload.generate.git.commit", "payload.manifest_content.generate.git.commit"],
                "message": (
                    "generate success must record the commit sha at payload.generate.git.commit "
                    "(manifest_content.generate.git.commit is also read) after all quality gates pass"
                ),
            }
        )
    if git_info.get("committed") is False:
        errors.append(
            {
                "code": "GIT_COMMIT_FALSE",
                "reason": git_info.get("reason"),
                "message": "success cannot record committed=false",
            }
        )
    status = str(git_info.get("status", "")).lower()
    reason = str(git_info.get("reason", "")).lower()
    bad_markers = {"failed", "skipped", "not_a_git_repository", "permission_required_or_dry_run", "permission_denied", "dry_run"}
    if status in bad_markers or reason in bad_markers:
        errors.append(
            {
                "code": "GIT_COMMIT_NOT_COMPLETED",
                "status": git_info.get("status"),
                "reason": git_info.get("reason"),
                "message": "success requires a completed git commit; otherwise emit partial with next_phase=null",
            }
        )
    permissions = payload.get("permissions")
    if not isinstance(permissions, list):
        errors.append(
            {
                "code": "PERMISSIONS_MISSING",
                "accepted_container": "list",
                "accepted_types": sorted(GIT_PERMISSION_TYPES),
                "expected_entry": {"type": "git_commit", "approved": True},
                "source_of_truth": "copy the shape from sample/phase_complete.upy_generate_plugin.success.json payload.permissions",
                "message": (
                    "payload.permissions must be a list of permission decision objects, each carrying a "
                    '"type" field; a dict keyed by permission type is rejected. success requires at least '
                    "one entry whose type is one of "
                    + ", ".join(sorted(GIT_PERMISSION_TYPES))
                    + ' with approved=true, e.g. [{"type": "git_commit", "approved": true}]'
                ),
            }
        )
    else:
        git_permissions = [
            item
            for item in permissions
            if isinstance(item, dict) and item.get("type") in GIT_PERMISSION_TYPES
        ]
        if not git_permissions:
            errors.append(
                {
                    "code": "GIT_PERMISSION_RECORD_MISSING",
                    # The filter above accepts exactly two type values and the message named
                    # neither, so "record the git commit permission decision" left the model
                    # guessing the shape of an entry it had never seen.
                    "accepted_types": sorted(GIT_PERMISSION_TYPES),
                    "expected_entry": {"type": "git_commit", "approved": True},
                    "message": (
                        "success must record the git commit permission decision in payload.permissions[]: "
                        "an entry whose type is one of " + ", ".join(sorted(GIT_PERMISSION_TYPES))
                        + ', e.g. {"type": "git_commit", "approved": true}'
                    ),
                }
            )
        elif not any(item.get("approved") is True for item in git_permissions):
            errors.append({"code": "GIT_PERMISSION_NOT_APPROVED", "message": "success requires an approved git commit permission record"})
    return errors


def git_head(project_dir: Path) -> str | None:
    result = run_cmd(["git", "rev-parse", "HEAD"], cwd=project_dir)
    if result["returncode"] == 0:
        return result["stdout"].strip()
    return None


def python_cache_errors(project_dir: Path) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for path in sorted(project_dir.rglob("*")):
        if path.name == "__pycache__" or path.suffix == ".pyc":
            try:
                rel_path = path.relative_to(project_dir).as_posix()
            except ValueError:
                rel_path = str(path)
            errors.append(
                {
                    "code": "PROJECT_PYTHON_CACHE_PRESENT",
                    "path": rel_path,
                    "message": "generate success must not leave __pycache__ or .pyc files in the project tree",
                }
            )
    if (project_dir / ".git").exists():
        result = run_cmd(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=project_dir)
        if result["returncode"] == 0:
            for line in result["stdout"].splitlines():
                if is_python_cache_path(line):
                    errors.append(
                        {
                            "code": "GIT_TRACKED_PYTHON_CACHE_PRESENT",
                            "path": line,
                            "message": "generate git commit must not track __pycache__ or .pyc files",
                        }
                    )
        else:
            errors.append(
                {
                    "code": "GIT_TREE_INSPECT_FAILED",
                    "returncode": result["returncode"],
                    "message": result["stderr"] or result["stdout"],
                }
            )
    return errors


def validate_phase_complete(
    phase_complete: dict[str, Any],
    project_dir: Path | None,
    strict_pylint: bool,
    phase_complete_path: Path | None = None,
    session_dir: Path | None = None,
    upstream_phase_complete_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    payload = phase_complete.get("payload")
    if not isinstance(payload, dict):
        errors.append({"code": "PAYLOAD_MISSING", "message": "phase_complete.payload must be an object"})
        payload = {}
    if phase_complete.get("type") != "phase_complete":
        errors.append({"code": "TYPE_NOT_PHASE_COMPLETE", "message": "envelope.type must be phase_complete"})
    if phase_complete.get("phase") != "upy-generate-plugin":
        errors.append({"code": "PHASE_NOT_GENERATE_PLUGIN", "message": "envelope.phase must be upy-generate-plugin"})
    payload_result = payload.get("result")
    if payload_result == "success":
        if payload.get("structured_errors"):
            errors.append({"code": "SUCCESS_HAS_STRUCTURED_ERRORS", "message": "structured_errors must be empty on success"})
        if payload.get("next_phase") not in ("upy-deploy-plugin", "upy-simulate-plugin", None):
            errors.append(
                {
                    "code": "NEXT_PHASE_INVALID",
                    "next_phase": payload.get("next_phase"),
                    "message": "next_phase must be deploy, simulate, or null",
                }
            )
        errors.extend(next_phase_decision_errors(payload))
        errors.extend(collect_gate_errors(payload, strict_pylint, project_dir))
        errors.extend(manifest_errors(payload, project_dir))
        errors.extend(upstream_hardware_boundary_errors(payload, phase_complete_path, project_dir, session_dir, upstream_phase_complete_path))
        errors.extend(deploy_tool_compat_errors(project_dir, payload.get("next_phase")))
        errors.extend(file_manifest_errors(payload))
        errors.extend(session_state_check_errors(payload, phase_complete_path, project_dir, session_dir))
        errors.extend(optional_next_phase_errors(payload))
        errors.extend(git_commit_errors(payload))
        errors.extend(final_git_consistency_errors(payload, project_dir, session_dir))
        if project_dir is not None:
            errors.extend(python_cache_errors(project_dir))
    elif payload_result in ("partial", "failed"):
        if payload.get("next_phase") is not None:
            errors.append({"code": "NON_SUCCESS_HAS_NEXT_PHASE", "message": "partial/failed phase_complete must set next_phase=null"})
        if not payload.get("structured_errors"):
            warnings.append({"code": "NON_SUCCESS_WITHOUT_STRUCTURED_ERRORS", "message": "partial/failed should include structured_errors"})
    else:
        errors.append({"code": "RESULT_INVALID", "result": payload_result, "message": "payload.result must be success, partial, or failed"})
    return {
        "check": "phase_complete_consistency",
        "phase": phase_complete.get("phase"),
        "result": "success" if not errors else "failed",
        "payload_result": payload_result,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Validate upy-generate-plugin phase_complete consistency")
    parser.add_argument("--phase-complete", required=True)
    parser.add_argument("--project-dir", default="")
    parser.add_argument("--session-dir", default="")
    parser.add_argument(
        "--upstream-phase-complete",
        default="",
        help="Optional scaffold/select-hw/flash phase_complete used as the immutable hardware baseline.",
    )
    parser.add_argument("--strict-pylint", action="store_true", help="Fail on any nonzero pylint exit code")
    args = parser.parse_args()
    phase_complete_path = Path(args.phase_complete)
    phase_complete = load_json(phase_complete_path)
    project_dir = Path(args.project_dir) if args.project_dir else None
    result = validate_phase_complete(
        phase_complete,
        project_dir,
        strict_pylint=args.strict_pylint,
        phase_complete_path=phase_complete_path,
        session_dir=Path(args.session_dir) if args.session_dir else None,
        upstream_phase_complete_path=Path(args.upstream_phase_complete) if args.upstream_phase_complete else None,
    )
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
