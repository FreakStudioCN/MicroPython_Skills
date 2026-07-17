#!/usr/bin/env python3
"""Validate MPK ZIP structure using MicroPythonOS streaming install rules."""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
import zipfile
from pathlib import Path
from typing import Any

from validate_mpos_app import SCHEMA_VERSION as APP_VALIDATION_SCHEMA
from validate_mpos_app import validate_app


SCHEMA_VERSION = "mpos-mpk-validation-v1"
LOCAL_HEADER_MAGIC = b"PK\x03\x04"
LOCAL_HEADER_STRUCT = "<4s2B4HL2L2H"
LOCAL_HEADER_SIZE = struct.calcsize(LOCAL_HEADER_STRUCT)
FLAG_DATA_DESCRIPTOR = 0x08
ZIP_STORED = 0
ZIP_DEFLATED = 8


def _display_path(path: Path, repo: Path | None = None) -> str:
    try:
        if repo is not None:
            return str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        pass
    return str(path)


def _decode_name(raw_name: bytes) -> str:
    try:
        return raw_name.decode("utf-8")
    except UnicodeDecodeError:
        return raw_name.decode("latin-1")


def _is_illegal_member(name: str) -> bool:
    parts = [part for part in name.split("/") if part]
    if any(part in {".git", "__pycache__", "__MACOSX"} for part in parts):
        return True
    last = parts[-1] if parts else ""
    return last.endswith(".pyc") or last.startswith("._") or last == ".DS_Store"


def _is_unsafe_member(name: str) -> bool:
    parts = [part for part in name.split("/") if part]
    return name.startswith("/") or any(part == ".." for part in parts)


