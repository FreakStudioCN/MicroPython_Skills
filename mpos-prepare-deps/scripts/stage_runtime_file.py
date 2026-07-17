#!/usr/bin/env python3
"""Safely download or stage an accepted MPOS app runtime dependency file."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_SUFFIXES = {".py", ".mpy", ".json", ".txt"}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def utc_now() -> str:
    fixed = os.environ.get("MPOS_PREPARE_DEPS_UTC_NOW", "").strip()
    if fixed:
        return fixed
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def require_safe_fullname(fullname: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", fullname or ""):
        fail("fullname must contain only letters, digits, dots, underscores, and hyphens")
    if "/" in fullname or "\\" in fullname or ".." in fullname.split("."):
        fail("fullname must not contain path separators or '..' components")


def require_safe_repo_relative(path: str, label: str) -> Path:
    value = Path(path)
    if value.is_absolute() or ".." in value.parts:
        fail(f"{label} must be a repo-relative path without '..': {path}")
    return value


def validate_target_path(target_path: str) -> Path:
    target = require_safe_repo_relative(target_path, "target_path")
    if not str(target).startswith("assets/"):
        fail("target_path must start with assets/")
    if target.name in {"README", "README.md", "LICENSE", "LICENSE.md"}:
        fail("runtime target_path must not be README or LICENSE metadata")
    if target.suffix and target.suffix not in ALLOWED_SUFFIXES:
        fail(f"target_path suffix {target.suffix!r} is not an allowed runtime suffix")
    if not target.suffix and target.name != "__init__.py":
        fail("target_path must point to a runtime file")
    return target


def read_source(source_url: str | None, source_file: str | None) -> tuple[bytes, dict[str, str]]:
    if bool(source_url) == bool(source_file):
        fail("provide exactly one of --source-url or --source-file")
    if source_file:
        path = Path(source_file)
        data = path.read_bytes()
        return data, {"source_file": str(path)}
    assert source_url is not None
    with urllib.request.urlopen(source_url, timeout=30) as response:
        data = response.read()
    return data, {"source_url": source_url}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def metadata_name(target_path: Path) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(target_path)).strip("._-")
    return text or "runtime_file"


def choose_destination(repo: Path, fullname: str, target_path: Path, mode: str, cache_root: Path) -> tuple[Path, str]:
    app_dir = repo / "internal_filesystem" / "apps" / fullname
    if mode == "app":
        if not app_dir.exists():
            fail(f"App directory does not exist for --mode app: {app_dir}")
        return app_dir / target_path, "app"
    if mode == "stage":
        return repo / cache_root / fullname / "staged" / target_path, "staged"
    if app_dir.exists():
        return app_dir / target_path, "app"
    return repo / cache_root / fullname / "staged" / target_path, "staged"


def stage_file(
    repo: Path,
    fullname: str,
    target_path_text: str,
    source_url: str | None,
    source_file: str | None,
    mode: str,
    cache_root_text: str,
    expected_sha256: str | None,
) -> dict[str, Any]:
    require_safe_fullname(fullname)
    cache_root = require_safe_repo_relative(cache_root_text, "cache_root")
    target_path = validate_target_path(target_path_text)
    data, source = read_source(source_url, source_file)
    digest = sha256_hex(data)
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        fail(f"sha256 mismatch: expected {expected_sha256}, got {digest}")

    destination, destination_kind = choose_destination(repo, fullname, target_path, mode, cache_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)

    cache_path = repo / cache_root / fullname
    downloads_dir = cache_path / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "mpos-runtime-download-v1",
        "created_at_utc": utc_now(),
        "app": {
            "fullname": fullname,
            "app_dir": f"internal_filesystem/apps/{fullname}",
            "assets_dir": f"internal_filesystem/apps/{fullname}/assets",
        },
        "cache": {"path": str(cache_root / fullname)},
        "target_path": str(target_path),
        "destination_kind": destination_kind,
        "destination": str(destination.relative_to(repo)),
        "bytes": len(data),
        "sha256": digest,
        **source,
        "handoff_file": {
            "target_path": str(target_path),
            "runtime": True,
            "sha256": digest,
        },
    }
    if destination_kind == "staged":
        record["staged_path"] = str(destination.relative_to(repo))
        record["handoff_file"]["staged_path"] = str(destination.relative_to(repo))
    else:
        record["app_path"] = str(destination.relative_to(repo))
        record["handoff_file"]["app_path"] = str(destination.relative_to(repo))

    record_path = downloads_dir / f"{metadata_name(target_path)}.json"
    record["cache_record"] = str(record_path.relative_to(repo))
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage an MPOS app runtime dependency file")
    parser.add_argument("--repo", default=".", help="MicroPythonOS repo root")
    parser.add_argument("--fullname", required=True, help="MPOS app fullname")
    parser.add_argument("--target-path", required=True, help="Repo app-relative target path, e.g. assets/driver.py")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-url", help="HTTP(S) URL to download")
    source.add_argument("--source-file", help="Local source file to copy")
    parser.add_argument("--mode", choices=["auto", "app", "stage"], default="auto")
    parser.add_argument("--cache-root", default="tmp/mpos-deps-cache", help="Repo-relative cache root")
    parser.add_argument("--expected-sha256", help="Optional expected sha256")
    args = parser.parse_args()

    record = stage_file(
        repo=Path(args.repo),
        fullname=args.fullname,
        target_path_text=args.target_path,
        source_url=args.source_url,
        source_file=args.source_file,
        mode=args.mode,
        cache_root_text=args.cache_root,
        expected_sha256=args.expected_sha256,
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
