#!/usr/bin/env python3
"""
Smoke tests for upy-analyze V0 protocol scaffolding.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "templates"
MOCK_DIR = SKILL_DIR / "mock-messages" / "analyze"
INIT_MANIFEST = SKILL_DIR / "scripts" / "init_manifest.py"
EXTERNAL_TEST_ROOT = Path("G:/test/test")
CORE_MANIFEST_FIELDS = [
    "schema_version",
    "phase",
    "project_name",
    "requirements",
    "devices",
    "final_status",
]


def run(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        cmd,
        cwd=str(SKILL_DIR),
        input=input_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalized_core(manifest: dict[str, Any]) -> dict[str, Any]:
    copy_manifest = dict(manifest)
    copy_manifest.setdefault("schema_version", "1.0")
    copy_manifest.setdefault("phase", "analyze")
    copy_manifest.setdefault("final_status", "pending")
    return {field: copy_manifest.get(field) for field in CORE_MANIFEST_FIELDS}


def check_json_files() -> None:
    paths = sorted(TEMPLATE_DIR.glob("*.json")) + sorted(MOCK_DIR.glob("*.json"))
    if not paths:
        raise AssertionError("no template/mock JSON files found")
    for path in paths:
        load_json(path)


def check_phase_complete_mocks() -> None:
    phase_complete_paths = sorted(MOCK_DIR.glob("phase_complete.*.json"))
    if not phase_complete_paths:
        raise AssertionError("no phase_complete mock files found")

    for path in phase_complete_paths:
        proc = run(
            [
                sys.executable,
                str(INIT_MANIFEST),
                "--validate-phase-complete",
                "--input",
                str(path),
            ]
        )
        if proc.returncode != 0:
            raise AssertionError(
                f"phase_complete mock rejected: {path}\nstdout={proc.stdout}\nstderr={proc.stderr}"
            )
        result = json.loads(proc.stdout)
        if result.get("status") != "ok":
            raise AssertionError(f"phase_complete mock validation inconsistent: {path}: {result}")


def check_manifest_validation() -> None:
    success = load_json(MOCK_DIR / "phase_complete.success.json")
    manifest = success["payload"]["manifest_content"]
    proc = run(
        [sys.executable, str(INIT_MANIFEST), "--stdin"],
        input_text=json.dumps(manifest, ensure_ascii=False),
    )
    if proc.returncode != 0:
        raise AssertionError(f"manifest validation failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    result = json.loads(proc.stdout)
    if result.get("status") != "ok":
        raise AssertionError(f"manifest validation inconsistent: {result}")


def check_compare_manifest() -> None:
    success_path = MOCK_DIR / "phase_complete.success.json"
    manifest = load_json(success_path)["payload"]["manifest_content"]
    proc = run(
        [sys.executable, str(INIT_MANIFEST), "--stdin"],
        input_text=json.dumps(manifest, ensure_ascii=False),
    )
    result = json.loads(proc.stdout)
    if result.get("status") != "ok":
        raise AssertionError(f"cannot build compare manifest: {result}")
    validated = result["manifest"]

    temp_path = TEST_DIR / "_tmp_manifest_validated.json"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(validated, f, ensure_ascii=False, indent=2)
        proc = run(
            [
                sys.executable,
                str(INIT_MANIFEST),
                "--validate-phase-complete",
                "--input",
                str(success_path),
                "--compare-manifest",
                str(temp_path),
            ]
        )
        if proc.returncode != 0:
            raise AssertionError(f"compare manifest failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    finally:
        if temp_path.exists():
            temp_path.unlink()


def candidate_external_session_dirs() -> list[Path]:
    sessions_root = EXTERNAL_TEST_ROOT / "sessions"
    if not sessions_root.exists():
        return []
    return sorted(path for path in sessions_root.iterdir() if path.is_dir())


def check_external_session_samples() -> None:
    if not EXTERNAL_TEST_ROOT.exists():
        print(f"[SKIP] external test root missing: {EXTERNAL_TEST_ROOT}")
        return

    session_dirs = candidate_external_session_dirs()
    if not session_dirs:
        print(f"[SKIP] no session-isolated external samples under: {EXTERNAL_TEST_ROOT / 'sessions'}")
        return

    for session_dir in session_dirs:
        manifest_draft = session_dir / "manifest_draft.json"
        manifest_validated = session_dir / "manifest_validated.json"
        phase_complete = session_dir / "phase_complete.analyze.json"
        driver_log = session_dir / "driver_search_log.md"
        for path in [manifest_draft, manifest_validated, phase_complete, driver_log]:
            if not path.exists():
                raise AssertionError(f"external session sample missing: {path}")

        for path in [manifest_draft, manifest_validated]:
            proc = run([sys.executable, str(INIT_MANIFEST), "--input", str(path)])
            if proc.returncode != 0:
                raise AssertionError(
                    f"manifest validation rejected external sample {path}:\n"
                    f"stdout={proc.stdout}\nstderr={proc.stderr}"
                )

        phase_data = load_json(phase_complete)
        payload = phase_data.get("payload", {})
        manifest_core = normalized_core(load_json(manifest_validated))
        payload_core = normalized_core(payload.get("manifest_content", {}))
        if manifest_core != payload_core:
            raise AssertionError(f"external manifest core mismatch in {session_dir}")

        declared_files: list[str] = []
        for artifact in payload.get("artifacts", []):
            if artifact.get("type") == "file_list":
                declared_files.extend(item.get("path") for item in artifact.get("files", []))

        required_declared = {
            "manifest_draft.json",
            "manifest_validated.json",
            "phase_complete.analyze.json",
            "driver_search_log.md",
        }
        missing = sorted(required_declared.difference(declared_files))
        if missing:
            raise AssertionError(f"external file_list missing required files in {session_dir}: {missing}")

        proc = run(
            [
                sys.executable,
                str(INIT_MANIFEST),
                "--validate-phase-complete",
                "--input",
                str(phase_complete),
                "--compare-manifest",
                str(manifest_validated),
                "--artifact-root",
                str(session_dir),
            ]
        )
        if proc.returncode != 0:
            raise AssertionError(
                f"phase_complete validation rejected external sample {phase_complete}:\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr}"
            )


def main() -> int:
    checks = [
        ("json files", check_json_files),
        ("manifest validation", check_manifest_validation),
        ("phase_complete mocks", check_phase_complete_mocks),
        ("manifest compare", check_compare_manifest),
        ("external session samples", check_external_session_samples),
    ]
    for name, check in checks:
        check()
        print(f"[OK] {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
