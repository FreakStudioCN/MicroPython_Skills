#!/usr/bin/env python3
"""Upload and install one MPK on a connected MicroPythonOS device."""

from __future__ import annotations

import argparse
import datetime
import shlex
import subprocess
from pathlib import Path

from _deploy_common import (
    DEFAULT_REPO,
    board_matches,
    controller_command,
    default_output_dir,
    inspect_mpk,
    load_app_metadata,
    installed_apps_code,
    normalize_app_metadata,
    make_check,
    mpremote_script,
    query_device_info,
    query_installed_apps,
    resolve_app_dir,
    run_mpremote,
    safe_fullname,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", required=True, help="App fullname")
    parser.add_argument("--mpk-path", required=True, help="Path to the MPK file")
    parser.add_argument("--board", required=True, help="Confirmed target board")
    parser.add_argument("--serial-port", required=True, help="Serial port for the device")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset the device on connect")
    parser.add_argument("--timeout", type=int, default=240, help="Deployment timeout in seconds")
    parser.add_argument("--output-dir", help="Output directory for deploy_result.json")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    fullname = safe_fullname(args.app_fullname)
    app_dir = resolve_app_dir(repo, fullname)
    mpk_path = Path(args.mpk_path).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else default_output_dir(repo, fullname)
    output_path = output_dir / "deploy_result.json"

    warnings: list[str] = []
    errors: list[str] = []

    if not app_dir.is_dir():
        warnings.append(f"App directory not found, continuing with MPK only: {app_dir}")
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
        warnings.append(str(exc))

    mpk_info = inspect_mpk(mpk_path, fullname)
    warnings.extend(mpk_info.get("warnings", []))
    errors.extend(mpk_info.get("errors", []))

    device_probe = query_device_info(
        repo,
        args.serial_port,
        baudrate=args.baudrate,
        no_reset=args.no_reset,
        timeout=min(args.timeout, 120),
    )
    device = device_probe.get("device", {}) if isinstance(device_probe.get("device"), dict) else {}
    machine = device.get("machine")
    if not device_probe.get("ok"):
        errors.append("device probe failed")
    if not board_matches(args.board, machine):
        errors.append(f"target board mismatch: expected {args.board!r}, got {machine!r}")
    if not device.get("has_mpos"):
        errors.append("mpos is not available on the target")
    warnings.extend(device_probe.get("warnings", []))
    errors.extend(device_probe.get("errors", []))
    preflight_warnings = list(device_probe.get("warnings", [])) + list(mpk_info.get("warnings", []))
    preflight_errors = list(device_probe.get("errors", [])) + list(mpk_info.get("errors", []))

    remote_temp_path = f"/tmp/{mpk_path.name}"
    dest_folder = f"apps/{fullname}"
    install_code = (
        "from mpos.content.app_manager import AppManager; "
        f"AppManager.install_mpk({remote_temp_path!r}, {dest_folder!r})"
    )
    mpremote_path = str(mpremote_script(repo))
    install_command = controller_command(
        repo,
        "exec",
        [install_code],
        serial_port=args.serial_port,
        baudrate=args.baudrate,
        no_reset=args.no_reset,
    )
    install_proc = None
    if not errors:
        mkdir_proc = run_mpremote(repo, ["fs", "mkdir", ":/tmp"], timeout=min(args.timeout, 60))
        if mkdir_proc.returncode != 0:
            if mkdir_proc.stdout:
                warnings.append(mkdir_proc.stdout.strip()[-1000:])
        copy_proc = run_mpremote(
            repo,
            ["fs", "cp", str(mpk_path), f":{remote_temp_path}"],
            timeout=min(args.timeout, 120),
        )
        if copy_proc.returncode != 0:
            errors.append(f"failed to upload MPK to {remote_temp_path}")
            if copy_proc.stdout:
                warnings.append(copy_proc.stdout.strip()[-1000:])
        else:
            install_proc = subprocess.run(
                install_command,
                cwd=str(repo),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=args.timeout,
                check=False,
            )
            if install_proc.returncode != 0:
                errors.append(f"AppManager.install_mpk exited with {install_proc.returncode}")
                if install_proc.stdout:
                    warnings.append(install_proc.stdout.strip()[-1000:])

    installed_apps = []
    if install_proc is not None and install_proc.returncode == 0 and not errors:
        verify = query_installed_apps(
            repo,
            args.serial_port,
            baudrate=args.baudrate,
            no_reset=True,
            timeout=min(args.timeout, 120),
        )
        warnings.extend(verify.get("warnings", []))
        errors.extend(verify.get("errors", []))
        if not verify.get("ok"):
            errors.append("installed app verification failed")
        else:
            installed_apps = verify.get("apps", [])
            if fullname not in installed_apps:
                errors.append(f"{fullname} not found after MPK install")

    if not app_info.get("name"):
        warnings.append("manifest name is missing")
    if not app_info.get("version"):
        warnings.append("manifest version is missing")

    result = "failed" if errors else ("partial" if warnings else "success")
    deploy_result = {
        "schema_version": "mpos-deploy-app-v1",
        "phase": "deploy",
        "result": result,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "app": app_info,
        "deploy": {
            "mode": "mpk-install",
            "transport": "serial",
            "board": args.board,
            "port": args.serial_port,
            "device_id": machine,
            "confirmed": True,
            "install_url": None,
            "web_url": None,
        },
        "command": {
            "primary": " && ".join(
                [
                    shlex.join([mpremote_path, "fs", "mkdir", ":/tmp"]),
                    shlex.join([mpremote_path, "fs", "cp", str(mpk_path), f":{remote_temp_path}"]),
                    shlex.join(install_command),
                ]
            ),
            "secondary": [
                shlex.join(
                    controller_command(
                        repo,
                        "exec",
                        [installed_apps_code()],
                        serial_port=args.serial_port,
                        baudrate=args.baudrate,
                        no_reset=True,
                    )
                )
            ],
        },
        "checks": [
            make_check(
                "target_confirmation",
                True,
                board_matches(args.board, machine),
                "confirmed" if board_matches(args.board, machine) else "failed",
                expected_board=args.board,
                observed_board=machine,
            ),
            make_check(
                "preflight",
                True,
                device_probe.get("ok", False) and device.get("has_mpos", False) and mpk_info.get("ok", False),
                "passed" if device_probe.get("ok") and device.get("has_mpos") and mpk_info.get("ok") else "failed",
                warnings=preflight_warnings,
                errors=preflight_errors,
                machine=machine,
                app_count=device.get("app_count"),
                mpk_entries=len(mpk_info.get("entries", [])),
            ),
            make_check(
                "deployment_action",
                True,
                install_proc is not None and install_proc.returncode == 0,
                "passed" if install_proc is not None and install_proc.returncode == 0 else "failed",
                warnings=[install_proc.stdout.strip()] if install_proc and install_proc.stdout and install_proc.returncode != 0 else [],
                errors=[] if install_proc is not None and install_proc.returncode == 0 else ["install_mpk did not complete successfully"],
                remote_temp_path=remote_temp_path,
            ),
            make_check(
                "post_deploy_refresh",
                True,
                fullname in installed_apps,
                "passed" if fullname in installed_apps else "failed",
                errors=[] if fullname in installed_apps else [f"{fullname} was not visible after refresh"],
                installed_count=len(installed_apps),
            ),
        ],
        "warnings": warnings,
        "errors": errors,
        "artifacts": [{"kind": "deploy_result", "path": str(output_path)}],
        "handoff": {
            "next_skill": "mpos-test-app" if result != "failed" else "mpos-package-app",
            "next_step": "Run mpos-test-app if you want a runtime smoke check after the MPK install.",
            "reason": "The MPK was installed on the target device and the registry was refreshed.",
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
