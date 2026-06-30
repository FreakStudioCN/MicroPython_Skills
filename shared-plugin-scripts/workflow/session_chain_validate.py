#!/usr/bin/env python3
"""Validate a MicroPython plugin workflow session artifact chain."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
PHASE_FILES = {
    "analyze": "phase_complete.analyze.json",
    "select_hw": "phase_complete.select_hw.json",
    "flash": "phase_complete.upy_flash_mpy_firmware_plugin.json",
    "scaffold": "phase_complete.upy_scaffold_plugin.json",
    "generate": "phase_complete.upy_generate_plugin.json",
    "deploy": "phase_complete.upy_deploy_plugin.json",
}
PHASE_VALIDATORS = {
    "scaffold": [REPO / "upy-scaffold-plugin" / "scripts" / "scaffold_manifest.py", "--validate-phase-complete"],
    "generate": [REPO / "upy-generate-plugin" / "scripts" / "check_phase_complete_consistency.py"],
    "deploy": [REPO / "upy-deploy-plugin" / "scripts" / "deploy_manifest.py", "--validate-phase-complete"],
}
FORBIDDEN_PROJECT_ROOT_FILES = {"-"}
FORBIDDEN_PROJECT_SUFFIXES = {".pyc"}
FORBIDDEN_PROJECT_DIR_NAMES = {"__pycache__"}


def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def rel_or_abs(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def run_validator(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, *cmd],
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    payload: Any = None
    if completed.stdout.strip().startswith("{"):
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = None
    return {
        "command": " ".join([sys.executable, *cmd]),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "payload": payload,
    }


def get_payload(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload")
    return payload if isinstance(payload, dict) else {}


def runtime_session_root(payload: dict[str, Any]) -> str:
    runtime = payload.get("runtime_context")
    if isinstance(runtime, dict) and isinstance(runtime.get("session_root"), str):
        return runtime["session_root"].replace("\\", "/")
    return ""


def runtime_project_root(payload: dict[str, Any]) -> str:
    runtime = payload.get("runtime_context")
    if isinstance(runtime, dict) and isinstance(runtime.get("project_root"), str):
        return runtime["project_root"].replace("\\", "/")
    return ""


def check_phase_file(
    phase: str,
    path: Path,
    session_dir: Path,
    project_dir: Path | None,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    data = load_json(path)
    payload = get_payload(data)
    if payload.get("result") == "success" and payload.get("structured_errors"):
        errors.append(
            {
                "code": "SUCCESS_HAS_STRUCTURED_ERRORS",
                "phase": phase,
                "path": str(path),
                "message": "phase_complete success must not contain structured_errors",
            }
        )
    recorded_session = data.get("session_id")
    if isinstance(recorded_session, str) and recorded_session and recorded_session != session_dir.name:
        errors.append(
            {
                "code": "SESSION_ID_MISMATCH",
                "phase": phase,
                "recorded": recorded_session,
                "expected": session_dir.name,
                "message": "phase_complete.session_id must match the workflow session directory",
            }
        )
    rt_session = runtime_session_root(payload)
    if rt_session and not rt_session.endswith(session_dir.name):
        errors.append(
            {
                "code": "RUNTIME_SESSION_ROOT_MISMATCH",
                "phase": phase,
                "runtime_session_root": rt_session,
                "expected_suffix": session_dir.name,
                "message": "runtime_context.session_root must point to the workflow session",
            }
        )
    rt_project = runtime_project_root(payload)
    if rt_project and project_dir is not None and not rt_project.endswith(f"{session_dir.name}/project"):
        errors.append(
            {
                "code": "RUNTIME_PROJECT_ROOT_MISMATCH",
                "phase": phase,
                "runtime_project_root": rt_project,
                "expected_suffix": f"{session_dir.name}/project",
                "message": "runtime_context.project_root must point to the workflow session project",
            }
        )
    if not rt_session and phase in {"scaffold", "generate", "deploy"}:
        warnings.append(
            {
                "code": "RUNTIME_CONTEXT_SESSION_ROOT_MISSING",
                "phase": phase,
                "path": str(path),
                "message": "runtime_context.session_root missing; older artifacts may be harder to validate",
            }
        )
    return data


def validate_phase_with_plugin(phase: str, path: Path, session_dir: Path, project_dir: Path | None) -> dict[str, Any] | None:
    spec = PHASE_VALIDATORS.get(phase)
    if not spec:
        return None
    script = spec[0]
    if phase == "generate":
        cmd = [str(script), "--phase-complete", str(path)]
        if project_dir is not None:
            cmd.extend(["--project-dir", str(project_dir)])
        cmd.extend(["--session-dir", str(session_dir)])
    else:
        cmd = [str(script), *spec[1:], "--input", str(path)]
    return run_validator(cmd)


def forbidden_project_artifacts(project_dir: Path) -> list[str]:
    if not project_dir.exists():
        return []
    bad: list[str] = []
    for path in sorted(project_dir.rglob("*")):
        rel = rel_or_abs(path, project_dir)
        if path.parent == project_dir and path.name in FORBIDDEN_PROJECT_ROOT_FILES:
            bad.append(rel)
        if path.name in FORBIDDEN_PROJECT_DIR_NAMES:
            bad.append(rel)
        if path.is_file() and path.suffix in FORBIDDEN_PROJECT_SUFFIXES:
            bad.append(rel)
    return bad


def validate_session(session_dir: Path, project_dir: Path | None, require_deploy: bool) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    phases: dict[str, dict[str, Any]] = {}
    actual_project_dir = project_dir or session_dir / "project"
    for phase, filename in PHASE_FILES.items():
        path = session_dir / filename
        if not path.exists():
            if phase == "deploy" and not require_deploy:
                continue
            errors.append(
                {
                    "code": "PHASE_FILE_MISSING",
                    "phase": phase,
                    "path": str(path),
                    "message": "expected phase_complete artifact is missing",
                }
            )
            continue
        phases[phase] = check_phase_file(phase, path, session_dir, actual_project_dir, errors, warnings)
        validator = validate_phase_with_plugin(phase, path, session_dir, actual_project_dir)
        if validator and validator["returncode"] != 0:
            errors.append(
                {
                    "code": "PHASE_VALIDATOR_FAILED",
                    "phase": phase,
                    "path": str(path),
                    "validator": validator,
                    "message": f"{phase} phase_complete failed its plugin validator",
                }
            )
    bad_project_artifacts = forbidden_project_artifacts(actual_project_dir)
    if bad_project_artifacts:
        errors.append(
            {
                "code": "PROJECT_TEMP_ARTIFACT_PRESENT",
                "project_dir": str(actual_project_dir),
                "paths": bad_project_artifacts,
                "message": "project root contains transient or Python cache artifacts",
            }
        )
    return {
        "check": "session_chain",
        "session_dir": str(session_dir),
        "project_dir": str(actual_project_dir),
        "phases_checked": sorted(phases),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--project-dir", default="")
    parser.add_argument("--require-deploy", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    session_dir = Path(args.session_dir).resolve()
    project_dir = Path(args.project_dir).resolve() if args.project_dir else None
    result = validate_session(session_dir, project_dir, args.require_deploy)
    print_json(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
