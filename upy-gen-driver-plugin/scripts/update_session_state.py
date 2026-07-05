#!/usr/bin/env python3
"""Create, update, or validate upy-gen-driver-plugin session state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_FILE = "session_state.upy_gen_driver_plugin.json"
PHASE = "upy-gen-driver-plugin"
CHECKPOINTS = {
    "started",
    "input_collected",
    "source_preprocessed",
    "understanding_written",
    "debug_driver_written",
    "hardware_verify_ready",
    "hardware_verify_passed",
    "production_driver_written",
    "normalized",
    "standalone_assets_written",
    "standalone_test_passed",
    "manifest_updated",
    "phase_completed",
    "cancelled",
    "verification_exhausted",
}
STATUSES = {"running", "retrying", "partial", "success", "failed", "cancelled"}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("JSON must be an object")
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


def parse_json(value: str, field: str, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} must be valid JSON: {exc}") from exc


def update(args: argparse.Namespace) -> dict[str, Any]:
    session_dir = Path(args.session_dir)
    state_path = session_dir / STATE_FILE
    state = load_json(state_path)
    if args.checkpoint not in CHECKPOINTS:
        raise ValueError(f"unknown checkpoint: {args.checkpoint}")
    if args.status not in STATUSES:
        raise ValueError(f"unknown status: {args.status}")
    ts = now()
    artifacts = parse_json(args.artifacts, "artifacts", [])
    permissions = parse_json(args.permissions, "permissions", [])
    error = parse_json(args.error, "error", None)
    events = state.get("events")
    if not isinstance(events, list):
        events = []
    event = {
        "timestamp": ts,
        "checkpoint": args.checkpoint,
        "step": args.step,
        "status": args.status,
        "idempotency_key": args.idempotency_key,
    }
    if args.retry_of:
        event["retry_of"] = args.retry_of
    if error:
        event["error"] = error
    events.append(event)
    manifest_hash = args.manifest_hash or state.get("manifest_hash") or "unknown"
    if args.project_dir:
        manifest = Path(args.project_dir) / "project-manifest.json"
        if manifest.exists():
            manifest_hash = sha256_file(manifest)
    state.update({
        "protocol_version": "1.0",
        "session_id": args.session_id or state.get("session_id") or session_dir.name,
        "phase": PHASE,
        "domain_phase": "gen-driver",
        "status": args.status,
        "checkpoint": args.checkpoint,
        "step": args.step,
        "idempotency_key": args.idempotency_key,
        "retry_of": args.retry_of or state.get("retry_of"),
        "manifest_hash": manifest_hash,
        "updated_at": ts,
        "artifacts": artifacts or state.get("artifacts", []),
        "permissions": permissions or state.get("permissions", []),
        "last_ok_artifact": (artifacts[-1] if artifacts else state.get("last_ok_artifact")),
        "events": events[-200:],
    })
    if "created_at" not in state:
        state["created_at"] = ts
    if error:
        state["last_error"] = error
    write_json(state_path, state)
    return {"ok": True, "path": str(state_path), "state": state}


def check(args: argparse.Namespace) -> dict[str, Any]:
    state_path = Path(args.session_dir) / STATE_FILE
    errors: list[str] = []
    if not state_path.exists():
        return {"ok": False, "errors": ["session state missing"], "path": str(state_path)}
    try:
        state = load_json(state_path)
    except Exception as exc:
        return {"ok": False, "errors": [str(exc)], "path": str(state_path)}
    for field in ("protocol_version", "session_id", "phase", "domain_phase", "status", "checkpoint", "step", "idempotency_key"):
        if not state.get(field):
            errors.append(f"missing {field}")
    if state.get("protocol_version") != "1.0":
        errors.append("protocol_version must be 1.0")
    if state.get("phase") != PHASE:
        errors.append(f"phase must be {PHASE}")
    key = state.get("idempotency_key")
    if isinstance(key, str) and not key.startswith(f"{PHASE}:"):
        errors.append(f"idempotency_key must start with {PHASE}:")
    if state.get("checkpoint") not in CHECKPOINTS:
        errors.append("checkpoint is not recognized")
    if state.get("status") not in STATUSES:
        errors.append("status is not recognized")
    return {"ok": not errors, "errors": errors, "path": str(state_path), "state": state}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--project-dir")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--checkpoint", default="started")
    parser.add_argument("--step", default="start")
    parser.add_argument("--status", default="running")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--retry-of", default="")
    parser.add_argument("--manifest-hash", default="")
    parser.add_argument("--artifacts", default="")
    parser.add_argument("--permissions", default="")
    parser.add_argument("--error", default="")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        result = check(args) if args.check else update(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
