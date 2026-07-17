#!/usr/bin/env python3
"""Launch a MicroPythonOS desktop preview for one app."""

from __future__ import annotations

import argparse
import datetime
import shlex
import subprocess
import time
from pathlib import Path

from _deploy_common import (
    DEFAULT_REPO,
    default_output_dir,
    load_app_metadata,
    normalize_app_metadata,
    make_check,
    resolve_app_dir,
    safe_fullname,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", required=True, help="App fullname")
    parser.add_argument("--timeout", type=int, default=10, help="Seconds to wait for the preview to stay alive")
    parser.add_argument("--output-dir", help="Output directory for deploy_result.json")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    fullname = safe_fullname(args.app_fullname)
    app_dir = resolve_app_dir(repo, fullname)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else default_output_dir(repo, fullname)
    output_path = output_dir / "deploy_result.json"
    log_path = output_dir / "desktop_preview.log"
    run_desktop = repo / "scripts" / "run_desktop.sh"
    binary = repo / "lvgl_micropython" / "build" / "lvgl_micropy_unix"

    warnings: list[str] = []
    errors: list[str] = []
    launched = False
    proc = None

    if not run_desktop.is_file():
        errors.append(f"Missing desktop launcher: {run_desktop}")
    if not app_dir.is_dir():
        errors.append(f"App directory does not exist: {app_dir}")

    try:
        app_info = normalize_app_metadata(load_app_metadata(app_dir, repo), app_dir, fullname)
    except Exception as exc:
        app_info = {
            "fullname": fullname,
            "name": fullname,
            "version": "unknown",
            "app_dir": str(app_dir),
            "manifest": str(app_dir / "MANIFEST.JSON"),
            "icon": str(app_dir / "icon_64x64.png"),
            "layout": "missing",
        }
        errors.append(str(exc))

    if not binary.is_file():
        warnings.append("desktop binary is missing; the launch may fail")
    preflight_warnings = list(warnings)
    preflight_errors = list(errors)

    if not errors:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("w", encoding="utf-8")
        try:
            try:
                proc = subprocess.Popen(
                    [str(run_desktop), fullname],
                    cwd=str(repo),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                time.sleep(min(args.timeout, 3))
                launched = proc.poll() is None
                if not launched:
                    errors.append("desktop preview exited immediately")
                elif not binary.is_file():
                    warnings.append("desktop preview is running without a verified binary")
            except Exception as exc:  # noqa: BLE001 - launcher should report local process failures.
                errors.append(f"desktop preview launch failed: {exc}")
        finally:
            log_file.flush()
            log_file.close()

    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()

    result = "failed" if errors else ("partial" if warnings else "success")
    deploy_result = {
        "schema_version": "mpos-deploy-app-v1",
        "phase": "deploy",
        "result": result,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "app": app_info,
        "deploy": {
            "mode": "desktop-preview",
            "transport": "desktop",
            "board": None,
            "port": None,
            "device_id": None,
            "confirmed": True,
            "install_url": None,
            "web_url": None,
        },
        "command": {
            "primary": shlex.join([str(run_desktop), fullname]),
            "secondary": [],
        },
        "checks": [
            make_check(
                "target_confirmation",
                True,
                True,
                "confirmed",
            ),
            make_check(
                "preflight",
                True,
                run_desktop.is_file() and app_dir.is_dir(),
                "passed" if run_desktop.is_file() and app_dir.is_dir() else "failed",
                warnings=preflight_warnings,
                errors=preflight_errors,
                binary=str(binary),
            ),
            make_check(
                "deployment_action",
                True,
                launched,
                "passed" if launched else "failed",
                warnings=[] if launched else ["desktop preview did not stay alive"],
                errors=[] if launched else ["desktop preview exited immediately"],
                pid=proc.pid if proc else None,
            ),
            make_check(
                "desktop_launch",
                True,
                launched,
                "passed" if launched else "failed",
                warnings=[],
                errors=[] if launched else ["desktop preview exited immediately"],
            ),
        ],
        "warnings": warnings,
        "errors": errors,
        "artifacts": [
            {"kind": "deploy_result", "path": str(output_path)},
            {"kind": "desktop_preview_log", "path": str(log_path)},
        ],
        "handoff": {
            "next_skill": None,
            "next_step": "Inspect the desktop window.",
            "reason": "Desktop preview was launched.",
        },
    }
    write_json(output_path, deploy_result)

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(output_path)
    return 0 if result in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
