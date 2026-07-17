#!/usr/bin/env python3
"""Validate the lightweight mpos-analyze-app JSON handoff."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mpos-analyze-v1"
PHASE = "analyze"
RESULTS = {"success", "partial", "failed"}
RUN_TARGETS = {"desktop-first", "web-first", "device-first", "desktop", "web", "device", "unknown"}
OS_INSTALLED = {"yes", "no", "unknown"}
HANDOFF_SKILLS = {
    None,
    "mpos-plan-app",
    "mpos-gen-app",
    "mpos-prepare-deps",
    "mpos-test-app",
    "mpos-package-app",
    "mpos-deploy-app",
    "mpos-publish-app",
}
REQUIRED_URLS = {
    "https://docs.micropythonos.com/",
    "https://upystore.io/",
    "https://install.micropythonos.com/",
    "https://web.micropythonos.com/",
}
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}$")
FULLNAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


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


def validate_resource_links(data: dict[str, Any], errors: list[str]) -> None:
    links = require_array(data.get("resource_links"), "resource_links", errors)
    urls = set()
    for i, item in enumerate(links):
        obj = require_object(item, f"resource_links[{i}]", errors)
        url = obj.get("url")
        if isinstance(url, str):
            urls.add(url)
        else:
            errors.append(f"resource_links[{i}].url must be a string")

    missing = sorted(REQUIRED_URLS - urls)
    if missing:
        errors.append("resource_links missing required URLs: " + ", ".join(missing))


def validate_app(data: dict[str, Any], errors: list[str]) -> None:
    app = require_object(data.get("app"), "app", errors)
    fullname = app.get("fullname")
    version = app.get("version")
    check_string(fullname, "app.fullname", errors)
    check_string(app.get("name"), "app.name", errors)
    check_string(version, "app.version", errors)
    check_string(app.get("category"), "app.category", errors)
    if isinstance(fullname, str) and not FULLNAME_RE.match(fullname):
        errors.append("app.fullname must look like a dotted package name")
    if isinstance(version, str) and not VERSION_RE.match(version):
        errors.append("app.version must be an integer dotted version like 1.0.0")


def validate_manifest_component(component: Any, name: str, errors: list[str]) -> None:
    obj = require_object(component, name, errors)
    check_string(obj.get("classname"), f"{name}.classname", errors)
    entrypoint = obj.get("entrypoint")
    check_string(entrypoint, f"{name}.entrypoint", errors)
    if isinstance(entrypoint, str) and not entrypoint.endswith(".py"):
        errors.append(f"{name}.entrypoint must end with .py")
    filters = obj.get("intent_filters", [])
    if filters is not None:
        require_array(filters, f"{name}.intent_filters", errors)


def validate_manifest(data: dict[str, Any], errors: list[str]) -> None:
    manifest = require_object(data.get("manifest_draft"), "manifest_draft", errors)
    check_string(manifest.get("fullname"), "manifest_draft.fullname", errors)
    check_string(manifest.get("name"), "manifest_draft.name", errors)
    check_string(manifest.get("version"), "manifest_draft.version", errors)

    activities = require_array(manifest.get("activities", []), "manifest_draft.activities", errors)
    services = require_array(manifest.get("services", []), "manifest_draft.services", errors)
    if not activities and not services:
        errors.append("manifest_draft must declare at least one activity or service")

    for i, activity in enumerate(activities):
        validate_manifest_component(activity, f"manifest_draft.activities[{i}]", errors)
    for i, service in enumerate(services):
        validate_manifest_component(service, f"manifest_draft.services[{i}]", errors)


def validate_dependency_plan(data: dict[str, Any], errors: list[str]) -> None:
    plan = require_object(data.get("dependency_plan"), "dependency_plan", errors)
    for key in ("builtin_api_sufficient", "external_driver_required"):
        if not isinstance(plan.get(key), bool):
            errors.append(f"dependency_plan.{key} must be boolean")
    require_array(plan.get("items", []), "dependency_plan.items", errors)
    require_array(plan.get("notes", []), "dependency_plan.notes", errors)


def validate_target(data: dict[str, Any], errors: list[str]) -> None:
    target = require_object(data.get("target"), "target", errors)
    run = target.get("run")
    os_installed = target.get("os_installed", "unknown")
    if run not in RUN_TARGETS:
        errors.append(f"target.run must be one of {sorted(RUN_TARGETS)}")
    if os_installed not in OS_INSTALLED:
        errors.append(f"target.os_installed must be one of {sorted(OS_INSTALLED)}")


def validate_handoff(data: dict[str, Any], errors: list[str]) -> None:
    handoff = require_object(data.get("handoff"), "handoff", errors)
    next_skill = handoff.get("next_skill")
    if next_skill not in HANDOFF_SKILLS:
        errors.append(f"handoff.next_skill must be one of {sorted(v for v in HANDOFF_SKILLS if v)} or null")
    reason = handoff.get("reason")
    if reason is not None:
        check_string(reason, "handoff.reason", errors)


def validate_app_structure(data: dict[str, Any], errors: list[str]) -> None:
    app = require_object(data.get("app"), "app", errors)
    structure = require_object(data.get("app_structure"), "app_structure", errors)
    fullname = app.get("fullname")
    if not isinstance(fullname, str) or not fullname:
        return

    app_dir = structure.get("app_dir")
    expected_app_dir = f"internal_filesystem/apps/{fullname}"
    check_string(app_dir, "app_structure.app_dir", errors)
    if isinstance(app_dir, str) and app_dir != expected_app_dir:
        errors.append(f"app_structure.app_dir must be {expected_app_dir!r}")

    manifest = structure.get("manifest")
    valid_manifests = {
        f"{expected_app_dir}/MANIFEST.JSON",
        f"{expected_app_dir}/META-INF/MANIFEST.JSON",
    }
    check_string(manifest, "app_structure.manifest", errors)
    if isinstance(manifest, str) and manifest not in valid_manifests:
        errors.append("app_structure.manifest must be root MANIFEST.JSON or legacy META-INF/MANIFEST.JSON")

    icon = structure.get("icon")
    valid_icons = {
        f"{expected_app_dir}/icon_64x64.png",
        f"{expected_app_dir}/res/mipmap-mdpi/icon_64x64.png",
    }
    check_string(icon, "app_structure.icon", errors)
    if isinstance(icon, str) and icon not in valid_icons:
        errors.append("app_structure.icon must be root icon_64x64.png or legacy res/mipmap-mdpi/icon_64x64.png")

    entrypoints = require_array(structure.get("entrypoints", []), "app_structure.entrypoints", errors)
    for index, entrypoint in enumerate(entrypoints):
        check_string(entrypoint, f"app_structure.entrypoints[{index}]", errors)
        if isinstance(entrypoint, str) and not entrypoint.startswith(expected_app_dir + "/"):
            errors.append(f"app_structure.entrypoints[{index}] must be under {expected_app_dir}")


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    root = require_object(data, "root", errors)
    if not root:
        return errors

    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if root.get("phase") != PHASE:
        errors.append(f"phase must be {PHASE!r}")
    if root.get("result") not in RESULTS:
        errors.append(f"result must be one of {sorted(RESULTS)}")
    check_string(root.get("summary"), "summary", errors)

    validate_resource_links(root, errors)
    validate_app(root, errors)
    validate_target(root, errors)
    validate_manifest(root, errors)
    validate_dependency_plan(root, errors)

    for name in ("feature_slices", "framework_plan", "lvgl_plan", "api_references", "test_plan", "blocking_questions", "warnings"):
        require_array(root.get(name, []), name, errors)

    require_object(root.get("requirements"), "requirements", errors)
    validate_app_structure(root, errors)
    require_object(root.get("deploy_plan"), "deploy_plan", errors)
    validate_handoff(root, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", nargs="?", default="-", help="Analysis JSON path, or '-' for stdin")
    parser.add_argument("--quiet", action="store_true", help="Only print errors")
    args = parser.parse_args()

    try:
        data = load_json(args.json_path)
    except Exception as exc:  # noqa: BLE001 - CLI should report any parse/read failure.
        print(f"ERROR: failed to read JSON: {exc}", file=sys.stderr)
        return 2

    errors = validate(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if not args.quiet:
        source = "stdin" if args.json_path == "-" else str(Path(args.json_path))
        print(f"OK: {source} is a valid {SCHEMA_VERSION} analysis result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
