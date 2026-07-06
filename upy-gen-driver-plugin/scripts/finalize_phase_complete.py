#!/usr/bin/env python3
"""Finalize upy-gen-driver-plugin phase_complete file manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


PHASE_COMPLETE_FILE = "phase_complete.upy_gen_driver_plugin.json"
STATE_FILE = "session_state.upy_gen_driver_plugin.json"
HASHED_FILE_STATUSES = {"created", "updated", "unchanged"}


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("phase_complete must be a JSON object")
    return data


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_relative_path(value: str) -> str:
    if not value or os.path.isabs(value) or (len(value) > 1 and value[1] == ":"):
        raise ValueError(f"manifest path must be relative: {value}")
    parts = Path(value).parts
    if ".." in parts:
        raise ValueError(f"manifest path must not contain '..': {value}")
    return Path(value.replace("\\", "/")).as_posix()


def relative_to_root(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside artifact_root: {path}") from exc


def resolve_manifest_path(root: Path, relative_path: str) -> Path:
    rel = normalize_relative_path(relative_path)
    return root / Path(rel.replace("/", os.sep))


def ensure_session_state_entry(payload: dict[str, Any], root: Path, session_state: Path) -> None:
    if not session_state.exists():
        raise FileNotFoundError(f"session_state file does not exist: {session_state}")
    state_rel = relative_to_root(root, session_state)
    checkpoint = payload.get("checkpoint")
    if isinstance(checkpoint, dict) and not checkpoint.get("state_file"):
        checkpoint["state_file"] = state_rel
    manifest = payload.setdefault("file_manifest", {})
    files = manifest.setdefault("files", [])
    if not isinstance(files, list):
        raise ValueError("payload.file_manifest.files must be an array")
    for entry in files:
        if isinstance(entry, dict) and entry.get("path") == state_rel:
            entry.setdefault("role", "state")
            entry.setdefault("status", "created")
            return
    files.append({"path": state_rel, "status": "created", "role": "state"})


def dedupe_entries(files: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(f"file_manifest.files[{index}] must be an object")
        path = item.get("path")
        if not isinstance(path, str):
            raise ValueError(f"file_manifest.files[{index}].path must be a string")
        normalized_path = normalize_relative_path(path)
        item["path"] = normalized_path
        if normalized_path in seen:
            continue
        seen.add(normalized_path)
        deduped.append(item)
    return deduped


def refresh_file_manifest(data: dict[str, Any], artifact_root: Path, output_path: Path) -> None:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    manifest = payload.setdefault("file_manifest", {})
    if not isinstance(manifest, dict):
        raise ValueError("payload.file_manifest must be an object")
    files = manifest.setdefault("files", [])
    if not isinstance(files, list):
        raise ValueError("payload.file_manifest.files must be an array")
    manifest["files"] = dedupe_entries(files)
    output_rel: str | None = None
    try:
        output_rel = relative_to_root(artifact_root, output_path)
    except ValueError:
        output_rel = None
    for index, item in enumerate(manifest["files"]):
        path = item["path"]
        if output_rel and path == output_rel:
            raise ValueError("phase_complete must not include a hash entry for itself")
        if item.get("role") == "phase_complete":
            raise ValueError("phase_complete role belongs in an external sidecar manifest, not payload.file_manifest")
        item.pop("hash", None)
        status = item.setdefault("status", "created")
        if status in HASHED_FILE_STATUSES:
            resolved = resolve_manifest_path(artifact_root, path)
            if not resolved.exists():
                raise FileNotFoundError(f"file_manifest.files[{index}].path does not exist: {path}")
            item["sha256"] = sha256_file(resolved)
            item["bytes"] = resolved.stat().st_size


def validate_output(output_path: Path, artifact_root: Path, session_state: Path | None) -> list[str]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_phase_complete import load, validate  # pylint: disable=import-outside-toplevel

    data = load(output_path)
    _, errors = validate(
        data,
        artifact_root=artifact_root,
        session_state_path=session_state,
        input_path=output_path,
    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Draft phase_complete JSON path.")
    parser.add_argument("--output", required=True, help=f"Final {PHASE_COMPLETE_FILE} path.")
    parser.add_argument("--artifact-root", required=True, help="Root used to resolve manifest paths.")
    parser.add_argument("--session-state", help=f"Final {STATE_FILE} path.")
    parser.add_argument("--no-validate", action="store_true", help="Write output without running validate_phase_complete.py.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    artifact_root = Path(args.artifact_root)
    session_state = Path(args.session_state) if args.session_state else None

    try:
        data = load_json(input_path)
        payload = data.setdefault("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if session_state:
            ensure_session_state_entry(payload, artifact_root, session_state)
        refresh_file_manifest(data, artifact_root, output_path)
        write_json(output_path, data)
        errors: list[str] = []
        if not args.no_validate:
            errors = validate_output(output_path, artifact_root, session_state)
        result = {
            "ok": not errors,
            "output": str(output_path),
            "manifest_count": len(data.get("payload", {}).get("file_manifest", {}).get("files", [])),
            "errors": errors,
        }
    except Exception as exc:
        result = {"ok": False, "output": str(output_path), "errors": [str(exc)]}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