def parse_local_headers(mpk_path: Path, fullname: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    data = mpk_path.read_bytes()
    offset = 0
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    while offset + LOCAL_HEADER_SIZE <= len(data):
        if data[offset:offset + 4] != LOCAL_HEADER_MAGIC:
            if not entries:
                errors.append("MPK does not start with a ZIP local file header")
            break

        values = struct.unpack(LOCAL_HEADER_STRUCT, data[offset:offset + LOCAL_HEADER_SIZE])
        flag_bits = values[3]
        compression_method = values[4]
        compressed_size = values[8]
        uncompressed_size = values[9]
        filename_length = values[10]
        extra_length = values[11]
        header_end = offset + LOCAL_HEADER_SIZE + filename_length + extra_length
        if header_end > len(data):
            errors.append("Truncated local file header")
            break

        raw_name = data[offset + LOCAL_HEADER_SIZE:offset + LOCAL_HEADER_SIZE + filename_length]
        name = _decode_name(raw_name)
        entry = {
            "name": name,
            "offset": offset,
            "flag_bits": flag_bits,
            "compression_method": compression_method,
            "compressed_size": compressed_size,
            "uncompressed_size": uncompressed_size,
        }
        entries.append(entry)

        if flag_bits & FLAG_DATA_DESCRIPTOR:
            errors.append(f"Entry {name!r} uses data descriptor flag, unsupported by StreamingUnzip")
        if compression_method not in {ZIP_STORED, ZIP_DEFLATED}:
            errors.append(f"Entry {name!r} uses unsupported compression method {compression_method}")
        if _is_unsafe_member(name):
            errors.append(f"Entry {name!r} is unsafe")
        if _is_illegal_member(name):
            errors.append(f"Entry {name!r} should not be packaged")

        offset = header_end + compressed_size

    if not entries:
        errors.append("No local file headers found")
        return entries, warnings, errors

    first_name = entries[0]["name"]
    expected_top = fullname + "/"
    if first_name != expected_top:
        errors.append(f"First entry must be {expected_top!r}, got {first_name!r}")

    for entry in entries[1:]:
        name = entry["name"]
        if not name.startswith(expected_top):
            errors.append(f"Entry {name!r} is outside top-level dir {expected_top!r}")

    top_dirs = {
        entry["name"].split("/", 1)[0]
        for entry in entries
        if entry["name"] and not entry["name"].startswith("/")
    }
    if top_dirs != {fullname}:
        errors.append(f"MPK must contain exactly one top-level dir {fullname!r}, got {sorted(top_dirs)!r}")

    trailing = len(data) - offset
    if trailing < 0:
        errors.append("Local header sizes extend past end of file")

    return entries, warnings, errors


def validate_zip_directory(mpk_path: Path, fullname: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(mpk_path, "r") as zf:
            bad_file = zf.testzip()
            if bad_file:
                errors.append(f"ZIP CRC/read test failed at {bad_file!r}")
            for info in zf.infolist():
                entries.append(
                    {
                        "name": info.filename,
                        "compress_type": info.compress_type,
                        "file_size": info.file_size,
                        "compress_size": info.compress_size,
                    }
                )
                if _is_unsafe_member(info.filename):
                    errors.append(f"Central directory entry {info.filename!r} is unsafe")
                if _is_illegal_member(info.filename):
                    errors.append(f"Central directory entry {info.filename!r} should not be packaged")
                if not info.filename.startswith(fullname + "/"):
                    errors.append(f"Central directory entry {info.filename!r} is outside {fullname!r}")
    except zipfile.BadZipFile as exc:
        errors.append(f"Invalid ZIP file: {exc}")
    return entries, warnings, errors


def run_install_check(
    mpk_path: Path,
    fullname: str,
    install_root: Path,
    repo: Path | None,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    dest = install_root / fullname

    if dest.exists():
        shutil.rmtree(dest)
    install_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(mpk_path, "r") as zf:
            zf.extractall(install_root)
    except Exception as exc:  # noqa: BLE001 - CLI validation should report extraction failures.
        errors.append(f"Temporary install extraction failed: {exc}")
        return None, warnings, errors

    if not dest.is_dir():
        errors.append(f"Temporary install did not create {dest}")
        return None, warnings, errors

    app_validation = validate_app(repo, dest, fullname)
    if app_validation.get("warnings"):
        warnings.extend(f"temporary install: {warning}" for warning in app_validation["warnings"])
    if app_validation.get("errors"):
        errors.extend(f"temporary install: {error}" for error in app_validation["errors"])
    return app_validation, warnings, errors


def validate_mpk(
    mpk_path: Path,
    fullname: str,
    repo: Path | None = None,
    install_check: bool = False,
    install_root: Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []

    if not mpk_path.is_file():
        errors.append(f"MPK file does not exist: {mpk_path}")
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "mpk_path": _display_path(mpk_path, repo),
            "fullname": fullname,
            "local_entries": [],
            "zip_entries": [],
            "install_check": None,
            "warnings": warnings,
            "errors": errors,
        }

    local_entries, local_warnings, local_errors = parse_local_headers(mpk_path, fullname)
    zip_entries, zip_warnings, zip_errors = validate_zip_directory(mpk_path, fullname)
    warnings.extend(local_warnings)
    warnings.extend(zip_warnings)
    errors.extend(local_errors)
    errors.extend(zip_errors)

    install_result = None
    if install_check:
        if install_root is None:
            install_root = mpk_path.parent / "install-check"
        install_result, install_warnings, install_errors = run_install_check(
            mpk_path,
            fullname,
            install_root,
            repo,
        )
        warnings.extend(install_warnings)
        errors.extend(install_errors)

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not errors,
        "mpk_path": _display_path(mpk_path, repo),
        "fullname": fullname,
        "local_entries": local_entries,
        "zip_entries": zip_entries,
        "install_check": {
            "requested": install_check,
            "root": _display_path(install_root, repo) if install_root else None,
            "app_validation_schema": APP_VALIDATION_SCHEMA if install_result else None,
            "result": install_result,
        },
        "warnings": warnings,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mpk_path", help="MPK path")
    parser.add_argument("--fullname", required=True, help="Expected app fullname")
    parser.add_argument("--repo", default="/home/leeqingshui/MicroPythonOS", help="MicroPythonOS repository root")
    parser.add_argument("--output", help="Write validation JSON to this path")
    parser.add_argument("--install-check", action="store_true", help="Extract to a temporary install dir and validate app layout")
    parser.add_argument("--install-root", help="Temporary install root")
    parser.add_argument("--quiet", action="store_true", help="Only print errors")
    args = parser.parse_args()

    repo = Path(args.repo).resolve() if args.repo else None
    install_root = Path(args.install_root).resolve() if args.install_root else None
    result = validate_mpk(Path(args.mpk_path).resolve(), args.fullname, repo, args.install_check, install_root)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if result["errors"]:
        for error in result["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
    if result["warnings"] and not args.quiet:
        for warning in result["warnings"]:
            print(f"WARNING: {warning}", file=sys.stderr)
    if not args.quiet:
        print(f"{'OK' if result['ok'] else 'FAILED'}: {result['mpk_path']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
