#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path


PROTOCOL_VERSION = "mpos-robot-skill/v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STAGES = {"analyze", "prepare_deps", "generate", "test", "package", "deploy", "publish_check"}


class SessionError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            value.update(chunk)
    return value.hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_session_id(value):
    if not SAFE_ID.match(value):
        raise SessionError("SESSION_ID_INVALID", "session_id contains unsupported characters")


def session_paths(session):
    return {
        "state": session / "session_state.json",
        "manifest": session / "artifact_manifest.json",
        "receipts": session / "operation_receipts.json",
        "checkpoints": session / "checkpoints",
        "results": session / "results",
    }


def require_session(path):
    session = Path(path).resolve()
    paths = session_paths(session)
    if not paths["state"].is_file():
        raise SessionError("SESSION_NOT_FOUND", "Session state does not exist", {"session": str(session)})
    return session, paths, load_json(paths["state"])


def initialize(root, session_id, input_value):
    validate_session_id(session_id)
    session = Path(root).resolve() / session_id
    paths = session_paths(session)
    input_hash = digest(input_value)
    if paths["state"].exists():
        state = load_json(paths["state"])
        if state.get("input_hash") != input_hash:
            raise SessionError("SESSION_INPUT_CONFLICT", "Existing Session has different normalized input")
        return {"ok": True, "created": False, "session": str(session), "state": state}
    session.mkdir(parents=True, exist_ok=False)
    paths["checkpoints"].mkdir()
    paths["results"].mkdir()
    state = {
        "protocol_version": PROTOCOL_VERSION,
        "session_id": session_id,
        "status": "created",
        "stage": "analyze",
        "input_hash": input_hash,
        "latest_checkpoint_id": None,
        "checkpoint_revision": 0,
        "cancel_requested": False,
        "created_at": now(),
        "updated_at": now(),
    }
    atomic_json(paths["state"], state)
    atomic_json(paths["manifest"], {"protocol_version": PROTOCOL_VERSION, "session_id": session_id, "revision": 0, "artifacts": []})
    atomic_json(paths["receipts"], {"protocol_version": PROTOCOL_VERSION, "session_id": session_id, "receipts": []})
    atomic_json(session / "normalized_input.json", input_value)
    return {"ok": True, "created": True, "session": str(session), "state": state}


def checkpoint(session_path, stage, result_value):
    session, paths, state = require_session(session_path)
    if stage not in STAGES:
        raise SessionError("PROTOCOL_STAGE_INVALID", "Cannot checkpoint an unknown stage", {"stage": stage})
    if state.get("protocol_version") != PROTOCOL_VERSION:
        raise SessionError("CHECKPOINT_INCOMPATIBLE", "Session protocol version is incompatible")
    if state.get("cancel_requested"):
        raise SessionError("OPERATION_CANCELLED", "Cancellation was requested before checkpoint commit")
    revision = int(state.get("checkpoint_revision", 0)) + 1
    checkpoint_id = "cp_%s_%04d" % (stage, revision)
    result_path = paths["results"] / (checkpoint_id + ".json")
    atomic_json(result_path, result_value)
    relative_result = result_path.relative_to(session).as_posix()
    artifact = {
        "artifact_id": "artifact_" + checkpoint_id,
        "kind": "stage_result",
        "role": stage,
        "path": relative_result,
        "mime": "application/json",
        "sha256": file_digest(result_path),
        "size": result_path.stat().st_size,
        "stage": stage,
        "revision": revision,
        "created_at": now(),
    }
    manifest = load_json(paths["manifest"])
    manifest["revision"] = revision
    manifest.setdefault("artifacts", []).append(artifact)
    atomic_json(paths["manifest"], manifest)
    checkpoint_value = {
        "protocol_version": PROTOCOL_VERSION,
        "session_id": state["session_id"],
        "checkpoint_id": checkpoint_id,
        "revision": revision,
        "stage": stage,
        "input_hash": state["input_hash"],
        "result_artifact_id": artifact["artifact_id"],
        "result_path": relative_result,
        "result_sha256": artifact["sha256"],
        "manifest_revision": manifest["revision"],
        "created_at": now(),
    }
    checkpoint_path = paths["checkpoints"] / (checkpoint_id + ".json")
    atomic_json(checkpoint_path, checkpoint_value)
    state["latest_checkpoint_id"] = checkpoint_id
    state["checkpoint_revision"] = revision
    state["stage"] = stage
    state["status"] = "completed" if stage == "publish_check" else "partial"
    state["updated_at"] = now()
    atomic_json(paths["state"], state)
    return {"ok": True, "session": str(session), "checkpoint": checkpoint_value, "artifact": artifact, "state": state}


