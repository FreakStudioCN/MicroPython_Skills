#!/usr/bin/env python3
"""Compile downloaded firmware/lib Python driver sources."""

from __future__ import annotations

import argparse
import py_compile
import sys
import tempfile
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


sys.dont_write_bytecode = True


def check(project_dir: Path) -> dict[str, Any]:
    lib_dir = project_dir / "firmware" / "lib"
    files = sorted(lib_dir.rglob("*.py")) if lib_dir.exists() else []
    entries = []
    errors = []
    with tempfile.TemporaryDirectory(prefix="upy_driver_compile_") as temp_dir:
        temp_root = Path(temp_dir)
        for index, path in enumerate(files):
            rel = path.relative_to(project_dir).as_posix()
            try:
                cfile = temp_root / f"{index}.pyc"
                py_compile.compile(str(path), cfile=str(cfile), doraise=True)
                entries.append({"path": rel, "compile": {"ok": True, "error": None}})
            except py_compile.PyCompileError as exc:
                error = {
                    "code": "DRIVER_SOURCE_COMPILE_FAILED",
                    "path": rel,
                    "message": str(exc),
                }
                entries.append({"path": rel, "compile": {"ok": False, "error": str(exc)}})
                errors.append(error)
            except OSError as exc:
                error = {
                    "code": "DRIVER_SOURCE_COMPILE_OS_ERROR",
                    "path": rel,
                    "message": str(exc),
                }
                entries.append({"path": rel, "compile": {"ok": False, "error": str(exc)}})
                errors.append(error)
    return {
        "check": "driver_source_compile",
        "files_checked": len(files),
        "files": entries,
        "errors": errors,
        "warnings": [],
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Compile firmware/lib driver sources")
    parser.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    result = check(Path(args.project_dir))
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
