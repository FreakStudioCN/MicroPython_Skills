#!/usr/bin/env python3
"""Copy one MicroPythonOS App directory to a connected device."""

from __future__ import annotations

import argparse
import datetime
import shlex
import sys
from pathlib import Path

from _deploy_common import (
    board_matches,
    load_app_metadata,
    mpremote_script,
    normalize_app_metadata,
    make_check,
    query_device_info,
    resolve_app_dir,
    resolve_output_dir,
    resolve_repo_arg,
    run_mpremote,
    safe_fullname,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", required=True, help="App fullname")
    parser.add_argument("--board", required=True, help="Confirmed target board")
    parser.add_argument("--serial-port", required=True, help="Serial port for the device")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset the device on connect")
    parser.add_argument("--timeout", type=int, default=180, help="Deployment timeout in seconds")
    parser.add_argument("--output-dir", help="Output directory for deploy_result.json")
    args = parser.parse_args()

    repo = resolve_repo_arg(args.repo)
    fullname = safe_fullname(args.app_fullname)
    app_dir = resolve_app_dir(repo, fullname)
    output_dir = resolve_output_dir(repo, fullname, args.output_dir)
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
            "publisher": "",
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
        warnings.append("MPOS runtime probe failed; continuing with direct mpremote filesystem copy")
    if machine and not board_matches(args.board, machine):
        errors.append(f"target board mismatch: expected {args.board!r}, got {machine!r}")
    if not device.get("has_mpos"):
        warnings.append("mpos runtime was not verified on the target; direct copy only proves filesystem deployment")
    warnings.extend(device_probe.get("warnings", []))
    if device_probe.get("errors"):
        warnings.extend(device_probe.get("errors", []))

    mpremote_path = str(mpremote_script(repo))
    mkdir_command = [sys.executable, mpremote_path, "connect", args.serial_port, "fs", "mkdir", ":/apps"]
    install_command = [
        sys.executable,
        mpremote_path,
        "connect",
        args.serial_port,
        "fs",
        "cp",
        "-r",
        str(app_dir),
        ":/apps/",
    ]
    verify_command = [sys.executable, mpremote_path, "connect", args.serial_port, "fs", "ls", f":/apps/{fullname}"]
    preflight_proc = None
    mkdir_proc = None
    install_proc = None
    verify_proc = None

    if not errors:
        preflight_proc = run_mpremote(
            repo,
            ["fs", "ls", ":/"],
            serial_port=args.serial_port,
            timeout=min(args.timeout, 60),
        )
        if preflight_proc.returncode != 0:
            errors.append(f"mpremote filesystem preflight failed with {preflight_proc.returncode}")
            if preflight_proc.stdout:
                warnings.append(preflight_proc.stdout.strip()[-1000:])

    if not errors:
        mkdir_proc = run_mpremote(
            repo,
            ["fs", "mkdir", ":/apps"],
            serial_port=args.serial_port,
            timeout=min(args.timeout, 60),
        )
        if mkdir_proc.returncode != 0 and mkdir_proc.stdout:
            warnings.append("mpremote mkdir :/apps returned non-zero; continuing because the directory may already exist: " + mkdir_proc.stdout.strip()[-500:])

        install_proc = run_mpremote(
            repo,
            ["fs", "cp", "-r", str(app_dir), ":/apps/"],
            serial_port=args.serial_port,
            timeout=args.timeout,
        )
        if install_proc.returncode != 0:
            errors.append(f"mpremote app copy exited with {install_proc.returncode}")
            if install_proc.stdout:
                warnings.append(install_proc.stdout.strip()[-1000:])

    if not errors:
        verify_proc = run_mpremote(
            repo,
            ["fs", "ls", f":/apps/{fullname}"],
            serial_port=args.serial_port,
            timeout=min(args.timeout, 60),
        )
        if verify_proc.returncode != 0:
            errors.append(f"mpremote verification failed: /apps/{fullname} not listed")
            if verify_proc.stdout:
                warnings.append(verify_proc.stdout.strip()[-1000:])

    if not app_info.get("name"):
        errors.append("manifest name is missing")
    if not app_info.get("publisher"):
        errors.append("manifest publisher is missing")
    if not app_info.get("version"):
        errors.append("manifest version is missing")

    result = "failed" if errors else ("partial" if warnings else "success")
    target_ok = bool(args.board) and (not machine or board_matches(args.board, machine))
    preflight_ok = preflight_proc is not None and preflight_proc.returncode == 0
    deploy_ok = install_proc is not None and install_proc.returncode == 0
    verify_ok = verify_proc is not None and verify_proc.returncode == 0
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
            "hardware_available": True,
            "install_url": None,
            "web_url": None,
        },
        "command": {
            "primary": shlex.join(mkdir_command) + " && " + shlex.join(install_command),
            "secondary": [shlex.join(verify_command)],
        },
        "checks": [
            make_check(
                "target_confirmation",
                True,
                target_ok,
                "confirmed" if machine else "user_confirmed_unverified",
                warnings=[] if machine else ["board was confirmed by user but could not be probed from os.uname().machine"],
                errors=[] if target_ok else [f"expected {args.board!r}, got {machine!r}"],
                expected_board=args.board,
                observed_board=machine,
            ),
            make_check(
                "preflight",
                True,
                preflight_ok,
                "passed" if preflight_ok else "failed",
                warnings=device_probe.get("warnings", []),
                errors=[] if preflight_ok else ["mpremote could not list target root filesystem"],
                machine=machine,
                has_mpos=bool(device.get("has_mpos")),
                app_count=device.get("app_count"),
            ),
            make_check(
                "deployment_action",
                True,
                deploy_ok,
                "passed" if deploy_ok else "failed",
                warnings=[] if mkdir_proc is None or mkdir_proc.returncode == 0 else ["mkdir :/apps returned non-zero; copy was still attempted"],
                errors=[] if deploy_ok else ["mpremote app copy did not complete successfully"],
                installed_path=f"/apps/{fullname}",
            ),
            make_check(
                "post_deploy_refresh",
                True,
                verify_ok,
                "filesystem_verified" if verify_ok else "failed",
                warnings=[] if verify_ok else ["AppManager refresh was not used for direct-copy mode"],
                errors=[] if verify_ok else [f"{fullname} was not visible at /apps/{fullname} after copy"],
            ),
        ],
        "warnings": warnings,
        "errors": errors,
        "artifacts": [
            {"kind": "deploy_result", "path": str(output_path)},
        ],
        "handoff": {
            "next_skill": "mpos-publish-app" if result in {"success", "partial"} else "mpos-deploy-app",
            "next_step": (
                "Prepare the manual upystore publishing handoff."
                if result in {"success", "partial"}
                else "Retry deployment after checking the board, port, filesystem, and MicroPythonOS install state."
            ),
            "reason": (
                "The app directory was copied to /apps with direct mpremote filesystem copy."
                if result in {"success", "partial"}
                else "Direct mpremote copy did not produce a usable deploy record."
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
