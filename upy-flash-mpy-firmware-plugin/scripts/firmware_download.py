#!/usr/bin/env python3
"""Download firmware resolved by firmware_page_resolve.py."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any


def write_json(data: dict[str, Any], output: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def portable_path(path: Path) -> str:
    return path.as_posix()


def artifact_path(path: Path, root: str | None) -> str | None:
    if not root:
        return None
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolved-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--artifact-root")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    resolved = json.loads(Path(args.resolved_json).read_text(encoding="utf-8"))
    latest = resolved.get("latest") or {}
    url = latest.get("url")
    filename = latest.get("filename")
    if not url or not filename:
        write_json({"status": "failed", "error": {"code": "latest_firmware_not_found", "message": "resolved JSON lacks latest.url/filename"}}, args.output_json)
        return 2

    out_dir = Path(args.out_dir)
    dest = out_dir / filename
    result: dict[str, Any] = {
        "status": "planned" if args.no_download else "success",
        "firmware_url": url,
        "filename": filename,
        "file_type": latest.get("file_type"),
        "downloaded": False,
        "downloaded_path": portable_path(dest),
    }
    rel_dest = artifact_path(dest, args.artifact_root)
    if args.artifact_root:
        if rel_dest:
            result["downloaded_artifact_path"] = rel_dest
        else:
            result["warnings"] = [
                {
                    "code": "artifact_path_unresolved",
                    "message": "download destination is not under artifact_root",
                    "severity": "warning",
                }
            ]
    if not args.no_download:
        out_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "upy-flash-mpy-firmware-plugin/1.0"})
        with urllib.request.urlopen(req, timeout=args.timeout) as response:
            dest.write_bytes(response.read())
        result["downloaded"] = True
    write_json(result, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
