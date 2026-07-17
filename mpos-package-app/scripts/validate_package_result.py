#!/usr/bin/env python3
"""Validate mpos-package-app package_result.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mpos-package-app-v1"
PHASE = "package"
RESULTS = {"success", "partial", "failed"}
HANDOFF_SKILLS = {None, "mpos-publish-app", "mpos-deploy-app", "mpos-test-app", "mpos-plan-app"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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
        "app_validation",
        "generation_result",
        "app_test_result",
        "mpk_validation",
        "app_index_entry",
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
    for key in ("fullname", "name", "version", "app_dir", "manifest", "icon", "layout"):
        check_string(app.get(key), f"app.{key}", errors)

    inputs = require_object(obj.get("inputs"), "inputs", errors)
    if inputs.get("test_policy") != "warn_only":
        errors.append("inputs.test_policy must be 'warn_only'")

    package = require_object(obj.get("package"), "package", errors)
    check_string(package.get("mpk_path"), "package.mpk_path", errors)
    if package.get("compression") not in {"stored", "deflated"}:
        errors.append("package.compression must be 'stored' or 'deflated'")
    if not isinstance(package.get("size_bytes"), int) or package.get("size_bytes") <= 0:
        errors.append("package.size_bytes must be a positive integer")
    sha256 = package.get("sha256")
    if not isinstance(sha256, str) or not SHA256_RE.match(sha256):
        errors.append("package.sha256 must be a lowercase sha256 hex digest")

    entry = require_object(obj.get("app_index_entry"), "app_index_entry", errors)
    for key in ("path", "base_url", "download_url", "icon_url"):
        check_string(entry.get(key), f"app_index_entry.{key}", errors)

    validate_checks(obj, errors)
    require_array(obj.get("warnings", []), "warnings", errors)
    require_array(obj.get("errors", []), "errors", errors)
    require_array(obj.get("artifacts", []), "artifacts", errors)

    handoff = require_object(obj.get("handoff"), "handoff", errors)
    if handoff.get("next_skill") not in HANDOFF_SKILLS:
        errors.append("handoff.next_skill must be null or a known downstream skill")
    reason = handoff.get("reason")
    if reason is not None:
        check_string(reason, "handoff.reason", errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", nargs="?", default="-", help="package_result.json path, or '-' for stdin")
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
        print(f"OK: {source} is a valid {SCHEMA_VERSION} package result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
