#!/usr/bin/env python3
"""Ensure a MicroPython-aware .pylintrc exists in a project."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


PYLINTRC = """[MASTER]
ignore-paths=^firmware/lib/.*\\.py$
ignore-patterns=test_
persistent=no

[MESSAGES CONTROL]
disable=
    import-error,
    no-member,
    no-name-in-module,
    c-extension-no-member,
    missing-module-docstring,
    missing-function-docstring,
    missing-class-docstring,
    broad-exception-caught,
    too-few-public-methods,
    duplicate-code,
    consider-using-f-string,
    import-outside-toplevel,
    invalid-name,
    unused-variable,
    ungrouped-imports

[TYPECHECK]
ignored-modules=
    machine,micropython,pyb,esp,esp32,espnow,rp2,mimxrt,zephyr,wipy,stm,
    neopixel,network,bluetooth,framebuf,uctypes,cryptolib,deflate,btree,
    vfs,openamp,lcd160cr,WM8960,
    uasyncio,uselect,utime,ujson,uos,ustruct,ure,uzlib,uhashlib,
    ubinascii,ucollections,urandom,uerrno,uheapq,ussl,usocket

[FORMAT]
max-line-length=120
"""


def ensure(project_dir: Path, force: bool) -> dict[str, Any]:
    target = project_dir / ".pylintrc"
    before = target.read_text(encoding="utf-8-sig") if target.exists() else None
    status = "unchanged"
    if not target.exists():
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(PYLINTRC)
        status = "created"
    elif force and before != PYLINTRC:
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(PYLINTRC)
        status = "updated"
    return {
        "check": "ensure_pylintrc",
        "path": ".pylintrc",
        "status": status,
        "written": status in {"created", "updated"},
        "ok": True,
        "errors": [],
        "warnings": [],
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Ensure MicroPython-aware .pylintrc")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    json_dump(ensure(Path(args.project_dir), args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
