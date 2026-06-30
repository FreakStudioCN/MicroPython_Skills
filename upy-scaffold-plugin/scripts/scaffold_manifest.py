#!/usr/bin/env python3
"""Validate upy-scaffold-plugin phase_complete JSON files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PHASE = "upy-scaffold-plugin"
FLAKE8_LINE_RE = re.compile(r"^[^:\n]+:\d+:\d+:\s+[A-Z]\d{3}\b", re.MULTILINE)


def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def artifact_paths(artifacts: Any) -> list[str]:
    paths: list[str] = []
    if not isinstance(artifacts, list):
        return paths
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("path")
        if isinstance(path, str):
            paths.append(path.replace("\\", "/"))
        for item in artifact.get("files") or []:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                paths.append(item["path"].replace("\\", "/"))
    return paths


def has_artifact_type(artifacts: Any, artifact_type: str) -> bool:
    return isinstance(artifacts, list) and any(
        isinstance(item, dict) and item.get("type") == artifact_type for item in artifacts
    )


def lint_has_violations(lint: Any) -> bool:
    if not isinstance(lint, dict):
        return False
    stdout = str(lint.get("stdout") or "")
    stderr = str(lint.get("stderr") or "")
    return bool(FLAKE8_LINE_RE.search(stdout) or FLAKE8_LINE_RE.search(stderr))


def validate_phase_complete(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    result = payload.get("result")
    artifacts = payload.get("artifacts")
    structured_errors = payload.get("structured_errors")
    lint = payload.get("lint")
    require(data.get("type") == "phase_complete", errors, "type must be phase_complete")
    require(data.get("phase") == PHASE, errors, f"phase must be {PHASE}")
    require(payload.get("phase") in {"scaffold", PHASE}, errors, "payload.phase must be scaffold or upy-scaffold-plugin")
    require(result in {"success", "partial", "failed"}, errors, "payload.result is invalid")
    require(isinstance(artifacts, list), errors, "payload.artifacts must be a list")
    require(isinstance(payload.get("file_manifest"), dict), errors, "payload.file_manifest object is required")
    require(has_artifact_type(artifacts, "file_manifest"), errors, "payload.artifacts must include file_manifest")
    if result == "success":
        require(not structured_errors, errors, "success payload.structured_errors must be empty")
        require(payload.get("next_phase") == "upy-generate-plugin", errors, "success next_phase must be upy-generate-plugin")
        require(isinstance(lint, dict), errors, "success payload.lint object is required")
        if isinstance(lint, dict):
            require(lint.get("returncode") == 0, errors, "success lint.returncode must be 0")
            require(not lint_has_violations(lint), errors, "success lint stdout/stderr must not contain flake8 violations")
        paths = artifact_paths(artifacts)
        require(any(path.endswith("scaffold_file_manifest.json") for path in paths), errors, "success artifacts must reference scaffold_file_manifest.json")
    elif result in {"partial", "failed"}:
        require(payload.get("next_phase") is None, errors, "partial/failed next_phase must be null")
        require(bool(structured_errors), errors, "partial/failed should include structured_errors")
    return {"status": "ok" if not errors else "failed", "errors": errors}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--validate-phase-complete", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    data = load_json(args.input)
    result = validate_phase_complete(data) if args.validate_phase_complete else {
        "status": "failed",
        "errors": ["choose a validation mode"],
    }
    print_json(result)
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
