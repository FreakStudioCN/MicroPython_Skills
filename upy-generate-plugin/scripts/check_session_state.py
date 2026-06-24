#!/usr/bin/env python3
"""Detect stale upy-generate-plugin artifacts before resume/regenerate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


GENERATE_PHASE_FILE = "phase_complete.upy_generate_plugin.json"
GENERATE_LOG_FILE = "generate_phase_log.md"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def git_status(project_dir: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=project_dir,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "clean": result.returncode == 0 and not result.stdout.strip(),
    }


def rel_exists(project_dir: Path, rel_path: str) -> bool:
    if not isinstance(rel_path, str) or not rel_path:
        return False
    rel = Path(rel_path)
    if rel.is_absolute() or rel.drive or ".." in rel.parts:
        return False
    return (project_dir / rel).exists()


def manifest_phase(project_dir: Path) -> str | None:
    path = project_dir / "project-manifest.json"
    if not path.exists():
        return None
    try:
        manifest = load_json(path)
    except json.JSONDecodeError:
        return None
    if isinstance(manifest, dict):
        phase = manifest.get("phase")
        return phase if isinstance(phase, str) else None
    return None


def phase_complete_file_paths(phase_complete: dict[str, Any]) -> list[str]:
    payload = phase_complete.get("payload") if isinstance(phase_complete.get("payload"), dict) else {}
    file_manifest = payload.get("file_manifest") if isinstance(payload.get("file_manifest"), dict) else {}
    files = file_manifest.get("files") if isinstance(file_manifest.get("files"), list) else []
    paths: list[str] = []
    for item in files:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.append(item["path"])
    return paths


def stale_errors(session_dir: Path, project_dir: Path, phase_path: Path) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not phase_path.exists():
        return errors
    try:
        phase_complete = load_json(phase_path)
    except json.JSONDecodeError as exc:
        return [
            {
                "code": "PREVIOUS_GENERATE_PHASE_JSON_INVALID",
                "path": str(phase_path),
                "message": str(exc),
            }
        ]
    payload = phase_complete.get("payload") if isinstance(phase_complete.get("payload"), dict) else {}
    result = payload.get("result")
    project_phase = manifest_phase(project_dir)
    plan_exists = (project_dir / "generate_plan.json").exists()
    if result == "success" and project_phase != "generate":
        errors.append(
            {
                "code": "STALE_GENERATE_PHASE_COMPLETE",
                "path": str(phase_path),
                "project_phase": project_phase,
                "message": "previous generate phase_complete says success but project-manifest.json is not phase=generate",
            }
        )
    if result == "success" and not plan_exists:
        errors.append(
            {
                "code": "STALE_GENERATE_PLAN_MISSING",
                "path": str(project_dir / "generate_plan.json"),
                "message": "previous generate success is stale because generate_plan.json is missing",
            }
        )
    missing_files = [
        path
        for path in phase_complete_file_paths(phase_complete)
        if path not in {"project-manifest.json"} and not rel_exists(project_dir, path)
    ]
    if result == "success" and missing_files:
        errors.append(
            {
                "code": "STALE_GENERATE_FILE_MANIFEST_MISSING_FILES",
                "missing_count": len(missing_files),
                "missing_sample": missing_files[:20],
                "message": "previous generate file_manifest lists files that are absent from the current project tree",
            }
        )
    if errors and (session_dir / GENERATE_LOG_FILE).exists():
        errors.append(
            {
                "code": "STALE_GENERATE_LOG_PRESENT",
                "path": str(session_dir / GENERATE_LOG_FILE),
                "message": "generate_phase_log.md belongs to a stale generate attempt and should be archived with the stale phase_complete",
            }
        )
    return errors


def check_session(session_dir: Path, project_dir: Path | None = None) -> dict[str, Any]:
    project = project_dir or session_dir / "project"
    phase_path = session_dir / GENERATE_PHASE_FILE
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not session_dir.exists():
        errors.append({"code": "SESSION_DIR_MISSING", "path": str(session_dir), "message": "session directory is missing"})
    if not project.exists():
        errors.append({"code": "PROJECT_DIR_MISSING", "path": str(project), "message": "project directory is missing"})
    if errors:
        return {
            "check": "session_state",
            "session_dir": str(session_dir),
            "project_dir": str(project),
            "errors": errors,
            "warnings": warnings,
            "ok": False,
        }
    errors.extend(stale_errors(session_dir, project, phase_path))
    status = git_status(project)
    if status["returncode"] == 0:
        warnings.append(
            {
                "code": "PROJECT_GIT_DIRTY",
                "message": "project git working tree is dirty",
                "details": status["stdout"].strip().splitlines(),
            }
        ) if not status["clean"] else None
    else:
        warnings.append(
            {
                "code": "PROJECT_NOT_GIT_REPOSITORY",
                "message": "project is not a git repository yet; success must initialize/commit or emit partial",
                "details": status["stderr"].strip(),
            }
        )
    return {
        "check": "session_state",
        "session_dir": str(session_dir),
        "project_dir": str(project),
        "phase_complete": str(phase_path),
        "project_phase": manifest_phase(project),
        "generate_plan_exists": (project / "generate_plan.json").exists(),
        "previous_generate_phase_exists": phase_path.exists(),
        "git": status,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Check upy-generate-plugin session/project state before resume")
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--project-dir", default="")
    args = parser.parse_args()
    session_dir = Path(args.session_dir)
    project_dir = Path(args.project_dir) if args.project_dir else None
    result = check_session(session_dir, project_dir)
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
