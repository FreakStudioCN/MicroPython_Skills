#!/usr/bin/env python3
import argparse
import json
import sys


PROTOCOL_VERSION = "mpos-robot-skill/v1"
STAGES = {"analyze", "prepare_deps", "generate", "test", "package", "deploy", "publish_check"}
STATUSES = {
    "created",
    "running",
    "completed",
    "partial",
    "blocked",
    "waiting_device",
    "failed",
    "cancelled",
    "timeout",
}
REQUIRED = {
    "protocol_version",
    "session_id",
    "checkpoint_id",
    "idempotency_key",
    "operation",
    "stage",
    "status",
    "capabilities",
    "input",
}


def load(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(envelope):
    errors = []
    if not isinstance(envelope, dict):
        return [{"code": "PROTOCOL_ENVELOPE_INVALID", "message": "Envelope must be an object"}]
    missing = sorted(REQUIRED.difference(envelope))
    if missing:
        errors.append({"code": "PROTOCOL_FIELDS_MISSING", "message": "Required fields are missing", "details": {"fields": missing}})
    if envelope.get("protocol_version") != PROTOCOL_VERSION:
        errors.append(
            {
                "code": "PROTOCOL_VERSION_UNSUPPORTED",
                "message": "Unsupported protocol version",
                "details": {"expected": PROTOCOL_VERSION, "actual": envelope.get("protocol_version")},
            }
        )
    for field in ("session_id", "idempotency_key", "operation"):
        value = envelope.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 160:
            errors.append({"code": "PROTOCOL_FIELD_INVALID", "message": field + " must be a non-empty string", "path": field})
    if envelope.get("stage") not in STAGES:
        errors.append({"code": "PROTOCOL_STAGE_INVALID", "message": "Unknown stage", "path": "stage"})
    if envelope.get("status") not in STATUSES:
        errors.append({"code": "PROTOCOL_STATUS_INVALID", "message": "Unknown status", "path": "status"})
    checkpoint = envelope.get("checkpoint_id")
    if checkpoint is not None and (not isinstance(checkpoint, str) or not checkpoint.strip()):
        errors.append({"code": "PROTOCOL_CHECKPOINT_INVALID", "message": "checkpoint_id must be null or a non-empty string", "path": "checkpoint_id"})
    if not isinstance(envelope.get("capabilities"), dict):
        errors.append({"code": "PROTOCOL_CAPABILITIES_INVALID", "message": "capabilities must be an object", "path": "capabilities"})
    if not isinstance(envelope.get("input"), dict):
        errors.append({"code": "PROTOCOL_INPUT_INVALID", "message": "input must be an object", "path": "input"})
    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate an mpos-robot-skill/v1 envelope")
    parser.add_argument("envelope", nargs="?", default="-", help="JSON path or '-' for stdin")
    args = parser.parse_args()
    try:
        envelope = load(args.envelope)
        errors = validate(envelope)
    except Exception as exc:
        errors = [{"code": "PROTOCOL_READ_FAILED", "message": str(exc)}]
    result = {"ok": not errors, "protocol_version": PROTOCOL_VERSION, "errors": errors}
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
