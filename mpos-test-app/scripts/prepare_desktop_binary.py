#!/usr/bin/env python3
"""Download the latest MicroPythonOS Linux desktop ELF and optionally launch an app."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.github.com/repos/MicroPythonOS/MicroPythonOS/releases/latest"
USER_AGENT = "mpos-test-app/prepare-desktop-binary"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_json(url: str, timeout: int) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("GitHub release API returned a non-object response")
    return data


def select_asset(release: dict[str, Any], asset_regex: str | None) -> dict[str, Any]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("GitHub release response has no assets array")
    candidates = [asset for asset in assets if isinstance(asset, dict)]
    if asset_regex:
        pattern = re.compile(asset_regex)
        for asset in candidates:
            name = str(asset.get("name") or "")
            if pattern.search(name):
                return asset
        raise ValueError(f"no release asset matched --asset-regex {asset_regex!r}")

    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        arch_terms = {"x64", "amd64", "x86_64"}
    elif machine in {"aarch64", "arm64"}:
        arch_terms = {"arm64", "aarch64"}
    else:
        arch_terms = {machine}

    def score(asset: dict[str, Any]) -> int:
        name = str(asset.get("name") or "").lower()
        if not name.endswith(".elf"):
            return -1
        points = 0
        if "linux" in name:
            points += 4
        if any(term in name for term in arch_terms):
            points += 8
        elif any(term in name for term in {"x64", "amd64", "x86_64", "arm64", "aarch64"}):
            return -1
        return points

    ranked = sorted(((score(asset), asset) for asset in candidates), key=lambda item: item[0], reverse=True)
    if ranked and ranked[0][0] >= 12:
        return ranked[0][1]
    raise ValueError(f"no Linux .elf asset for host architecture {machine!r} found in latest MicroPythonOS release")


def download(url: str, output: Path, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".download")
    digest = hashlib.sha256()
    try:
        with urlopen(request, timeout=timeout) as response, temp.open("wb") as f:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                f.write(chunk)
        temp.replace(output)
    finally:
        if temp.exists():
            temp.unlink()
    mode = output.stat().st_mode
    output.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="MicroPythonOS repository root")
    parser.add_argument("--timeout", type=int, default=60, help="Seconds for GitHub API and download requests")
    parser.add_argument("--asset-regex", help="Optional regex used to select a release asset by name")
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse an existing lvgl_micropy_unix instead of downloading")
    parser.add_argument("--run-app", help="Run scripts/run_desktop.sh for this app after preparing the ELF")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    target = repo / "lvgl_micropython" / "build" / "lvgl_micropy_unix"
    result: dict[str, Any] = {
        "schema_version": "mpos-test-app-desktop-binary-v1",
        "phase": "prepare-desktop-binary",
        "result": "failed",
        "created_at_utc": utc_now(),
        "repo": str(repo),
        "target": str(target),
        "release": None,
        "asset": None,
        "sha256": None,
        "warnings": [],
        "errors": [],
    }

    try:
        if args.reuse_existing and target.is_file():
            result["result"] = "success"
            result["warnings"].append("reused existing desktop binary")
        else:
            release = fetch_json(API_URL, args.timeout)
            asset = select_asset(release, args.asset_regex)
            url = asset.get("browser_download_url")
            if not isinstance(url, str) or not url:
                raise ValueError("selected release asset has no browser_download_url")
            result["release"] = {
                "tag_name": release.get("tag_name"),
                "name": release.get("name"),
                "html_url": release.get("html_url"),
            }
            result["asset"] = {
                "name": asset.get("name"),
                "size": asset.get("size"),
                "browser_download_url": url,
            }
            result["sha256"] = download(url, target, args.timeout)
            result["result"] = "success"

        if args.run_app and result["result"] == "success":
            run_desktop = repo / "scripts" / "run_desktop.sh"
            if not run_desktop.is_file():
                raise FileNotFoundError(f"missing desktop launcher: {run_desktop}")
            print(json.dumps(result, indent=2, sort_keys=True), flush=True)
            os.execv(str(run_desktop), [str(run_desktop), args.run_app])
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