def resume(session_path):
    session, paths, state = require_session(session_path)
    checkpoint_id = state.get("latest_checkpoint_id")
    if checkpoint_id is None:
        return {"ok": True, "session": str(session), "state": state, "checkpoint": None}
    checkpoint_path = paths["checkpoints"] / (checkpoint_id + ".json")
    if not checkpoint_path.is_file():
        raise SessionError("CHECKPOINT_CORRUPTED", "Latest checkpoint file is missing", {"checkpoint_id": checkpoint_id})
    value = load_json(checkpoint_path)
    if value.get("protocol_version") != PROTOCOL_VERSION or value.get("input_hash") != state.get("input_hash"):
        raise SessionError("CHECKPOINT_INCOMPATIBLE", "Checkpoint protocol or input hash does not match")
    result_path = session / value.get("result_path", "")
    try:
        result_path.resolve().relative_to(session)
    except ValueError as exc:
        raise SessionError("CHECKPOINT_CORRUPTED", "Checkpoint result path escapes the Session") from exc
    if not result_path.is_file() or file_digest(result_path) != value.get("result_sha256"):
        raise SessionError("CHECKPOINT_CORRUPTED", "Checkpoint result hash validation failed")
    return {"ok": True, "session": str(session), "state": state, "checkpoint": value, "result": load_json(result_path)}


def cancel(session_path):
    session, paths, state = require_session(session_path)
    state["cancel_requested"] = True
    state["status"] = "cancelled"
    state["updated_at"] = now()
    atomic_json(paths["state"], state)
    return {"ok": True, "session": str(session), "state": state}


def receipt(session_path, operation, idempotency_key, input_value, result_value):
    session, paths, state = require_session(session_path)
    input_hash = digest(input_value)
    ledger = load_json(paths["receipts"])
    for item in ledger.get("receipts", []):
        if item.get("operation") == operation and item.get("idempotency_key") == idempotency_key:
            if item.get("input_hash") != input_hash:
                raise SessionError("IDEMPOTENCY_CONFLICT", "Idempotency key was already used with different input")
            return {"ok": True, "reused": True, "session": str(session), "receipt": item}
    item = {
        "operation": operation,
        "idempotency_key": idempotency_key,
        "input_hash": input_hash,
        "result": result_value,
        "created_at": now(),
    }
    ledger.setdefault("receipts", []).append(item)
    atomic_json(paths["receipts"], ledger)
    state["updated_at"] = now()
    atomic_json(paths["state"], state)
    return {"ok": True, "reused": False, "session": str(session), "receipt": item}


def json_arg(value):
    if value == "-":
        return json.load(sys.stdin)
    path = Path(value)
    if path.is_file():
        return load_json(path)
    return json.loads(value)


def main():
    parser = argparse.ArgumentParser(description="Local mpos-robot-skill/v1 Session store")
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init")
    init_parser.add_argument("--root", required=True)
    init_parser.add_argument("--session-id", required=True)
    init_parser.add_argument("--input", required=True)
    checkpoint_parser = commands.add_parser("checkpoint")
    checkpoint_parser.add_argument("--session", required=True)
    checkpoint_parser.add_argument("--stage", required=True)
    checkpoint_parser.add_argument("--result", required=True)
    resume_parser = commands.add_parser("resume")
    resume_parser.add_argument("--session", required=True)
    cancel_parser = commands.add_parser("cancel")
    cancel_parser.add_argument("--session", required=True)
    receipt_parser = commands.add_parser("receipt")
    receipt_parser.add_argument("--session", required=True)
    receipt_parser.add_argument("--operation", required=True)
    receipt_parser.add_argument("--idempotency-key", required=True)
    receipt_parser.add_argument("--input", required=True)
    receipt_parser.add_argument("--result", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = initialize(args.root, args.session_id, json_arg(args.input))
        elif args.command == "checkpoint":
            result = checkpoint(args.session, args.stage, json_arg(args.result))
        elif args.command == "resume":
            result = resume(args.session)
        elif args.command == "cancel":
            result = cancel(args.session)
        else:
            result = receipt(args.session, args.operation, args.idempotency_key, json_arg(args.input), json_arg(args.result))
        exit_code = 0
    except SessionError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc), "details": exc.details}}
        exit_code = 1
    except Exception as exc:
        result = {"ok": False, "error": {"code": "SESSION_STORE_FAILED", "message": str(exc), "details": {}}}
        exit_code = 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
