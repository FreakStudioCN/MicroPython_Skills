#!/usr/bin/env python3
"""Prepare a batch manifest for manual upystore uploads."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_repo_root(path: Path) -> bool:
    return (path / "internal_filesystem" / "apps").is_dir() and (path / "scripts").is_dir()


def resolve_repo(value: str | None) -> Path:
    if value:
        repo = Path(value).expanduser().resolve()
    else:
        env_repo = os.environ.get("MPOS_REPO")
        repo = Path(env_repo).expanduser().resolve() if env_repo else Path.cwd().resolve()
    if not is_repo_root(repo):
        raise SystemExit(f"ERROR: not a MicroPythonOS repo root: {repo}")
    return repo


def safe_fullname(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value or ""):
        raise ValueError(f"invalid app fullname: {value!r}")
    if "/" in value or "\\" in value or ".." in value.split("."):
        raise ValueError(f"invalid app fullname: {value!r}")
    return value


def read_apps_file(path: Path) -> list[str]:
    apps: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            apps.append(safe_fullname(line))
    return apps


def discover_apps(repo: Path, prefix: str | None) -> list[str]:
    root = repo / "internal_filesystem" / "apps"
    apps = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        name = path.name
        if prefix and not name.startswith(prefix):
            continue
        if (path / "MANIFEST.JSON").exists():
            apps.append(safe_fullname(name))
    return apps


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_path(repo: Path, value: str | None, default: str) -> Path:
    path = Path(value or default).expanduser()
    if not path.is_absolute():
        path = repo / path
    return path


def find_screenshot(screenshot_dir: Path, fullname: str) -> Path | None:
    for ext in IMAGE_EXTENSIONS:
        path = screenshot_dir / f"{fullname}{ext}"
        if path.exists():
            return path
    return None


def rel(repo: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(repo))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_hardware_tags(value: str | None) -> dict[str, Any]:
    if value:
        return json.loads(value)
    return {
        "required": [{"capability": "display"}],
        "optional": [{"capability": "touch"}],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a manual upystore upload manifest for one or more MPOS Apps")
    parser.add_argument("--repo", help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", action="append", default=[], help="App fullname; may be repeated")
    parser.add_argument("--apps-file", help="Text file with one App fullname per line")
    parser.add_argument("--app-prefix", help="Discover Apps whose fullname starts with this prefix")
    parser.add_argument("--mpk-dir", default="tmp/mpos-batch-100-apps/mpk-repaired")
    parser.add_argument("--screenshot-dir", default="tmp/mpos-batch-100-apps/screenshots")
    parser.add_argument("--output", default="tmp/mpos-batch-100-apps/upystore_upload_manifest.json")
    parser.add_argument("--artifact-manifest-output", default="tmp/mpos-batch-100-apps/artifact_manifest.json")
    parser.add_argument("--developer-url", default="https://upystore.io/developer")
    parser.add_argument("--hardware-tags-json")
    parser.add_argument("--release-notes", default="Initial Blockless-Make-APP release.")
    parser.add_argument("--tag", action="append", default=["blockless"])
    parser.add_argument("--category")
    parser.add_argument("--target-board", action="append", default=[])
    args = parser.parse_args()

    repo = resolve_repo(args.repo)
    apps = [safe_fullname(app) for app in args.app_fullname]
    if args.apps_file:
        apps.extend(read_apps_file(Path(args.apps_file).expanduser()))
    if not apps:
        apps = discover_apps(repo, args.app_prefix)
    if not apps:
        raise SystemExit("ERROR: no Apps selected")
    apps = list(dict.fromkeys(apps))

    mpk_dir = resolve_path(repo, args.mpk_dir, "tmp/mpos-batch-100-apps/mpk-repaired")
    screenshot_dir = resolve_path(repo, args.screenshot_dir, "tmp/mpos-batch-100-apps/screenshots")
    output_path = resolve_path(repo, args.output, "tmp/mpos-batch-100-apps/upystore_upload_manifest.json")
    artifact_manifest_path = resolve_path(repo, args.artifact_manifest_output, "tmp/mpos-batch-100-apps/artifact_manifest.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    hardware_tags = default_hardware_tags(args.hardware_tags_json)
    entries: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []

    for app in apps:
        app_dir = repo / "internal_filesystem" / "apps" / app
        manifest_path = app_dir / "MANIFEST.JSON"
        icon_path = app_dir / "icon_64x64.png"
        mpk_path = mpk_dir / f"{app}_r1.mpk"
        screenshot_path = find_screenshot(screenshot_dir, app)
        errors: list[str] = []
        warnings: list[str] = []
        manifest: dict[str, Any] = {}

        if manifest_path.exists():
            try:
                manifest = load_json(manifest_path)
            except Exception as exc:
                errors.append(f"manifest json error: {type(exc).__name__}: {exc}")
        else:
            errors.append("MANIFEST.JSON is missing")

        for field in ("fullname", "name", "publisher", "version"):
            if not manifest.get(field):
                errors.append(f"manifest field {field!r} is missing")
        if manifest.get("fullname") and manifest.get("fullname") != app:
            errors.append(f"manifest fullname {manifest.get('fullname')!r} does not match {app!r}")
        if not icon_path.exists():
            errors.append("icon_64x64.png is missing")
        if not mpk_path.exists():
            errors.append("MPK is missing")
        if screenshot_path is None:
            errors.append("publish-ready screenshot is missing")

        mpk_meta: dict[str, Any] = {
            "path": rel(repo, mpk_path),
            "exists": mpk_path.exists(),
            "revision": 1,
            "filename_policy": "upystore-release-revision",
        }
        if mpk_path.exists():
            mpk_meta["size_bytes"] = mpk_path.stat().st_size
            mpk_meta["sha256"] = sha256_file(mpk_path)
        screenshot_meta: dict[str, Any] = {
            "path": rel(repo, screenshot_path),
            "exists": screenshot_path is not None,
            "publish_format_ok": screenshot_path is not None and screenshot_path.suffix.lower() in IMAGE_EXTENSIONS,
        }
        if screenshot_path is not None:
            screenshot_meta["format"] = screenshot_path.suffix.lower().lstrip(".")
            screenshot_meta["mime"] = mimetypes.guess_type(screenshot_path.name)[0] or "image/png"

        name = str(manifest.get("name") or app.rsplit(".", 1)[-1])
        entry = {
            "fullname": app,
            "ready_for_manual_upload": not errors,
            "errors": errors,
            "warnings": warnings,
            "app": {
                "name": name,
                "publisher": manifest.get("publisher"),
                "version": manifest.get("version"),
                "category": args.category or manifest.get("category") or "tools",
                "manifest": rel(repo, manifest_path),
                "icon": rel(repo, icon_path),
            },
            "release_artifacts": {
                "mpk": mpk_meta,
                "screenshot": screenshot_meta,
            },
            "store_metadata": {
                "short_description": f"{name} for MicroPythonOS.",
                "long_description": f"{name} is a Blockless-Make-APP MicroPythonOS application prepared for classroom, maker, and STEM demos.",
                "release_notes": args.release_notes,
                "tags": args.tag,
                "hardware_tags": hardware_tags,
                "target_boards": args.target_board,
            },
            "manual_upload": {
                "developer_console_url": args.developer_url,
                "required_files": [rel(repo, mpk_path), rel(repo, icon_path), rel(repo, screenshot_path)],
            },
        }
        entries.append(entry)

        if mpk_path.exists():
            artifacts.append({
                "id": f"{app}:mpk",
                "phase": "mpos-publish-app",
                "kind": "package",
                "role": "mpk",
                "path": rel(repo, mpk_path),
                "mime": "application/zip",
                "size": mpk_path.stat().st_size,
                "sha256": sha256_file(mpk_path),
                "display_name": mpk_path.name,
            })
        if screenshot_path is not None:
            artifacts.append({
                "id": f"{app}:screenshot",
                "phase": "mpos-test-app",
                "kind": "image",
                "role": "store_screenshot",
                "path": rel(repo, screenshot_path),
                "mime": mimetypes.guess_type(screenshot_path.name)[0] or "image/png",
                "size": screenshot_path.stat().st_size,
                "sha256": sha256_file(screenshot_path),
                "display_name": screenshot_path.name,
            })

    ready_count = sum(1 for item in entries if item["ready_for_manual_upload"])
    manifest_out = {
        "schema_version": "mpos-upystore-upload-manifest-v1",
        "created_at_utc": utc_now(),
        "repo": str(repo),
        "developer_console_url": args.developer_url,
        "total": len(entries),
        "ready_count": ready_count,
        "blocked_count": len(entries) - ready_count,
        "apps": entries,
    }
    output_path.write_text(json.dumps(manifest_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    artifacts.append({
        "id": "upystore_upload_manifest",
        "phase": "mpos-publish-app",
        "kind": "json",
        "role": "upystore_upload_manifest",
        "path": rel(repo, output_path),
        "mime": "application/json",
        "size": output_path.stat().st_size,
        "sha256": sha256_file(output_path),
        "display_name": output_path.name,
    })
    artifact_manifest = {
        "schema_version": "mpos-artifact-manifest-v1",
        "session_id": "batch",
        "app_fullname": None,
        "artifacts": artifacts,
    }
    artifact_manifest_path.write_text(json.dumps(artifact_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "artifact_manifest": str(artifact_manifest_path), "ready_count": ready_count, "total": len(entries)}, ensure_ascii=False))
    return 0 if ready_count == len(entries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
