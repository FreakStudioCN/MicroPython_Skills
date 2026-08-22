#!/usr/bin/env python3
"""Find UF2 mass-storage mount points such as RPI-RP2."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--label", default="RPI-RP2")
    parser.add_argument("--candidate", action="append", default=[], help="Extra path to check; useful for tests")
    return parser.parse_args(argv)


def host_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform or "unknown"


def windows_label_mounts(label: str) -> list[str]:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-Volume -FileSystemLabel "
                + json.dumps(label)
                + " -ErrorAction SilentlyContinue | "
                + "Where-Object DriveLetter | "
                + "ForEach-Object { \"$($_.DriveLetter):\\\" }"
            ),
        ],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def default_candidates(label: str) -> list[str]:
    platform = host_platform()
    if platform == "windows":
        return windows_label_mounts(label)
    if platform == "macos":
        return [f"/Volumes/{label}"]
    if platform == "linux":
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
        candidates = [f"/mnt/{label}"]
        if user:
            candidates = [f"/media/{user}/{label}", f"/run/media/{user}/{label}", *candidates]
        return candidates
    return []


def find_mounts(candidates: list[str]) -> list[dict[str, Any]]:
    mounts = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if path.is_dir():
            mounts.append({"path": str(path), "source": "candidate"})
    return mounts


def write_json(data: dict[str, Any], output: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    candidates = [*args.candidate, *default_candidates(args.label)]
    mounts = find_mounts(candidates)
    result = {
        "status": "found" if mounts else "not_found",
        "label": args.label,
        "platform": host_platform(),
        "mounts": mounts,
        "checked": candidates,
    }
    if not mounts:
        # not_found used to carry no message at all, so a model got a bare status and no idea
        # what to do next. Exit stays 0 deliberately: SKILL.md says a missing mount must not
        # auto-fail the Pico flow, because the user may have copied the UF2 without the host
        # ever seeing the volume. The remedy rides in the report instead of the returncode.
        # Singular "error", not an "errors" array: an array would be picked up as a quality-gate
        # failure and inject a corrective for what is an OPTIONAL probe.
        result["error"] = {
            "code": "uf2_mount_not_found",
            "message": (
                f"no UF2 volume labeled '{args.label}' is mounted (checked: "
                + (", ".join(candidates) if candidates else "<none of the known paths apply on this platform>")
                + "). Put the board in bootloader mode: unplug it, hold BOOTSEL while plugging it back in, and "
                "wait for the volume to appear. If the board mounts under a different label, pass --label; if it "
                "mounts at an unusual path, pass --candidate <path>."
            ),
        }
    write_json(result, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
