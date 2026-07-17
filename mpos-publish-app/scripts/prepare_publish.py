#!/usr/bin/env python3
"""Prepare a MicroPythonOS App release handoff for manual upystore publishing."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_REPO = Path("/home/leeqingshui/MicroPythonOS")
DEFAULT_OUTPUT_ROOT = Path("tmp/mpos-publish-app")
APP_INDEX_URL = "https://upystore.io/app_index.json"
API_APPS_URL = "https://upystore.io/api/v1/apps"
DEVELOPER_CONSOLE_URL = "https://upystore.io/developer"
USER_AGENT = "Mozilla/5.0 (mpos-publish-app)"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: str | Path) -> Any:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def display_path(path: str | Path | None, repo: Path | None = None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    if not p.is_absolute() and repo is not None:
        return p.as_posix()
    if repo is not None:
        try:
            return str(p.resolve().relative_to(repo.resolve()))
        except ValueError:
            pass
    return str(p)


def resolve_repo_path(repo: Path, path_text: str | None) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    return path if path.is_absolute() else repo / path


def version_tuple(value: str | None) -> tuple[int, ...] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parts = value.strip().split(".")
    numbers: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        numbers.append(int(part))
    return tuple(numbers)


def compare_versions(local: str | None, remote: str | None) -> str:
    local_tuple = version_tuple(local)
    remote_tuple = version_tuple(remote)
    if local_tuple is None or remote_tuple is None:
        return "unknown"
    length = max(len(local_tuple), len(remote_tuple))
    local_norm = local_tuple + (0,) * (length - len(local_tuple))
    remote_norm = remote_tuple + (0,) * (length - len(remote_tuple))
    if local_norm > remote_norm:
        return "upgrade_ready"
    if local_norm == remote_norm:
        return "same_version_blocked"
    return "downgrade_blocked"


def make_check(
    name: str,
    required: bool,
    ok: bool,
    status: str,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    check = {
        "name": name,
        "required": required,
        "ok": ok,
        "status": status,
        "warnings": list(warnings or []),
        "errors": list(errors or []),
    }
    check.update(extra)
    return check


def fetch_json(url: str, timeout: int) -> tuple[Any | None, str | None]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, f"{url} unavailable: {exc}"


def iter_upystore_apps(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        apps = data.get("apps")
        if isinstance(apps, list):
            return [item for item in apps if isinstance(item, dict)]
    return []


def query_upystore(fullname: str, timeout: int, skip_network: bool) -> dict[str, Any]:
    checked_at = utc_now()
    if skip_network:
        return {
            "developer_console_url": DEVELOPER_CONSOLE_URL,
            "app_index_url": APP_INDEX_URL,
            "api_apps_url": API_APPS_URL,
            "published": {"exists": False, "source": None, "version": None, "slug": None, "revision": None},
            "version_status": "unknown_unverified",
            "checked_at_utc": checked_at,
            "warnings": ["upystore network check skipped"],
        }

    warnings: list[str] = []
    found: dict[str, Any] | None = None
    for url, source in ((API_APPS_URL, "api/v1/apps"), (APP_INDEX_URL, "app_index.json")):
        data, error = fetch_json(url, timeout)
        if error:
            warnings.append(error)
            continue
        for app in iter_upystore_apps(data):
            if app.get("fullname") == fullname:
                found = dict(app)
                found["_source"] = source
                break
        if found:
            break

    if not found:
        if len(warnings) == 2:
            version_status = "unknown_unverified"
        else:
            version_status = "new_app"
        return {
            "developer_console_url": DEVELOPER_CONSOLE_URL,
            "app_index_url": APP_INDEX_URL,
            "api_apps_url": API_APPS_URL,
            "published": {"exists": False, "source": None, "version": None, "slug": None, "revision": None},
            "version_status": version_status,
            "checked_at_utc": checked_at,
            "warnings": warnings,
        }

    return {
        "developer_console_url": DEVELOPER_CONSOLE_URL,
        "app_index_url": APP_INDEX_URL,
        "api_apps_url": API_APPS_URL,
        "published": {
            "exists": True,
            "source": found.get("_source"),
            "version": found.get("version"),
            "slug": found.get("slug"),
            "revision": found.get("revision"),
        },
        "version_status": "unknown",
        "checked_at_utc": checked_at,
        "warnings": warnings,
    }


def load_required_result(path_text: str, expected_schema: str, expected_phase: str, name: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    path = Path(path_text)
    if not path.is_file():
        errors.append(f"{path} does not exist")
        return None, make_check(name, True, False, "missing", warnings, errors, path=path_text)
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001 - CLI reports malformed input as a structured failure.
        errors.append(f"failed to read {path}: {exc}")
        return None, make_check(name, True, False, "invalid_json", warnings, errors, path=path_text)
    if not isinstance(data, dict):
        errors.append(f"{path} root must be an object")
        return None, make_check(name, True, False, "invalid_json", warnings, errors, path=path_text)
    if data.get("schema_version") != expected_schema:
        errors.append(f"{path} schema_version {data.get('schema_version')!r} != {expected_schema!r}")
    if data.get("phase") != expected_phase:
        errors.append(f"{path} phase {data.get('phase')!r} != {expected_phase!r}")
    result = data.get("result")
    if result == "partial":
        warnings.append(f"{path} result is partial; publishing continues with warning")
    elif result != "success":
        errors.append(f"{path} result is {result!r}")
    status = "passed" if not errors and not warnings else ("warning" if not errors else "failed")
    return data, make_check(name, True, not errors, status, warnings, errors, path=path_text)


def read_app_index_entry(repo: Path, package_result: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    path_text = None
    app_index = package_result.get("app_index_entry")
    if isinstance(app_index, dict):
        path_text = app_index.get("path")
    path = resolve_repo_path(repo, path_text)
    if path is None or not path.is_file():
        if path_text:
            warnings.append(f"app_index_entry file not found: {path_text}")
        else:
            warnings.append("package_result.app_index_entry.path is missing")
        return {}, warnings
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001 - malformed app index is a warning; package_result already validated MPK.
        warnings.append(f"failed to read app_index_entry {path}: {exc}")
        return {}, warnings
    if not isinstance(data, dict):
        warnings.append(f"app_index_entry {path} root is not an object")
        return {}, warnings
    return data, warnings


def normalize_hardware_tags(value: str | None, app_index_entry: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if value:
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            warnings.append(f"hardware_tags JSON is invalid: {exc}")
            return {"required": [], "optional": []}, warnings
        if isinstance(data, dict):
            data.setdefault("required", [])
            data.setdefault("optional", [])
            return data, warnings
        warnings.append("hardware_tags JSON must be an object")
        return {"required": [], "optional": []}, warnings
    entry_tags = app_index_entry.get("hardware_tags")
    if isinstance(entry_tags, dict):
        entry_tags.setdefault("required", [])
        entry_tags.setdefault("optional", [])
        return entry_tags, warnings
    return {"required": [], "optional": []}, warnings


def collect_metadata(args: argparse.Namespace, repo: Path, app_index_entry: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    missing: list[str] = []
    hardware_tags, hardware_warnings = normalize_hardware_tags(args.hardware_tags_json, app_index_entry)
    warnings.extend(hardware_warnings)

    screenshots = []
    for value in args.screenshot or []:
        path = Path(value)
        exists = path.is_file() or (repo / path).is_file()
        screenshots.append({"path": display_path(path, repo), "exists": exists})
        if not exists:
            warnings.append(f"screenshot not found: {value}")

    metadata = {
        "short_description": args.short_description or app_index_entry.get("short_description") or "",
        "long_description": args.long_description or app_index_entry.get("long_description") or "",
        "category": args.category or app_index_entry.get("category"),
        "tags": list(args.tag or app_index_entry.get("tags") or []),
        "hardware_tags": hardware_tags,
        "screenshots": screenshots,
        "release_notes": args.release_notes or "",
        "min_os_version": args.min_os_version or app_index_entry.get("min_os_version"),
        "min_api_level": args.min_api_level if args.min_api_level is not None else app_index_entry.get("min_api_level"),
        "missing_fields": missing,
    }
    for field in ("short_description", "long_description", "release_notes"):
        if not metadata.get(field):
            missing.append(field)
    if not screenshots:
        warnings.append("no screenshots were provided for upystore metadata")
    if not hardware_tags.get("required") and not hardware_tags.get("optional"):
        warnings.append("hardware_tags are empty")
    return metadata, missing, warnings


def app_from_results(package_result: dict[str, Any], app_test_result: dict[str, Any], deploy_result: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    package_app = package_result.get("app") if isinstance(package_result.get("app"), dict) else {}
    test_app = app_test_result.get("app") if isinstance(app_test_result.get("app"), dict) else {}
    deploy_app = deploy_result.get("app") if isinstance(deploy_result.get("app"), dict) else {}
    fullname = package_app.get("fullname") or deploy_app.get("fullname") or test_app.get("fullname")
    for source, app in (("app_test_result", test_app), ("deploy_result", deploy_app)):
        if app.get("fullname") and fullname and app.get("fullname") != fullname:
            errors.append(f"{source}.app.fullname {app.get('fullname')!r} does not match {fullname!r}")
    app = {
        "fullname": fullname or "",
        "name": package_app.get("name") or deploy_app.get("name") or fullname or "",
        "version": package_app.get("version") or deploy_app.get("version") or "",
        "app_dir": package_app.get("app_dir") or deploy_app.get("app_dir") or test_app.get("app_dir") or "",
        "manifest": package_app.get("manifest") or deploy_app.get("manifest") or "",
        "icon": package_app.get("icon") or deploy_app.get("icon") or "",
        "layout": package_app.get("layout") or deploy_app.get("layout") or "unknown",
    }
    for key in ("fullname", "name", "version", "app_dir", "manifest", "icon"):
        if not app.get(key):
            errors.append(f"app.{key} is missing from upstream results")
    return app, warnings, errors


def artifact_info(repo: Path, package_result: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    package = package_result.get("package") if isinstance(package_result.get("package"), dict) else {}
    entry = package_result.get("app_index_entry") if isinstance(package_result.get("app_index_entry"), dict) else {}
    mpk_path_text = package.get("mpk_path")
    mpk_path = resolve_repo_path(repo, mpk_path_text)
    if mpk_path is None or not mpk_path.is_file():
        errors.append(f"MPK file is missing: {mpk_path_text}")
    app_index_path_text = entry.get("path")
    app_index_path = resolve_repo_path(repo, app_index_path_text)
    if app_index_path is None or not app_index_path.is_file():
        errors.append(f"app_index_entry file is missing: {app_index_path_text}")
    return {
        "mpk_path": mpk_path_text or "",
        "mpk_sha256": package.get("sha256") or "0" * 64,
        "mpk_size_bytes": package.get("size_bytes") or 0,
        "app_index_entry": app_index_path_text or "",
    }, warnings, errors


def choose_handoff(errors: list[str]) -> tuple[str | None, str, str]:
    if not errors:
        return None, f"Open {DEVELOPER_CONSOLE_URL} and upload the MPK manually.", "Release artifacts and metadata are ready for manual upystore submission."
    joined = "\n".join(errors)
    if "package_result" in joined or "MPK" in joined or "app_index_entry" in joined:
        return "mpos-package-app", "Regenerate and validate the MPK package before publishing.", "Package artifacts are not publish-ready."
    if "app_test_result" in joined:
        return "mpos-test-app", "Rerun runtime smoke tests before publishing.", "Test result is not publish-ready."
    if "deploy_result" in joined:
        return "mpos-deploy-app", "Rerun the deployment or preview handoff before publishing.", "Deploy result is not publish-ready."
    return "mpos-gen-app", "Repair App metadata or release fields before publishing.", "Release metadata is not publish-ready."


def prepare_publish(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    package_result, package_check = load_required_result(args.package_result, "mpos-package-app-v1", "package", "package_result")
    app_test_result, test_check = load_required_result(args.app_test_result, "mpos-test-app-v1", "test-app", "app_test_result")
    deploy_result, deploy_check = load_required_result(args.deploy_result, "mpos-deploy-app-v1", "deploy", "deploy_result")

    checks = [package_check, test_check, deploy_check]
    warnings: list[str] = []
    errors: list[str] = []
    for check in checks:
        warnings.extend(check["warnings"])
        errors.extend(check["errors"])

    package_result = package_result or {"app": {}, "package": {}, "app_index_entry": {}}
    app_test_result = app_test_result or {"app": {}}
    deploy_result = deploy_result or {"app": {}}

    app, app_warnings, app_errors = app_from_results(package_result, app_test_result, deploy_result)
    warnings.extend(app_warnings)
    errors.extend(app_errors)

    artifacts, artifact_warnings, artifact_errors = artifact_info(repo, package_result)
    warnings.extend(artifact_warnings)
    errors.extend(artifact_errors)
    artifact_check_errors = app_errors + artifact_errors
    checks.append(
        make_check(
            "artifact_consistency",
            True,
            not artifact_check_errors,
            "passed" if not artifact_check_errors else "failed",
            artifact_warnings + app_warnings,
            artifact_check_errors,
        )
    )

    app_index_entry, index_warnings = read_app_index_entry(repo, package_result)
    warnings.extend(index_warnings)
    metadata, missing_metadata, metadata_warnings = collect_metadata(args, repo, app_index_entry)
    warnings.extend(metadata_warnings)

    upystore = query_upystore(app.get("fullname", ""), args.network_timeout, args.skip_network)
    warnings.extend(upystore.get("warnings", []))
    if upystore["published"]["exists"]:
        upystore["version_status"] = compare_versions(app.get("version"), upystore["published"].get("version"))
    version_status = upystore["version_status"]
    version_errors: list[str] = []
    version_warnings: list[str] = list(upystore.get("warnings", []))
    if version_status in {"same_version_blocked", "downgrade_blocked"}:
        version_errors.append(
            f"local version {app.get('version')!r} is not greater than published version {upystore['published'].get('version')!r}"
        )
    elif version_status in {"unknown", "unknown_unverified"}:
        version_warnings.append("upystore version comparison could not be fully verified")
    checks.append(
        make_check(
            "upystore_version",
            True,
            not version_errors,
            version_status,
            version_warnings,
            version_errors,
            published=upystore["published"],
        )
    )
    warnings.extend(version_warnings)
    errors.extend(version_errors)

    metadata_errors: list[str] = []
    if missing_metadata:
        metadata_errors.append("missing required store metadata: " + ", ".join(missing_metadata))
    checks.append(
        make_check(
            "store_metadata",
            True,
            not metadata_errors,
            "complete" if not metadata_errors else "incomplete",
            metadata_warnings,
            metadata_errors,
            missing_fields=missing_metadata,
        )
    )
    errors.extend(metadata_errors)

    upload_ready = not errors
    checks.append(
        make_check(
            "manual_upload_guidance",
            True,
            upload_ready,
            "ready" if upload_ready else "blocked",
            [],
            [] if upload_ready else ["release is not ready for manual upystore upload"],
            url=DEVELOPER_CONSOLE_URL,
        )
    )

    fullname = app.get("fullname") or "unknown"
    output_dir = Path(args.output_dir).resolve() if args.output_dir else repo / DEFAULT_OUTPUT_ROOT / fullname
    output_path = output_dir / "publish_result.json"
    next_skill, next_step, reason = choose_handoff(errors)
    result = "failed" if errors else ("partial" if warnings else "success")
    publish_result = {
        "schema_version": "mpos-publish-app-v1",
        "phase": "publish",
        "result": result,
        "created_at_utc": utc_now(),
        "app": app,
        "inputs": {
            "package_result": args.package_result,
            "app_test_result": args.app_test_result,
            "deploy_result": args.deploy_result,
        },
        "release_artifacts": artifacts,
        "store_metadata": metadata,
        "upystore": upystore,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "artifacts": [
            {"kind": "publish_result", "path": display_path(output_path, repo)},
        ],
        "handoff": {
            "next_skill": next_skill,
            "next_step": next_step,
            "reason": reason,
        },
    }
    write_json(output_path, publish_result)
    return publish_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="MicroPythonOS repository root")
    parser.add_argument("--package-result", required=True, help="mpos-package-app package_result.json")
    parser.add_argument("--app-test-result", required=True, help="mpos-test-app app_test_result.json")
    parser.add_argument("--deploy-result", required=True, help="mpos-deploy-app deploy_result.json")
    parser.add_argument("--short-description", help="upystore short_description")
    parser.add_argument("--long-description", help="upystore long_description")
    parser.add_argument("--release-notes", help="upystore release notes")
    parser.add_argument("--hardware-tags-json", help="JSON object for upystore hardware_tags")
    parser.add_argument("--screenshot", action="append", help="Screenshot path for upystore metadata")
    parser.add_argument("--tag", action="append", help="Store tag; may be repeated")
    parser.add_argument("--category", help="Store category")
    parser.add_argument("--min-os-version", help="Minimum MicroPythonOS version")
    parser.add_argument("--min-api-level", type=int, help="Minimum API level")
    parser.add_argument("--network-timeout", type=int, default=20, help="Seconds for each upystore request")
    parser.add_argument("--skip-network", action="store_true", help="Skip upystore version comparison network requests")
    parser.add_argument("--output-dir", help="Directory for publish_result.json")
    args = parser.parse_args()

    result = prepare_publish(args)
    for warning in result.get("warnings", []):
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in result.get("errors", []):
        print(f"ERROR: {error}", file=sys.stderr)
    print(result["artifacts"][0]["path"])
    return 0 if result.get("result") in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
