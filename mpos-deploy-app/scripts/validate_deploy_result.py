#!/usr/bin/env python3
"""Validate an mpos-deploy-app deploy_result JSON file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from _deploy_common import (
    DEFAULT_INSTALL_URL,
    VALID_MODES,
    VALID_NEXT_SKILLS,
    VALID_RESULTS,
    VALID_TRANSPORTS,
    load_json,
)


SCHEMA_VERSION = "mpos-deploy-app-v1"
PHASE = "deploy"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def require_object(value: Any, name: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{name} must be an object")
    return value


def require_array(value: Any, name: str) -> list[Any]:
    require(isinstance(value, list), f"{name} must be an array")
    return value


def require_string(value: Any, name: str, *, allow_empty: bool = False) -> None:
    require(isinstance(value, str), f"{name} must be a string")
    if isinstance(value, str) and not allow_empty:
        require(bool(value.strip()), f"{name} must not be empty")


def validate_checks(root: dict[str, Any], mode: str) -> None:
    checks = require_array(root.get("checks"), "checks")
    by_name: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(checks):
        check = require_object(item, f"checks[{index}]")
        name = check.get("name")
        require(isinstance(name, str) and name, f"checks[{index}].name is required")
        by_name[name] = check
        require(isinstance(check.get("required"), bool), f"{name}: required must be boolean")
        require(isinstance(check.get("ok"), bool), f"{name}: ok must be boolean")
        require_string(check.get("status"), f"{name}: status")
        require_array(check.get("warnings", []), f"{name}: warnings")
        require_array(check.get("errors", []), f"{name}: errors")

    required = {"target_confirmation", "preflight", "deployment_action"}
    if mode in {"device-copy", "mpk-install"}:
        required.add("post_deploy_refresh")
    elif mode == "web-preview":
        required.add("web_http_check")
    elif mode == "desktop-preview":
        required.add("desktop_launch")
    elif mode in {"install-site", "local-flash"}:
        required.add("install_site_guidance")

    missing = sorted(required - set(by_name))
    require(not missing, "checks missing required check names: " + ", ".join(missing))


def validate(root: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(root, dict):
        return ["root must be an object"]

    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if root.get("phase") != PHASE:
        errors.append(f"phase must be {PHASE!r}")
    if root.get("result") not in VALID_RESULTS:
        errors.append(f"result must be one of {sorted(VALID_RESULTS)}")
    require_string(root.get("created_at_utc"), "created_at_utc")

    app = require_object(root.get("app"), "app")
    for key in ("fullname", "name", "version", "app_dir", "manifest", "layout"):
        require_string(app.get(key), f"app.{key}")
    if app.get("icon") is not None:
        require_string(app.get("icon"), "app.icon")

    deploy = require_object(root.get("deploy"), "deploy")
    mode = deploy.get("mode")
    if mode not in VALID_MODES:
        errors.append(f"deploy.mode must be one of {sorted(VALID_MODES)}")
        mode = "desktop-preview"
    transport = deploy.get("transport")
    if transport not in VALID_TRANSPORTS:
        errors.append(f"deploy.transport must be one of {sorted(VALID_TRANSPORTS)}")

    if mode in {"device-copy", "mpk-install"}:
        require_string(deploy.get("board"), "deploy.board")
        require_string(deploy.get("port"), "deploy.port")
    elif mode in {"install-site", "local-flash"}:
        require_string(deploy.get("board"), "deploy.board")
    else:
        if deploy.get("board") is not None:
            require_string(deploy.get("board"), "deploy.board", allow_empty=False)

    if mode in {"install-site", "local-flash"}:
        require_string(deploy.get("install_url"), "deploy.install_url")
        if deploy.get("install_url") != DEFAULT_INSTALL_URL:
            errors.append(f"deploy.install_url should be {DEFAULT_INSTALL_URL!r}")
    elif deploy.get("install_url") is not None:
        require_string(deploy.get("install_url"), "deploy.install_url", allow_empty=False)

    if mode == "web-preview":
        require_string(deploy.get("web_url"), "deploy.web_url")
        parsed = urlparse(str(deploy.get("web_url")))
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            errors.append("deploy.web_url should use http://127.0.0.1 or http://localhost")
    elif deploy.get("web_url") is not None:
        require_string(deploy.get("web_url"), "deploy.web_url", allow_empty=False)

    require(isinstance(deploy.get("confirmed"), bool), "deploy.confirmed must be boolean")

    command = require_object(root.get("command"), "command")
    require_string(command.get("primary"), "command.primary")
    secondary = require_array(command.get("secondary", []), "command.secondary")
    for index, value in enumerate(secondary):
        require_string(value, f"command.secondary[{index}]")

    validate_checks(root, mode)

    require_array(root.get("warnings", []), "warnings")
    require_array(root.get("errors", []), "errors")
    artifacts = require_array(root.get("artifacts", []), "artifacts")
    for index, artifact in enumerate(artifacts):
        item = require_object(artifact, f"artifacts[{index}]")
        require_string(item.get("kind"), f"artifacts[{index}].kind")
        require_string(item.get("path"), f"artifacts[{index}].path")

    handoff = require_object(root.get("handoff"), "handoff")
    if handoff.get("next_skill") not in VALID_NEXT_SKILLS:
        errors.append("handoff.next_skill must be null or a known downstream skill")
    next_step = handoff.get("next_step")
    if next_step is not None:
        require_string(next_step, "handoff.next_step")
    reason = handoff.get("reason")
    if reason is not None:
        require_string(reason, "handoff.reason")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", nargs="?", default="-", help="deploy_result.json path, or '-' for stdin")
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
        print(f"OK: {source} is a valid {SCHEMA_VERSION} deploy result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
