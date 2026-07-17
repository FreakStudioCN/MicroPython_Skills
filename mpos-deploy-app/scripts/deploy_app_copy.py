#!/usr/bin/env python3
"""Copy one MicroPythonOS App directory to a connected device."""

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
    installed_apps_code,
    load_app_metadata,
    normalize_app_metadata,
    make_check,
    query_device_info,
    query_installed_apps,
    resolve_app_dir,
    safe_fullname,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", required=True, help="App fullname")
    parser.add_argument("--board", required=True, help="Confirmed target board")
    parser.add_argument("--serial-port", required=True, help="Serial port for the device")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset the device on connect")
    parser.add_argument("--timeout", type=int, default=180, help="Deployment timeout in seconds")
    parser.add_argument("--output-dir", help="Output directory for deploy_result.json")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    fullname = safe_fullname(args.app_fullname)
    app_dir = resolve_app_dir(repo, fullname)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else default_output_dir(repo, fullname)
    output_path = output_dir / "deploy_result.json"

    warnings: list[str] = []
    errors: list[str] = []

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

    install_command = controller_command(
        repo,
        "installapp",
        [str(app_dir)],
        serial_port=args.serial_port,
        baudrate=args.baudrate,
        no_reset=args.no_reset,
    )
    install_proc = None
    if not errors:
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
            errors.append(f"installapp exited with {install_proc.returncode}")
            if install_proc.stdout:
                warnings.append(install_proc.stdout.strip()[-1000:])

    installed_apps = []
    if not errors:
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
                errors.append(f"{fullname} not found after install")

    if not app_info.get("name"):
        errors.append("manifest name is missing")
    if not app_info.get("version"):
        errors.append("manifest version is missing")

    result = "failed" if errors else ("partial" if warnings else "success")
    command_secondary = [
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
    ]
    deploy_result = {
        "schema_version": "mpos-deploy-app-v1",
        "phase": "deploy",
        "result": result,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "app": app_info,
        "deploy": {
            "mode": "device-copy",
            "transport": "serial",
            "board": args.board,
            "port": args.serial_port,
            "device_id": machine,
            "confirmed": True,
            "install_url": None,
            "web_url": None,
        },
        "command": {
            "primary": shlex.join(install_command),
            "secondary": command_secondary,
        },
        "checks": [
            make_check(
                "target_confirmation",
                True,
                board_matches(args.board, machine),
                "confirmed" if board_matches(args.board, machine) else "failed",
                warnings=[],
                errors=[] if board_matches(args.board, machine) else [f"expected {args.board!r}, got {machine!r}"],
                expected_board=args.board,
                observed_board=machine,
            ),
            make_check(
                "preflight",
                True,
                device_probe.get("ok", False) and device.get("has_mpos", False),
                "passed" if device_probe.get("ok") and device.get("has_mpos") else "failed",
                warnings=device_probe.get("warnings", []),
                errors=device_probe.get("errors", []),
                machine=machine,
                app_count=device.get("app_count"),
            ),
            make_check(
                "deployment_action",
                True,
                install_proc is not None and install_proc.returncode == 0,
                "passed" if install_proc is not None and install_proc.returncode == 0 else "failed",
                warnings=[install_proc.stdout.strip()] if install_proc and install_proc.stdout and install_proc.returncode != 0 else [],
                errors=[] if install_proc is not None and install_proc.returncode == 0 else ["installapp did not complete successfully"],
                installed_path=str(app_dir),
            ),
            make_check(
                "post_deploy_refresh",
                True,
                fullname in installed_apps,
                "passed" if fullname in installed_apps else "failed",
                warnings=[],
                errors=[] if fullname in installed_apps else [f"{fullname} was not visible after refresh"],
            ),
        ],
        "warnings": warnings,
        "errors": errors,
        "artifacts": [
            {"kind": "deploy_result", "path": str(output_path)},
        ],
        "handoff": {
            "next_skill": "mpos-test-app" if result != "failed" else "mpos-gen-app",
            "next_step": "Run mpos-test-app if you want a runtime smoke check after deployment.",
            "reason": "The app was copied to the target device and the registry was refreshed.",
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
