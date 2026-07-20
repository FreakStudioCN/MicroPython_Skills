#!/usr/bin/env python3
"""Run CPython py_compile and MicroPython mpy-cross syntax checks for an MPOS App."""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


def collect_files(app_dir: Path) -> list[Path]:
    if not app_dir.exists():
        return []
    return sorted(path for path in app_dir.rglob("*.py") if "__pycache__" not in path.parts)


def cpython_compile(files: list[Path], temp_root: Path) -> tuple[list[dict], list[dict]]:
    ok: list[dict] = []
    errors: list[dict] = []
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pyc-", dir=temp_root) as tmp:
        tmp_dir = Path(tmp)
        for index, path in enumerate(files):
            cfile = tmp_dir / f"{index}.pyc"
            try:
                py_compile.compile(str(path), cfile=str(cfile), doraise=True)
                ok.append({"path": str(path)})
            except py_compile.PyCompileError as exc:
                errors.append({"path": str(path), "message": str(exc)})
    return ok, errors


def ensure_mpy_cross(mpy_cross: Path, build: bool, timeout: int) -> tuple[bool, list[dict], list[dict]]:
    warnings: list[dict] = []
    errors: list[dict] = []
    if mpy_cross.exists():
        return True, warnings, errors
    if not build:
        errors.append({"code": "MPY_CROSS_MISSING", "path": str(mpy_cross), "message": "mpy-cross binary not found"})
        return False, warnings, errors

    build_dir = mpy_cross.parents[1]
    if not build_dir.is_dir():
        errors.append({"code": "MPY_CROSS_BUILD_DIR_MISSING", "path": str(build_dir), "message": "mpy-cross source directory not found"})
        return False, warnings, errors

    jobs = str(os.cpu_count() or 1)
    try:
        proc = subprocess.run(
            ["make", f"-j{jobs}", "-C", str(build_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        errors.append({"code": "MPY_CROSS_BUILD_TIMEOUT", "path": str(build_dir), "message": f"mpy-cross build timed out after {timeout}s", "stdout": (exc.stdout or "")[-4000:], "stderr": (exc.stderr or "")[-4000:]})
        return False, warnings, errors

    build_item = {
        "code": "MPY_CROSS_BUILT",
        "path": str(mpy_cross),
        "command": f"make -j{jobs} -C {build_dir}",
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    if proc.returncode != 0:
        errors.append({"code": "MPY_CROSS_BUILD_FAILED", **build_item})
        return False, warnings, errors
    if not mpy_cross.exists():
        errors.append({"code": "MPY_CROSS_STILL_MISSING", **build_item, "message": "mpy-cross build completed but binary is missing"})
        return False, warnings, errors
    warnings.append(build_item)
    return True, warnings, errors


def mpy_cross_compile(files: list[Path], mpy_cross: Path, build: bool, timeout: int, temp_root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    ok: list[dict] = []
    errors: list[dict] = []
    warnings: list[dict] = []
    available, build_warnings, build_errors = ensure_mpy_cross(mpy_cross, build, timeout)
    warnings.extend(build_warnings)
    errors.extend(build_errors)
    if not available:
        return ok, errors, warnings
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mpy-", dir=temp_root) as tmp:
        tmp_dir = Path(tmp)
        for index, path in enumerate(files):
            out = tmp_dir / f"{index}.mpy"
            proc = subprocess.run(
                [str(mpy_cross), "-o", str(out), str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            item = {
                "path": str(path),
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
            if proc.returncode == 0:
                ok.append(item)
            else:
                errors.append(item)
    return ok, errors, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check MPOS App syntax with CPython and mpy-cross")
    parser.add_argument("--repo", default=".", help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", help="App fullname under internal_filesystem/apps")
    parser.add_argument("--app-dir", help="Explicit app directory")
    parser.add_argument("--mpy-cross", help="Explicit mpy-cross path")
    parser.add_argument("--no-build-mpy-cross", action="store_true", help="Fail instead of attempting to build missing mpy-cross")
    parser.add_argument("--mpy-cross-build-timeout", type=int, default=300, help="Seconds allowed for automatic mpy-cross build")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if args.app_dir:
        app_dir = Path(args.app_dir)
        if not app_dir.is_absolute():
            app_dir = repo / app_dir
    elif args.app_fullname:
        app_dir = repo / "internal_filesystem" / "apps" / args.app_fullname
    else:
        print("--app-fullname or --app-dir is required", file=sys.stderr)
        return 2

    mpy_cross = Path(args.mpy_cross) if args.mpy_cross else repo / "lvgl_micropython" / "lib" / "micropython" / "mpy-cross" / "build" / "mpy-cross"
    temp_root = repo / "tmp" / "mpos-gen-app" / "syntax-temp"
    files = collect_files(app_dir)
    cpy_ok, cpy_errors = cpython_compile(files, temp_root)
    mpy_ok, mpy_errors, warnings = mpy_cross_compile(files, mpy_cross, not args.no_build_mpy_cross, args.mpy_cross_build_timeout, temp_root)
    result = {
        "ok": not cpy_errors and not mpy_errors,
        "app_dir": str(app_dir),
        "files_checked": [str(path) for path in files],
        "cpython_syntax": {"ok": not cpy_errors, "passed": cpy_ok, "errors": cpy_errors},
        "mpy_syntax": {"ok": not mpy_errors, "passed": mpy_ok, "errors": mpy_errors, "warnings": warnings},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
