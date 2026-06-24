#!/usr/bin/env python3
"""Create or update resumable upy-generate-plugin session state."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


DEFAULT_STATE_FILE = "session_state.upy_generate_plugin.json"
KNOWN_ERROR_CODES = {
    "CANCELLED_BY_USER",
    "MODEL_CONTEXT_EXHAUSTED",
    "NETWORK_DISCONNECTED",
    "RATE_LIMITED",
    "TOKEN_BUDGET_EXCEEDED",
    "UPSTREAM_TIMEOUT",
}
RETRYABLE_CODES = {"NETWORK_DISCONNECTED", "RATE_LIMITED", "UPSTREAM_TIMEOUT"}
NON_RETRYABLE_CODES = {"CANCELLED_BY_USER", "MODEL_CONTEXT_EXHAUSTED", "TOKEN_BUDGET_EXCEEDED"}
USAGE_STATUSES = {"unknown", "ok", "exhausted"}
GIT_SHA40_LENGTH = 40


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("session state must be a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def parse_json_object(value: str, field: str) -> dict[str, Any]:
    if not value:
        return {}
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError(f"{field} must be a JSON object")
    return data


def parse_json_list(value: str, field: str) -> list[Any]:
    if not value:
        return []
    data = json.loads(value)
    if not isinstance(data, list):
        raise ValueError(f"{field} must be a JSON array")
    return data


def normalize_error(code: str, step: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    retryable = code in RETRYABLE_CODES
    if code in NON_RETRYABLE_CODES:
        retryable = False
    return {
        "code": code,
        "severity": "error",
        "phase_step": step,
        "retryable": retryable,
        "message": message or code.replace("_", " ").lower(),
        "details": details,
    }


def default_usage() -> dict[str, Any]:
    return {
        "token_budget_status": "unknown",
        "remaining_budget": None,
    }


def update_state(
    session_dir: Path,
    project_dir: Path | None,
    session_id: str,
    checkpoint: str,
    step: str,
    idempotency_key: str,
    status: str,
    attempt: int | None,
    artifacts: list[Any],
    error: dict[str, Any] | None,
    extra: dict[str, Any],
    manifest_hash: str,
    git_commit: str,
    usage: dict[str, Any],
) -> dict[str, Any]:
    state_path = session_dir / DEFAULT_STATE_FILE
    state = load_json(state_path)
    now = utc_now()
    previous_attempt = int(state.get("attempt", 0) or 0)
    attempt_value = attempt if attempt is not None else max(1, previous_attempt)
    if status == "retrying" and attempt is None:
        attempt_value = previous_attempt + 1
    events = state.get("events")
    if not isinstance(events, list):
        events = []
    previous_usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}
    usage_value = {**default_usage(), **previous_usage, **usage}
    computed_manifest_hash = ""
    if project_dir is not None:
        manifest_path = project_dir / "project-manifest.json"
        if manifest_path.exists():
            computed_manifest_hash = sha256_file(manifest_path)
    manifest_hash_value = manifest_hash or computed_manifest_hash or state.get("manifest_hash") or "unknown"
    if git_commit:
        git_commit_value: str | None = git_commit
    elif "git_commit" in state:
        git_commit_value = state.get("git_commit")
    else:
        git_commit_value = None
    event: dict[str, Any] = {
        "timestamp": now,
        "checkpoint": checkpoint,
        "step": step,
        "status": status,
        "idempotency_key": idempotency_key,
        "attempt": attempt_value,
        "manifest_hash": manifest_hash_value,
        "git_commit": git_commit_value,
    }
    if error:
        event["error"] = error
    events.append(event)
    state.update(
        {
            "protocol_version": "1.0",
            "session_id": session_id or state.get("session_id") or session_dir.name,
            "phase": "upy-generate-plugin",
            "checkpoint": checkpoint,
            "step": step,
            "status": status,
            "attempt": attempt_value,
            "idempotency_key": idempotency_key,
            "manifest_hash": manifest_hash_value,
            "git_commit": git_commit_value,
            "usage": usage_value,
            "updated_at": now,
            "last_ok_artifact": artifacts[-1] if artifacts else state.get("last_ok_artifact"),
            "artifacts": artifacts or state.get("artifacts", []),
            "events": events[-200:],
        }
    )
    if "created_at" not in state:
        state["created_at"] = now
    if error:
        state["last_error"] = error
    if extra:
        state["extra"] = {**state.get("extra", {}), **extra} if isinstance(state.get("extra"), dict) else extra
    write_json(state_path, state)
    return {"check": "session_state_update", "path": str(state_path), "state": state, "ok": True, "errors": [], "warnings": []}


def check_state(session_dir: Path) -> dict[str, Any]:
    return check_state_with_project(session_dir, None)


def check_state_with_project(session_dir: Path, project_dir: Path | None) -> dict[str, Any]:
    state_path = session_dir / DEFAULT_STATE_FILE
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not state_path.exists():
        return {
            "check": "session_state_checkpoint",
            "path": str(state_path),
            "exists": False,
            "errors": [{"code": "SESSION_STATE_MISSING", "message": "session_state.upy_generate_plugin.json is missing"}],
            "warnings": [],
            "ok": False,
        }
    try:
        state = load_json(state_path)
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "check": "session_state_checkpoint",
            "path": str(state_path),
            "exists": True,
            "errors": [{"code": "SESSION_STATE_INVALID", "message": str(exc)}],
            "warnings": [],
            "ok": False,
        }
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
            errors.append({"code": "SESSION_STATE_FIELD_MISSING", "field": field, "message": f"{field} is required"})
    if state.get("phase") != "upy-generate-plugin":
        errors.append({"code": "SESSION_STATE_PHASE_INVALID", "phase": state.get("phase"), "message": "phase must be upy-generate-plugin"})
    manifest_hash = state.get("manifest_hash")
    if not isinstance(manifest_hash, str) or not manifest_hash.strip():
        errors.append({"code": "SESSION_STATE_MANIFEST_HASH_INVALID", "message": "manifest_hash must be a non-empty string"})
    git_commit = state.get("git_commit")
    if manifest_hash == git_commit and looks_like_git_sha(manifest_hash):
        errors.append(
            {
                "code": "SESSION_STATE_MANIFEST_HASH_IS_GIT_COMMIT",
                "message": "manifest_hash must be the project-manifest.json SHA256, not the git commit",
            }
        )
    if project_dir is not None:
        manifest_path = project_dir / "project-manifest.json"
        if not manifest_path.exists():
            errors.append(
                {
                    "code": "SESSION_STATE_PROJECT_MANIFEST_MISSING",
                    "path": str(manifest_path),
                    "message": "project-manifest.json is required when --project-dir is supplied",
                }
            )
        elif isinstance(manifest_hash, str) and manifest_hash.strip() and manifest_hash != "unknown":
            actual_hash = sha256_file(manifest_path)
            if manifest_hash.lower() != actual_hash.lower():
                errors.append(
                    {
                        "code": "SESSION_STATE_MANIFEST_HASH_MISMATCH",
                        "expected": actual_hash,
                        "actual": manifest_hash,
                        "path": str(manifest_path),
                        "message": "manifest_hash must match the SHA256 of project-manifest.json",
                    }
                )
    usage = state.get("usage")
    if not isinstance(usage, dict):
        errors.append({"code": "SESSION_STATE_USAGE_INVALID", "message": "usage must be a JSON object"})
    else:
        if usage.get("token_budget_status") not in USAGE_STATUSES:
            errors.append(
                {
                    "code": "SESSION_STATE_USAGE_STATUS_INVALID",
                    "status": usage.get("token_budget_status"),
                    "message": "usage.token_budget_status must be unknown, ok, or exhausted",
                }
            )
        if "remaining_budget" not in usage:
            errors.append({"code": "SESSION_STATE_USAGE_REMAINING_MISSING", "message": "usage.remaining_budget is required"})
    if state.get("status") == "completed" and state.get("checkpoint") == "phase_completed":
        if manifest_hash == "unknown":
            errors.append({"code": "SESSION_STATE_MANIFEST_HASH_UNKNOWN", "message": "completed phase state must record the manifest hash"})
        if not isinstance(git_commit, str) or not git_commit.strip():
            errors.append({"code": "SESSION_STATE_GIT_COMMIT_MISSING", "message": "completed phase state must record the generate git commit"})
        artifacts = state.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append({"code": "SESSION_STATE_ARTIFACTS_MISSING", "message": "completed phase state must record resumable artifacts"})
        last_ok = state.get("last_ok_artifact")
        if not isinstance(last_ok, dict) or not last_ok.get("type") or not last_ok.get("path"):
            errors.append({"code": "SESSION_STATE_LAST_OK_ARTIFACT_MISSING", "message": "completed phase state must record last_ok_artifact"})
        artifact_types = {item.get("type") for item in artifacts if isinstance(item, dict)} if isinstance(artifacts, list) else set()
        for required_type in ("project_manifest", "generate_plan"):
            if required_type not in artifact_types:
                errors.append(
                    {
                        "code": "SESSION_STATE_ARTIFACT_TYPE_MISSING",
                        "type": required_type,
                        "message": f"completed phase state artifacts must include {required_type}",
                    }
                )
    events = state.get("events")
    if isinstance(events, list):
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                continue
            if event.get("checkpoint") in {"quality_gates_passed", "git_committed", "phase_completed"} and event.get("manifest_hash") == "unknown":
                warnings.append(
                    {
                        "code": "SESSION_STATE_EVENT_MANIFEST_HASH_UNKNOWN",
                        "index": index,
                        "checkpoint": event.get("checkpoint"),
                        "message": "late checkpoint event should record a real manifest_hash",
                    }
                )
    last_error = state.get("last_error")
    if isinstance(last_error, dict):
        code = last_error.get("code")
        if code in KNOWN_ERROR_CODES and "retryable" not in last_error:
            errors.append({"code": "SESSION_STATE_ERROR_RETRYABLE_MISSING", "error_code": code, "message": "known interruption errors must record retryable"})
    elif state.get("status") in {"failed", "cancelled", "blocked"}:
        warnings.append({"code": "SESSION_STATE_TERMINAL_WITHOUT_ERROR", "message": "terminal non-success state should record last_error"})
    return {
        "check": "session_state_checkpoint",
        "path": str(state_path),
        "exists": True,
        "state": state,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Update or validate upy-generate-plugin session checkpoint state")
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--project-dir", default="", help="Optional project root for manifest_hash validation")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--step", default="")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--status", default="running", choices=["running", "completed", "partial", "failed", "retrying", "cancelled", "blocked"])
    parser.add_argument("--attempt", type=int, default=None)
    parser.add_argument("--artifacts-json", default="")
    parser.add_argument("--extra-json", default="")
    parser.add_argument("--manifest-hash", default="")
    parser.add_argument("--git-commit", default="")
    parser.add_argument("--usage-json", default="")
    parser.add_argument("--error-code", default="")
    parser.add_argument("--error-message", default="")
    parser.add_argument("--error-details-json", default="")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    session_dir = Path(args.session_dir)
    if args.check:
        result = check_state_with_project(session_dir, Path(args.project_dir) if args.project_dir else None)
        json_dump(result)
        return 0 if result["ok"] else 2
    if not args.checkpoint or not args.step or not args.idempotency_key:
        result = {
            "check": "session_state_update",
            "errors": [
                {
                    "code": "SESSION_STATE_UPDATE_ARGUMENT_MISSING",
                    "message": "--checkpoint, --step, and --idempotency-key are required unless --check is used",
                }
            ],
            "warnings": [],
            "ok": False,
        }
        json_dump(result)
        return 2
    details = parse_json_object(args.error_details_json, "error-details-json")
    error = normalize_error(args.error_code, args.step, args.error_message, details) if args.error_code else None
    result = update_state(
        session_dir=session_dir,
        project_dir=Path(args.project_dir) if args.project_dir else None,
        session_id=args.session_id,
        checkpoint=args.checkpoint,
        step=args.step,
        idempotency_key=args.idempotency_key,
        status=args.status,
        attempt=args.attempt,
        artifacts=parse_json_list(args.artifacts_json, "artifacts-json"),
        error=error,
        extra=parse_json_object(args.extra_json, "extra-json"),
        manifest_hash=args.manifest_hash,
        git_commit=args.git_commit,
        usage=parse_json_object(args.usage_json, "usage-json"),
    )
    json_dump(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
