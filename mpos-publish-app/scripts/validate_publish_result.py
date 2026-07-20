#!/usr/bin/env python3
"""Validate mpos-publish-app publish_result.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mpos-publish-app-v1"
PHASE = "publish"
RESULTS = {"success", "partial", "failed"}
HANDOFF_SKILLS = {None, "mpos-gen-app", "mpos-package-app", "mpos-test-app", "mpos-deploy-app", "mpos-plan-app"}
VERSION_STATUSES = {
    "new_app",
    "upgrade_ready",
    "same_version_blocked",
    "downgrade_blocked",
    "unknown",
    "unknown_unverified",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MPK_RELEASE_RE = re.compile(r"^(?P<fullname>[A-Za-z0-9_.-]+)_r(?P<revision>[1-9][0-9]*)\.mpk$")
SCREENSHOT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def load_json(path: str | None) -> Any:
    if path == "-" or path is None:
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def require_object(value: Any, name: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return {}
    return value


def require_array(value: Any, name: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{name} must be an array")
        return []
    return value


def check_string(value: Any, name: str, errors: list[str], *, allow_empty: bool = False) -> None:
    if not isinstance(value, str):
        errors.append(f"{name} must be a string")
        return
    if not allow_empty and not value.strip():
        errors.append(f"{name} must not be empty")


def validate_checks(root: dict[str, Any], errors: list[str]) -> None:
    checks = require_array(root.get("checks"), "checks", errors)
    names = set()
    for idx, item in enumerate(checks):
        check = require_object(item, f"checks[{idx}]", errors)
        name = check.get("name")
        if isinstance(name, str):
            names.add(name)
        else:
            errors.append(f"checks[{idx}].name must be a string")
        if not isinstance(check.get("required"), bool):
            errors.append(f"checks[{idx}].required must be boolean")
        if not isinstance(check.get("ok"), bool):
            errors.append(f"checks[{idx}].ok must be boolean")
        check_string(check.get("status"), f"checks[{idx}].status", errors)
        require_array(check.get("warnings", []), f"checks[{idx}].warnings", errors)
        require_array(check.get("errors", []), f"checks[{idx}].errors", errors)

    required_names = {
        "package_result",
        "app_test_result",
        "deploy_result",
        "artifact_consistency",
        "upystore_version",
        "store_metadata",
        "manual_upload_guidance",
    }
    missing = sorted(required_names - names)
    if missing:
        errors.append("checks missing required check names: " + ", ".join(missing))


def validate(root: Any) -> list[str]:
    errors: list[str] = []
    obj = require_object(root, "root", errors)
    if not obj:
        return errors

    if obj.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if obj.get("phase") != PHASE:
        errors.append(f"phase must be {PHASE!r}")
    if obj.get("result") not in RESULTS:
        errors.append(f"result must be one of {sorted(RESULTS)}")
    check_string(obj.get("created_at_utc"), "created_at_utc", errors)

    app = require_object(obj.get("app"), "app", errors)
    for key in ("fullname", "name", "publisher", "version", "app_dir", "manifest", "icon", "layout"):
        check_string(app.get(key), f"app.{key}", errors)

    inputs = require_object(obj.get("inputs"), "inputs", errors)
    for key in ("package_result", "app_test_result", "deploy_result"):
        check_string(inputs.get(key), f"inputs.{key}", errors)

    artifacts = require_object(obj.get("release_artifacts"), "release_artifacts", errors)
    check_string(artifacts.get("mpk_path"), "release_artifacts.mpk_path", errors)
    check_string(artifacts.get("app_index_entry"), "release_artifacts.app_index_entry", errors)
    revision = artifacts.get("revision")
    if not isinstance(revision, int) or revision < 1:
        errors.append("release_artifacts.revision must be a positive integer")
    mpk_name = Path(str(artifacts.get("mpk_path", ""))).name
    match = MPK_RELEASE_RE.fullmatch(mpk_name)
    if not match:
        errors.append("release_artifacts.mpk_path filename must use <fullname>_rN.mpk")
    elif app.get("fullname") and match.group("fullname") != app.get("fullname"):
        errors.append("release_artifacts.mpk_path fullname must match app.fullname")
    elif isinstance(revision, int) and int(match.group("revision")) != revision:
        errors.append("release_artifacts.mpk_path revision must match release_artifacts.revision")
    sha256 = artifacts.get("mpk_sha256")
    if not isinstance(sha256, str) or not SHA256_RE.match(sha256):
        errors.append("release_artifacts.mpk_sha256 must be a lowercase sha256 hex digest")
    if not isinstance(artifacts.get("mpk_size_bytes"), int) or artifacts.get("mpk_size_bytes") <= 0:
        errors.append("release_artifacts.mpk_size_bytes must be a positive integer")

    metadata = require_object(obj.get("store_metadata"), "store_metadata", errors)
    for key in ("short_description", "long_description", "release_notes"):
        check_string(metadata.get(key), f"store_metadata.{key}", errors)
    if metadata.get("category") is not None:
        check_string(metadata.get("category"), "store_metadata.category", errors)
    require_array(metadata.get("tags", []), "store_metadata.tags", errors)
    require_object(metadata.get("hardware_tags"), "store_metadata.hardware_tags", errors)
    screenshots = require_array(metadata.get("screenshots", []), "store_metadata.screenshots", errors)
    for idx, item in enumerate(screenshots):
        shot = require_object(item, f"store_metadata.screenshots[{idx}]", errors)
        check_string(shot.get("path"), f"store_metadata.screenshots[{idx}].path", errors)
        if not isinstance(shot.get("exists"), bool):
            errors.append(f"store_metadata.screenshots[{idx}].exists must be boolean")
        path_value = shot.get("path")
        if isinstance(path_value, str) and Path(path_value).suffix.lower() not in SCREENSHOT_EXTENSIONS:
            errors.append(f"store_metadata.screenshots[{idx}].path must be PNG, JPEG, or WebP")
        if not isinstance(shot.get("publish_format_ok"), bool):
            errors.append(f"store_metadata.screenshots[{idx}].publish_format_ok must be boolean")
    require_array(metadata.get("missing_fields", []), "store_metadata.missing_fields", errors)
    if metadata.get("min_os_version") is not None:
        check_string(metadata.get("min_os_version"), "store_metadata.min_os_version", errors)
    if metadata.get("min_api_level") is not None and not isinstance(metadata.get("min_api_level"), int):
        errors.append("store_metadata.min_api_level must be integer or null")

    upystore = require_object(obj.get("upystore"), "upystore", errors)
    for key in ("developer_console_url", "app_index_url", "api_apps_url", "checked_at_utc"):
        check_string(upystore.get(key), f"upystore.{key}", errors)
    if upystore.get("version_status") not in VERSION_STATUSES:
        errors.append("upystore.version_status must be a known version status")
    published = require_object(upystore.get("published"), "upystore.published", errors)
    if not isinstance(published.get("exists"), bool):
        errors.append("upystore.published.exists must be boolean")
    require_array(upystore.get("warnings", []), "upystore.warnings", errors)

    validate_checks(obj, errors)
    require_array(obj.get("warnings", []), "warnings", errors)
    require_array(obj.get("errors", []), "errors", errors)
    output_artifacts = require_array(obj.get("artifacts", []), "artifacts", errors)
    for idx, artifact in enumerate(output_artifacts):
        item = require_object(artifact, f"artifacts[{idx}]", errors)
        check_string(item.get("kind"), f"artifacts[{idx}].kind", errors)
        check_string(item.get("path"), f"artifacts[{idx}].path", errors)

    handoff = require_object(obj.get("handoff"), "handoff", errors)
    if handoff.get("next_skill") not in HANDOFF_SKILLS:
        errors.append("handoff.next_skill must be null or a known upstream skill")
    for key in ("next_step", "reason"):
        if handoff.get(key) is not None:
            check_string(handoff.get(key), f"handoff.{key}", errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", nargs="?", default="-", help="publish_result.json path, or '-' for stdin")
    parser.add_argument("--quiet", action="store_true", help="Only print errors")
    args = parser.parse_args()

    try:
        data = load_json(args.json_path)
    except Exception as exc:  # noqa: BLE001 - CLI should report parse/read failures.
        print(f"ERROR: failed to read JSON: {exc}", file=sys.stderr)
        return 2

    errors = validate(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if not args.quiet:
        source = "stdin" if args.json_path == "-" else str(Path(args.json_path))
        print(f"OK: {source} is a valid {SCHEMA_VERSION} publish result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
