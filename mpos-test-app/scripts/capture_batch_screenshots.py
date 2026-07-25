#!/usr/bin/env python3
"""Capture publish-ready screenshots for a batch of MicroPythonOS Apps."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MARKER = "__MPOS_BATCH_SCREENSHOT__"


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


def parse_marker(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", "replace")
    parsed: dict[str, Any] = {"ok": False, "raw_output": text}
    for line in reversed(text.splitlines()):
        if MARKER in line:
            payload = line.split(MARKER, 1)[1].strip()
            try:
                data = json.loads(payload)
                if isinstance(data, dict):
                    data["raw_output"] = text
                    return data
            except Exception as exc:
                parsed["parse_error"] = f"{type(exc).__name__}: {exc}"
                return parsed
    parsed["parse_error"] = "marker not found"
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture PNG screenshots for multiple MPOS Apps")
    parser.add_argument("--repo", help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", action="append", default=[], help="App fullname; may be repeated")
    parser.add_argument("--apps-file", help="Text file with one App fullname per line")
    parser.add_argument("--app-prefix", help="Discover Apps whose fullname starts with this prefix")
    parser.add_argument("--output-dir", default="tmp/mpos-batch-screenshots")
    parser.add_argument("--manifest", help="Screenshot manifest output path")
    parser.add_argument("--render-iterations", type=int, default=10)
    parser.add_argument("--heapsize", default="32M")
    parser.add_argument("--keep-bmp", action="store_true", help="Keep raw BMP evidence next to PNG files")
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

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest) if args.manifest else output_dir / "screenshot_manifest.json"
    if not manifest_path.is_absolute():
        manifest_path = repo / manifest_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(repo / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mpos_controller import MPOSController  # type: ignore
    from run_app_smoke import bmp_to_png_bytes  # type: ignore

    entries: list[dict[str, Any]] = []
    with MPOSController(backend="process", heapsize=args.heapsize) as mpos:
        for app in apps:
            code = f"""
import json
try:
    from mpos.content.app_manager import AppManager
    from mpos.ui.testing import wait_for_render
    ok = AppManager.start_app({app!r})
    wait_for_render({int(args.render_iterations)})
    print({MARKER!r} + json.dumps({{"ok": bool(ok), "start_result": repr(ok)}}))
except Exception as exc:
    import sys
    try:
        sys.print_exception(exc)
    except Exception:
        print(repr(exc))
    print({MARKER!r} + json.dumps({{"ok": False, "error_type": type(exc).__name__, "error": str(exc)}}))
"""
            raw = mpos.exec_multiline(code)
            parsed = parse_marker(raw)
            raw_text = parsed.get("raw_output", "")
            has_exception = any(token in raw_text for token in ("Traceback", "AttributeError:", "TypeError:", "caught exception"))
            entry: dict[str, Any] = {
                "fullname": app,
                "result": "failed",
                "start_ok": bool(parsed.get("ok")),
                "warnings": [],
                "errors": [],
                "artifacts": [],
            }
            if not parsed.get("ok"):
                entry["errors"].append(parsed.get("error") or parsed.get("parse_error") or "App did not start")
            if has_exception:
                entry["errors"].append("runtime output contained exception markers")
            if not entry["errors"]:
                try:
                    bmp = mpos.screenshot()
                    if args.keep_bmp:
                        bmp_path = output_dir / f"{app}.bmp"
                        bmp_path.write_bytes(bmp)
                        entry["artifacts"].append({"kind": "screenshot_raw", "path": str(bmp_path), "format": "bmp"})
                    png_path = output_dir / f"{app}.png"
                    png_path.write_bytes(bmp_to_png_bytes(bmp))
                    entry["artifacts"].append({"kind": "screenshot", "path": str(png_path), "format": "png", "publish_ready": True})
                    entry["result"] = "success"
                except Exception as exc:
                    entry["errors"].append(f"screenshot failed: {type(exc).__name__}: {exc}")
            entries.append(entry)
            print(f"{app}: {entry['result']}", flush=True)

    manifest = {
        "schema_version": "mpos-batch-screenshot-manifest-v1",
        "created_at_utc": utc_now(),
        "repo": str(repo),
        "output_dir": str(output_dir),
        "total": len(entries),
        "success_count": sum(1 for item in entries if item["result"] == "success"),
        "failed_count": sum(1 for item in entries if item["result"] != "success"),
        "apps": entries,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if manifest["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
