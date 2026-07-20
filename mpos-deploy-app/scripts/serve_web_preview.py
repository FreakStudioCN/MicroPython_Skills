#!/usr/bin/env python3
"""Serve the MicroPythonOS Web Port preview from existing artifacts."""

from __future__ import annotations

import argparse
import datetime
import os
import shlex
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from _deploy_common import (
    load_app_metadata,
    normalize_app_metadata,
    make_check,
    run,
    resolve_app_dir,
    resolve_output_dir,
    resolve_repo_arg,
    safe_fullname,
    write_json,
)


def artifact_paths(repo: Path) -> list[Path]:
    web_dir = repo / "web"
    return [
        web_dir / "index.html",
        web_dir / "micropython.js",
        web_dir / "micropython.wasm",
        web_dir / "micropython.data",
    ]


def check_http(url: str, timeout: int) -> tuple[bool, str]:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                if 200 <= getattr(response, "status", 200) < 400:
                    return True, ""
                last_error = f"HTTP {getattr(response, 'status', 'unknown')}"
        except URLError as exc:
            last_error = str(exc)
        except Exception as exc:  # noqa: BLE001 - preview launcher should record unexpected network failures.
            last_error = str(exc)
        time.sleep(1)
    return False, last_error or "timed out"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", required=True, help="App fullname")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP readiness timeout in seconds")
    parser.add_argument("--build", action="store_true", help="Build web artifacts before serving")
    parser.add_argument("--output-dir", help="Output directory for deploy_result.json")
    args = parser.parse_args()

    repo = resolve_repo_arg(args.repo)
    fullname = safe_fullname(args.app_fullname)
    app_dir = resolve_app_dir(repo, fullname)
    output_dir = resolve_output_dir(repo, fullname, args.output_dir)
    output_path = output_dir / "deploy_result.json"
    log_path = output_dir / "web_preview.log"
    web_url = f"http://127.0.0.1:{args.port}/"
    web_dir = repo / "web"
    run_web = repo / "scripts" / "run_web.sh"
    build_web = repo / "scripts" / "build_mpos.sh"

    warnings: list[str] = []
    errors: list[str] = []
    build_proc = None
    server_proc = None
    launched = False
    server_ready = False

    if not run_web.is_file():
        errors.append(f"Missing web launcher: {run_web}")
    if args.build and not build_web.is_file():
        errors.append(f"Missing web build script: {build_web}")
    if not app_dir.is_dir():
        errors.append(f"App directory does not exist: {app_dir}")
    try:
        app_info = normalize_app_metadata(load_app_metadata(app_dir, repo), app_dir, fullname)
    except Exception as exc:
        app_info = {
            "fullname": fullname,
            "name": fullname,
            "publisher": "",
            "version": "unknown",
            "app_dir": str(app_dir),
            "manifest": str(app_dir / "MANIFEST.JSON"),
            "icon": str(app_dir / "icon_64x64.png"),
            "layout": "missing",
        }
        errors.append(str(exc))
    if not app_info.get("publisher"):
        errors.append("manifest publisher is missing")

    missing_artifacts = [path for path in artifact_paths(repo) if not path.is_file()]
    if missing_artifacts and not args.build:
        warnings.append("web artifacts are missing; confirm build before serving")
    elif args.build:
        build_command = [str(build_web), "web"]
        build_proc = run(build_command, cwd=str(repo), timeout=max(args.timeout * 4, 60))
        if build_proc.returncode != 0:
            errors.append("web build failed")
            if build_proc.stdout:
                warnings.append(build_proc.stdout.strip()[-1500:])
        else:
            missing_artifacts = [path for path in artifact_paths(repo) if not path.is_file()]
            if missing_artifacts:
                warnings.append("web build completed but some artifacts are still missing")

    if not errors and not missing_artifacts:
        preview_command = [str(run_web), "--no-build"]
        env = os.environ.copy()
        env["PORT"] = str(args.port)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("w", encoding="utf-8")
        try:
            try:
                server_proc = subprocess.Popen(
                    preview_command,
                    cwd=str(repo),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    start_new_session=True,
                )
                launched = True
                server_ready, http_error = check_http(web_url, args.timeout)
                if not server_ready:
                    errors.append(f"web preview did not become ready: {http_error}")
                    try:
                        server_proc.terminate()
                    except Exception:
                        pass
            except Exception as exc:  # noqa: BLE001 - launcher should report local process failures.
                errors.append(f"web preview launch failed: {exc}")
        finally:
            log_file.flush()
            log_file.close()
    else:
        if not missing_artifacts:
            warnings.append("web preview was not launched")

    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()

    if errors:
        result = "failed"
    elif missing_artifacts:
        result = "blocked"
    elif not launched or not server_ready:
        result = "failed"
    elif warnings:
        result = "partial"
    else:
        result = "success"
    command_primary = shlex.join([str(run_web), "--no-build"])
    if args.build:
        command_primary = shlex.join([str(build_web), "web"]) + " && " + command_primary
    deploy_result = {
        "schema_version": "mpos-deploy-app-v1",
        "phase": "deploy",
        "result": result,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "app": app_info,
        "deploy": {
            "mode": "web-preview",
            "transport": "http",
            "board": None,
            "port": str(args.port),
            "device_id": None,
            "confirmed": True,
            "hardware_available": False,
            "install_url": None,
            "web_url": web_url,
        },
        "command": {
            "primary": command_primary,
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
                not missing_artifacts,
                "passed" if not missing_artifacts else "warning",
                warnings=[f"missing web artifact: {path.relative_to(repo)}" for path in missing_artifacts],
                errors=[],
                web_dir=str(web_dir),
                build_requested=args.build,
            ),
            make_check(
                "deployment_action",
                True,
                launched,
                "passed" if launched else "skipped",
                warnings=[] if launched else ["web preview was not launched"],
                errors=[],
                pid=server_proc.pid if server_proc else None,
            ),
            make_check(
                "web_http_check",
                True,
                server_ready,
                "passed" if server_ready else ("missing_artifacts" if missing_artifacts else "failed"),
                warnings=[f"missing web artifact: {path.relative_to(repo)}" for path in missing_artifacts] if missing_artifacts else [],
                errors=[] if server_ready or missing_artifacts else [f"preview URL did not answer at {web_url}"],
                url=web_url,
            ),
        ],
        "warnings": warnings,
        "errors": errors,
        "artifacts": [
            {"kind": "deploy_result", "path": str(output_path)},
            {"kind": "web_preview_log", "path": str(log_path)},
        ],
        "handoff": {
            "next_skill": "mpos-publish-app" if result in {"success", "partial"} else "mpos-deploy-app",
            "next_step": (
                "Prepare the manual upystore publishing handoff."
                if result in {"success", "partial"}
                else "Retry web preview after building artifacts or changing the preview target."
            ),
            "reason": (
                "Web preview deploy record is available."
                if result in {"success", "partial"}
                else "Web preview did not produce a usable deploy record."
            ),
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
