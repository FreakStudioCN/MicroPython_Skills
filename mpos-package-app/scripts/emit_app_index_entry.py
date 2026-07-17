#!/usr/bin/env python3
"""Emit one app_index entry for a MicroPythonOS App."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from validate_mpos_app import resolve_app_dir, validate_app


DEFAULT_REPO = Path("/home/leeqingshui/MicroPythonOS")
DEFAULT_BASE_URL = "https://apps.micropythonos.com"


def emit_entry(
    repo: Path,
    app_dir: Path,
    app_fullname: str | None,
    base_url: str,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    validation = validate_app(repo, app_dir, app_fullname)
    warnings.extend(validation.get("warnings", []))
    errors.extend(validation.get("errors", []))
    if errors:
        return None, warnings, errors

    manifest = dict(validation["manifest"])
    fullname = manifest["fullname"]
    version = manifest["version"]
    base_url = base_url.rstrip("/")
    manifest["icon_url"] = (
        f"{base_url}/apps/{fullname}/icons/{fullname}_{version}_64x64.png"
    )
    manifest["download_url"] = (
        f"{base_url}/apps/{fullname}/mpks/{fullname}_{version}.mpk"
    )
    manifest.setdefault("services", [])
    return manifest, warnings, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", help="App fullname")
    parser.add_argument("--app-dir", help="Explicit App directory")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base AppStore URL")
    parser.add_argument("--output", required=True, help="Output app_index_entry.json path")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    try:
        app_dir = resolve_app_dir(repo, args.app_fullname, args.app_dir).resolve()
        entry, warnings, errors = emit_entry(repo, app_dir, args.app_fullname, args.base_url)
    except Exception as exc:  # noqa: BLE001 - CLI should report any setup failure.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(f"OK: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
