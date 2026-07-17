#!/usr/bin/env python3
"""Run CPython py_compile and MicroPython mpy-cross syntax checks for an MPOS App."""

from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


def collect_files(app_dir: Path) -> list[Path]:
    if not app_dir.exists():
        return []
    return sorted(path for path in app_dir.rglob("*.py") if "__pycache__" not in path.parts)


def cpython_compile(files: list[Path]) -> tuple[list[dict], list[dict]]:
    ok: list[dict] = []
    errors: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="mpos-gen-pyc-") as tmp:
        tmp_dir = Path(tmp)
        for index, path in enumerate(files):
            cfile = tmp_dir / f"{index}.pyc"
            try:
                py_compile.compile(str(path), cfile=str(cfile), doraise=True)
                ok.append({"path": str(path)})
            except py_compile.PyCompileError as exc:
                errors.append({"path": str(path), "message": str(exc)})
    return ok, errors


def mpy_cross_compile(files: list[Path], mpy_cross: Path) -> tuple[list[dict], list[dict], list[dict]]:
    ok: list[dict] = []
    errors: list[dict] = []
    warnings: list[dict] = []
    if not mpy_cross.exists():
        warnings.append({"code": "MPY_CROSS_MISSING", "path": str(mpy_cross), "message": "mpy-cross binary not found"})
        return ok, errors, warnings
    with tempfile.TemporaryDirectory(prefix="mpos-gen-mpy-") as tmp:
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
    files = collect_files(app_dir)
    cpy_ok, cpy_errors = cpython_compile(files)
    mpy_ok, mpy_errors, warnings = mpy_cross_compile(files, mpy_cross)
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
