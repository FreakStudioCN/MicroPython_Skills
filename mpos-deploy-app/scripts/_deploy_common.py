#!/usr/bin/env python3
"""Shared helpers for mpos-deploy-app scripts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO = Path("/home/leeqingshui/MicroPythonOS")
DEFAULT_OUTPUT_ROOT = Path("tmp/mpos-deploy-app")
DEFAULT_INSTALL_URL = "https://install.micropythonos.com/"
DEFAULT_WEB_URL = "http://127.0.0.1:8080/"

VALID_RESULTS = {"success", "partial", "failed"}
VALID_MODES = {
    "desktop-preview",
    "web-preview",
    "device-copy",
    "mpk-install",
    "install-site",
    "local-flash",
}
VALID_TRANSPORTS = {"desktop", "http", "serial", "usb", "browser"}
VALID_NEXT_SKILLS = {None, "mpos-test-app", "mpos-gen-app", "mpos-package-app", "mpos-plan-app", "mpos-publish-app"}
FULLNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_fullname(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("app fullname must be a non-empty string")
    if not FULLNAME_RE.fullmatch(value):
        raise ValueError("app fullname may contain only letters, digits, dots, underscores, and hyphens")
    if "/" in value or "\\" in value or ".." in value.split("."):
        raise ValueError("app fullname must not contain path separators or '..' components")
    return value


def normalize_board_label(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value.upper() if ch.isalnum())


def board_matches(expected: str | None, observed: str | None) -> bool:
    if not expected or not observed:
        return False
    expected_norm = normalize_board_label(expected)
    observed_norm = normalize_board_label(observed)
    if not expected_norm or not observed_norm:
        return False
    return expected_norm in observed_norm or observed_norm in expected_norm


def resolve_app_dir(repo: Path, fullname: str) -> Path:
    return repo / "internal_filesystem" / "apps" / safe_fullname(fullname)


def default_output_dir(repo: Path, fullname: str) -> Path:
    return repo / DEFAULT_OUTPUT_ROOT / safe_fullname(fullname)


def find_manifest_path(app_dir: Path) -> tuple[Path, str]:
    root_manifest = app_dir / "MANIFEST.JSON"
    if root_manifest.is_file():
        return root_manifest, "flat"
    legacy_manifest = app_dir / "META-INF" / "MANIFEST.JSON"
    if legacy_manifest.is_file():
        return legacy_manifest, "legacy"
    raise FileNotFoundError(f"Missing MANIFEST.JSON in {app_dir}")


def find_icon_path(app_dir: Path) -> tuple[Path, str]:
    root_icon = app_dir / "icon_64x64.png"
    if root_icon.is_file():
        return root_icon, "flat"
    legacy_icon = app_dir / "res" / "mipmap-mdpi" / "icon_64x64.png"
    if legacy_icon.is_file():
        return legacy_icon, "legacy"
    raise FileNotFoundError(f"Missing icon_64x64.png in {app_dir}")


def load_app_metadata(app_dir: Path, repo: Path | None = None) -> dict[str, Any]:
    manifest_path, layout = find_manifest_path(app_dir)
    icon_path, icon_layout = find_icon_path(app_dir)
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"Manifest must be a JSON object: {manifest_path}")
    return {
        "fullname": manifest.get("fullname", app_dir.name),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "app_dir": display_path(app_dir, repo),
        "manifest": display_path(manifest_path, repo),
        "icon": display_path(icon_path, repo),
        "layout": layout,
        "icon_layout": icon_layout,
        "manifest_data": manifest,
    }


def normalize_app_metadata(app_info: dict[str, Any], app_dir: Path, fullname: str) -> dict[str, Any]:
    normalized = dict(app_info)
    normalized["fullname"] = str(normalized.get("fullname") or fullname)
    normalized["name"] = str(normalized.get("name") or fullname)
    normalized["version"] = str(normalized.get("version") or "unknown")
    normalized["app_dir"] = str(normalized.get("app_dir") or app_dir)
    normalized["manifest"] = str(normalized.get("manifest") or (app_dir / "MANIFEST.JSON"))
    icon_value = normalized.get("icon")
    if isinstance(icon_value, str) and icon_value.strip():
        normalized["icon"] = icon_value
    else:
        normalized["icon"] = str(app_dir / "icon_64x64.png")
    normalized["layout"] = str(normalized.get("layout") or "missing")
    normalized.pop("manifest_data", None)
    normalized.pop("icon_layout", None)
    return normalized


def display_path(path: Path | str | None, repo: Path | None = None) -> str | None:
    if path is None:
        return None
    value = Path(path)
    if repo is not None:
        try:
            return str(value.resolve().relative_to(repo.resolve()))
        except ValueError:
            pass
    return str(value)


def load_json(path: str | Path) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    env = kwargs.pop("env", None)
    if env is None:
        env = os.environ.copy()
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        env=env,
        **kwargs,
    )


def tail_text(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def controller_script(repo: Path) -> Path:
    return repo / "scripts" / "mpos_controller.py"


def mpremote_script(repo: Path) -> Path:
    return repo / "lvgl_micropython" / "lib" / "micropython" / "tools" / "mpremote" / "mpremote.py"


def controller_command(
    repo: Path,
    action: str,
    args: list[str] | None = None,
    *,
    serial_port: str | None = None,
    baudrate: int = 115200,
    no_reset: bool = False,
    binary: str | None = None,
    heapsize: str = "16M",
) -> list[str]:
    command = [sys.executable, str(controller_script(repo))]
    if serial_port:
        command += ["--serial-port", serial_port, "--baudrate", str(baudrate)]
        if no_reset:
            command.append("--no-reset")
    else:
        if binary:
            command += ["--binary", binary]
        command += ["--heapsize", heapsize]
    command.append(action)
    command.extend(args or [])
    return command


def controller_exec(
    repo: Path,
    code: str,
    *,
    serial_port: str | None = None,
    baudrate: int = 115200,
    no_reset: bool = False,
    binary: str | None = None,
    heapsize: str = "16M",
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return run(
        controller_command(
            repo,
            "exec",
            [code],
            serial_port=serial_port,
            baudrate=baudrate,
            no_reset=no_reset,
            binary=binary,
            heapsize=heapsize,
        ),
        cwd=str(repo),
        timeout=timeout,
    )


def mpremote_command(repo: Path, args: list[str]) -> list[str]:
    return [sys.executable, str(mpremote_script(repo))] + args


def run_mpremote(repo: Path, args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run(mpremote_command(repo, args), cwd=str(repo), timeout=timeout)


def inspect_mpk(mpk_path: Path, fullname: str) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    entries: list[str] = []
    if not mpk_path.is_file():
        errors.append(f"MPK file does not exist: {mpk_path}")
        return {"ok": False, "entries": entries, "warnings": warnings, "errors": errors}

    try:
        with zipfile.ZipFile(mpk_path, "r") as zf:
            entries = [info.filename for info in zf.infolist()]
            if not entries:
                errors.append("MPK is empty")
            else:
                expected_top = fullname.rstrip("/") + "/"
                if entries[0] != expected_top:
                    errors.append(f"First entry must be {expected_top!r}, got {entries[0]!r}")
                if any(not name.startswith(expected_top) for name in entries):
                    bad = [name for name in entries if not name.startswith(expected_top)]
                    errors.append("Entries outside top-level dir: " + ", ".join(bad[:5]))
            bad_file = zf.testzip()
            if bad_file:
                errors.append(f"ZIP CRC/read test failed at {bad_file!r}")
    except zipfile.BadZipFile as exc:
        errors.append(f"Invalid ZIP file: {exc}")
    return {"ok": not errors, "entries": entries, "warnings": warnings, "errors": errors}


def extract_json_object(text: str) -> dict[str, Any]:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    raise ValueError("no JSON object found in output")


def query_device_info(
    repo: Path,
    serial_port: str,
    *,
    baudrate: int = 115200,
    no_reset: bool = False,
    timeout: int = 120,
) -> dict[str, Any]:
    code = device_probe_code()
    payload = {
        "ok": False,
        "returncode": None,
        "stdout": "",
        "device": {},
        "warnings": [],
        "errors": [],
    }
    try:
        proc = controller_exec(
            repo,
            code,
            serial_port=serial_port,
            baudrate=baudrate,
            no_reset=no_reset,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - return structured probe failures instead of raising.
        payload["errors"].append(f"controller probe failed: {exc}")
        return payload

    payload["returncode"] = proc.returncode
    payload["stdout"] = proc.stdout
    if proc.returncode == 0:
        try:
            payload["device"] = extract_json_object(proc.stdout)
        except Exception as exc:  # noqa: BLE001 - parse failures should be reported, not raised.
            payload["errors"].append(f"failed to parse device info: {exc}")
            return payload
        payload["ok"] = True
        device = payload["device"]
        if not device.get("machine"):
            payload["warnings"].append("device did not report os.uname().machine")
        if not device.get("has_mpos"):
            payload["warnings"].append("mpos is not importable on the target yet")
    else:
        payload["errors"].append("controller probe failed")
    return payload


def device_probe_code() -> str:
    return (
        "import json, os, sys\n"
        "payload = {\n"
        "    'machine': None,\n"
        "    'sys_platform': sys.platform,\n"
        "    'has_mpos': False,\n"
        "    'app_count': None,\n"
        "}\n"
        "try:\n"
        "    payload['machine'] = os.uname().machine\n"
        "except Exception:\n"
        "    pass\n"
        "try:\n"
        "    from mpos import AppManager\n"
        "    payload['has_mpos'] = True\n"
        "    try:\n"
        "        payload['app_count'] = len(AppManager.get_app_list())\n"
        "    except Exception:\n"
        "        pass\n"
        "except Exception:\n"
        "    payload['has_mpos'] = False\n"
        "print(json.dumps(payload, sort_keys=True))\n"
    )


def query_installed_apps(
    repo: Path,
    serial_port: str,
    *,
    baudrate: int = 115200,
    no_reset: bool = False,
    timeout: int = 120,
) -> dict[str, Any]:
    code = installed_apps_code()
    payload = {
        "ok": False,
        "returncode": None,
        "stdout": "",
        "apps": [],
        "warnings": [],
        "errors": [],
    }
    try:
        proc = controller_exec(
            repo,
            code,
            serial_port=serial_port,
            baudrate=baudrate,
            no_reset=no_reset,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - return structured probe failures instead of raising.
        payload["errors"].append(f"controller app listing failed: {exc}")
        return payload

    payload["returncode"] = proc.returncode
    payload["stdout"] = proc.stdout
    if proc.returncode == 0:
        try:
            payload["apps"] = extract_json_object(proc.stdout).get("apps", [])
        except Exception as exc:  # noqa: BLE001 - parse failures should be reported, not raised.
            payload["errors"].append(f"failed to parse app list: {exc}")
            return payload
        payload["ok"] = True
    else:
        payload["errors"].append("controller app listing failed")
    return payload


def installed_apps_code() -> str:
    return (
        "import json\n"
        "from mpos import AppManager\n"
        "print(json.dumps({'apps': [a.fullname for a in AppManager.get_app_list()]}, sort_keys=True))\n"
    )


def make_check(
    name: str,
    required: bool,
    ok: bool,
    status: str,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    check = {
        "name": name,
        "required": required,
        "ok": ok,
        "status": status,
        "warnings": list(warnings or []),
        "errors": list(errors or []),
    }
    check.update(extra)
    return check


def build_result(
    *,
    app: dict[str, Any],
    mode: str,
    transport: str | None,
    board: str | None,
    port: str | None,
    device_id: str | None = None,
    confirmed: bool = False,
    install_url: str | None = None,
    web_url: str | None = None,
    command: dict[str, Any] | None = None,
    result: str = "partial",
    checks: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    next_skill: str | None = None,
    next_step: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "mpos-deploy-app-v1",
        "phase": "deploy",
        "result": result,
        "created_at_utc": utc_now(),
        "app": app,
        "deploy": {
            "mode": mode,
            "transport": transport,
            "board": board,
            "port": port,
            "device_id": device_id,
            "confirmed": confirmed,
            "install_url": install_url,
            "web_url": web_url,
        },
        "command": command or {"primary": "", "secondary": []},
        "checks": checks or [],
        "warnings": list(warnings or []),
        "errors": list(errors or []),
        "artifacts": artifacts or [],
        "handoff": {
            "next_skill": next_skill,
            "next_step": next_step,
            "reason": reason,
        },
    }
    return payload
