#!/usr/bin/env python3
"""Package one MicroPythonOS App as a deterministic MPK."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emit_app_index_entry import DEFAULT_BASE_URL, emit_entry
from validate_mpos_app import resolve_app_dir, validate_app
from validate_mpk import validate_mpk


DEFAULT_REPO = Path("/home/leeqingshui/MicroPythonOS")
FIXED_ZIP_TIME = (2025, 1, 1, 0, 0, 0)
COMPRESSION_TYPES = {
    "stored": zipfile.ZIP_STORED,
    "deflated": zipfile.ZIP_DEFLATED,
}


def _display_path(path: Path, repo: Path | None = None) -> str:
    try:
        if repo is not None:
            return str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        pass
    return str(path)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _is_excluded(path: Path, app_dir: Path) -> bool:
    rel = path.relative_to(app_dir)
    parts = rel.parts
    name = path.name
    if any(part in {".git", "__pycache__", "__MACOSX"} for part in parts):
        return True
    return name.endswith(".pyc") or name.startswith("._") or name == ".DS_Store"


def _collect_entries(app_dir: Path) -> tuple[list[Path], list[Path]]:
    dirs: list[Path] = []
    files: list[Path] = []
    for path in app_dir.rglob("*"):
        if _is_excluded(path, app_dir):
            continue
        if path.is_dir():
            dirs.append(path)
        elif path.is_file():
            files.append(path)
    dirs.sort(key=lambda p: p.relative_to(app_dir).as_posix())
    files.sort(key=lambda p: p.relative_to(app_dir).as_posix())
    return dirs, files


def _dir_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (0o40755 << 16) | 0x10
    return info


def _file_info(name: str, compression: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = compression
    info.external_attr = 0o100644 << 16
    return info


def write_mpk(app_dir: Path, fullname: str, mpk_path: Path, compression: str) -> None:
    compression_type = COMPRESSION_TYPES[compression]
    if mpk_path.exists():
        mpk_path.unlink()
    mpk_path.parent.mkdir(parents=True, exist_ok=True)

    dirs, files = _collect_entries(app_dir)
    with zipfile.ZipFile(mpk_path, "w") as zf:
        zf.writestr(_dir_info(f"{fullname}/"), b"")
        for directory in dirs:
            arcname = f"{fullname}/{directory.relative_to(app_dir).as_posix().rstrip('/')}/"
            if arcname == f"{fullname}/":
                continue
            zf.writestr(_dir_info(arcname), b"")
        for file_path in files:
            arcname = f"{fullname}/{file_path.relative_to(app_dir).as_posix()}"
            zf.writestr(_file_info(arcname, compression_type), file_path.read_bytes())


def _load_optional_result(
    path_text: str | None,
    expected_schema: str,
    expected_phase: str,
    fullname: str,
    check_name: str,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    check = {
        "name": check_name,
        "required": False,
        "ok": True,
        "status": "not_provided",
        "path": path_text,
        "warnings": [],
        "errors": [],
    }
    if not path_text:
        warning = f"{check_name}.json was not provided; packaging continues with warning"
        check["warnings"].append(warning)
        warnings.append(warning)
        return check, warnings

    path = Path(path_text)
    if not path.is_file():
        warning = f"{path} does not exist; packaging continues with warning"
        check["status"] = "missing"
        check["warnings"].append(warning)
        warnings.append(warning)
        return check, warnings

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - malformed optional input is a warning, not package blocker.
        warning = f"Failed to read {path}: {exc}; packaging continues with warning"
        check["status"] = "invalid_json"
        check["warnings"].append(warning)
        warnings.append(warning)
        return check, warnings

    if data.get("schema_version") != expected_schema:
        check["warnings"].append(f"{path} schema_version is {data.get('schema_version')!r}, expected {expected_schema!r}")
    if data.get("phase") != expected_phase:
        check["warnings"].append(f"{path} phase is {data.get('phase')!r}, expected {expected_phase!r}")
    app = data.get("app", {})
    if isinstance(app, dict) and app.get("fullname") != fullname:
        check["warnings"].append(f"{path} app.fullname {app.get('fullname')!r} does not match {fullname!r}")
    if data.get("result") != "success":
        check["warnings"].append(f"{path} result is {data.get('result')!r}; packaging continues with warning")

    check["status"] = "passed" if not check["warnings"] else "warning"
    warnings.extend(check["warnings"])
    return check, warnings


def _check_from_validation(name: str, validation: dict[str, Any], required: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "required": required,
        "ok": bool(validation.get("ok")),
        "status": "passed" if validation.get("ok") else "failed",
        "warnings": list(validation.get("warnings", [])),
        "errors": list(validation.get("errors", [])),
    }


def package_app(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    app_dir = resolve_app_dir(repo, args.app_fullname, args.app_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else (
        repo / "tmp" / "mpos-package-app" / (args.app_fullname or app_dir.name)
    )
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    app_validation = validate_app(repo, app_dir, args.app_fullname)
    checks.append(_check_from_validation("app_validation", app_validation, True))
    warnings.extend(app_validation.get("warnings", []))
    errors.extend(app_validation.get("errors", []))

    app_info = app_validation.get("app", {})
    fullname = app_info.get("fullname") or args.app_fullname or app_dir.name
    version = app_info.get("version")
    name = app_info.get("name")

    gen_check, gen_warnings = _load_optional_result(
        args.generation_result,
        "mpos-gen-app-v1",
        "generate",
        fullname,
        "generation_result",
    )
    test_check, test_warnings = _load_optional_result(
        args.app_test_result,
        "mpos-test-app-v1",
        "test-app",
        fullname,
        "app_test_result",
    )
    checks.extend([gen_check, test_check])
    warnings.extend(gen_warnings)
    warnings.extend(test_warnings)

    mpk_path = output_dir / f"{fullname}_{version or 'unknown'}.mpk"
    app_index_path = output_dir / "app_index_entry.json"
    mpk_validation: dict[str, Any] = {
        "ok": False,
        "warnings": [],
        "errors": ["Skipped because App validation failed"],
    }
    app_index_entry = None

    if not errors:
        write_mpk(app_dir, fullname, mpk_path, args.compression)
        app_index_entry, index_warnings, index_errors = emit_entry(
            repo,
            app_dir,
            fullname,
            args.base_url,
        )
        warnings.extend(index_warnings)
        errors.extend(index_errors)
        if app_index_entry is not None:
            _write_json(app_index_path, app_index_entry)
        mpk_validation = validate_mpk(
            mpk_path,
            fullname,
            repo=repo,
            install_check=args.install_check,
            install_root=output_dir / "install-check" if args.install_check else None,
        )
        warnings.extend(mpk_validation.get("warnings", []))
        errors.extend(mpk_validation.get("errors", []))

    checks.append(_check_from_validation("mpk_validation", mpk_validation, True))
    checks.append(
        {
            "name": "app_index_entry",
            "required": True,
            "ok": app_index_entry is not None and app_index_path.is_file(),
            "status": "written" if app_index_entry is not None and app_index_path.is_file() else "failed",
            "warnings": [],
            "errors": [] if app_index_entry is not None and app_index_path.is_file() else ["app_index_entry.json was not written"],
        }
    )
    if args.install_check:
        install_check = mpk_validation.get("install_check") or {}
        install_ok = bool(mpk_validation.get("ok")) and bool(install_check.get("result", {}).get("ok"))
        checks.append(
            {
                "name": "temporary_install_validation",
                "required": True,
                "ok": install_ok,
                "status": "passed" if install_ok else "failed",
                "root": install_check.get("root"),
                "warnings": [
                    warning for warning in mpk_validation.get("warnings", [])
                    if warning.startswith("temporary install:")
                ],
                "errors": [
                    error for error in mpk_validation.get("errors", [])
                    if error.startswith("temporary install:")
                ],
            }
        )

    package_info = {
        "mpk_path": _display_path(mpk_path, repo),
        "compression": args.compression,
        "size_bytes": mpk_path.stat().st_size if mpk_path.is_file() else 0,
        "sha256": _sha256(mpk_path) if mpk_path.is_file() else "0" * 64,
    }
    entry_info = {
        "path": _display_path(app_index_path, repo),
        "base_url": args.base_url.rstrip("/"),
        "download_url": app_index_entry.get("download_url") if app_index_entry else "",
        "icon_url": app_index_entry.get("icon_url") if app_index_entry else "",
    }

    required_failed = any(check["required"] and not check["ok"] for check in checks)
    result = "failed" if required_failed or errors else ("partial" if warnings else "success")
    package_result = {
        "schema_version": "mpos-package-app-v1",
        "phase": "package",
        "result": result,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "app": {
            "fullname": fullname,
            "name": name,
            "version": version,
            "app_dir": _display_path(app_dir, repo),
            "manifest": app_info.get("manifest"),
            "icon": app_info.get("icon"),
            "layout": app_validation.get("layout", {}).get("manifest"),
        },
        "inputs": {
            "generation_result": args.generation_result,
            "app_test_result": args.app_test_result,
            "test_policy": "warn_only",
        },
        "package": package_info,
        "app_index_entry": entry_info,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "artifacts": [
            {"kind": "mpk", "path": package_info["mpk_path"]},
            {"kind": "app_index_entry", "path": entry_info["path"]},
            {"kind": "package_result", "path": _display_path(output_dir / "package_result.json", repo)},
        ],
        "handoff": {
            "next_skill": "mpos-publish-app" if result in {"success", "partial"} else "mpos-gen-app",
            "reason": (
                "MPK and app_index entry were generated and validated; upload is a separate publishing step."
                if result in {"success", "partial"}
                else "Package required checks failed; repair the App or package script before publishing."
            ),
        },
    }
    _write_json(output_dir / "package_result.json", package_result)
    return package_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", help="App fullname")
    parser.add_argument("--app-dir", help="Explicit App directory")
    parser.add_argument("--output-dir", help="Package output directory")
    parser.add_argument("--compression", choices=sorted(COMPRESSION_TYPES), default="stored", help="MPK compression")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base AppStore URL for app_index_entry.json")
    parser.add_argument("--generation-result", help="Optional generation_result.json")
    parser.add_argument("--app-test-result", help="Optional app_test_result.json")
    parser.add_argument("--install-check", action="store_true", help="Temporarily extract MPK and validate installed tree")
    parser.add_argument("--clean", action="store_true", help="Remove output dir before packaging")
    args = parser.parse_args()

    try:
        result = package_app(args)
    except Exception as exc:  # noqa: BLE001 - CLI should report unexpected package failures.
        print(f"ERROR: package failed: {exc}", file=sys.stderr)
        return 2

    for warning in result.get("warnings", []):
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in result.get("errors", []):
        print(f"ERROR: {error}", file=sys.stderr)

    package_result_path = Path(args.output_dir).resolve() / "package_result.json" if args.output_dir else (
        Path(args.repo).resolve() / "tmp" / "mpos-package-app" / (args.app_fullname or result["app"]["fullname"]) / "package_result.json"
    )
    print(f"{result['result'].upper()}: {package_result_path}")
    return 0 if result["result"] in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
