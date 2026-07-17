#!/usr/bin/env python3
"""Build and optionally cache MicroPythonOS dependency search queries."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCES = [
    "mpos_builtin",
    "micropython-lib",
    "upypi",
    "awesome-micropython",
    "github",
    "gitlab",
    "codeberg",
    "single_file_driver",
]

ASYNC_TERMS = [
    "async",
    "asyncio",
    "uasyncio",
    "aio",
    "await",
    "create_task",
    "sleep_ms",
    "event loop",
    "task",
    "coroutine",
    "non-blocking",
    "nonblocking",
    "stream",
    "queue",
    "lock",
    "event",
    "callback",
    "reconnect",
    "timeout",
]


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def utc_now() -> str:
    fixed = os.environ.get("MPOS_PREPARE_DEPS_UTC_NOW", "").strip()
    if fixed:
        return fixed
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def require_safe_fullname(fullname: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", fullname or ""):
        fail("fullname must contain only letters, digits, dots, underscores, and hyphens")
    if "/" in fullname or "\\" in fullname or ".." in fullname.split("."):
        fail("fullname must not contain path separators or '..' components")


def safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return text or "dependency"


def safe_relative_path(path: str) -> Path:
    value = Path(path)
    if value.is_absolute() or ".." in value.parts:
        fail(f"path must be relative and must not contain '..': {path}")
    return value


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = " ".join(item.split())
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def dependency_queries(name: str, protocols: list[str]) -> dict[str, list[str]]:
    base = [
        f"{name} micropython",
        f"{name} micropython driver",
    ]
    async_queries = [
        f"{name} micropython async",
        f"{name} micropython asyncio",
        f"{name} micropython uasyncio",
        f"{name} micropython aio",
    ]
    for protocol in protocols:
        async_queries.extend(
            [
                f"{protocol} micropython non-blocking",
                f"{protocol} micropython await create_task sleep_ms",
                f"{protocol} micropython websocket mqtt ble aioble espnow async",
            ]
        )
    return {
        "base": unique(base),
        "async": unique(async_queries),
        "all": unique(base + async_queries),
    }


def build_plan(fullname: str, dependencies: list[str], protocols: list[str], cache_root: str) -> dict[str, Any]:
    require_safe_fullname(fullname)
    cache_root_path = safe_relative_path(cache_root)
    cache_path = cache_root_path / fullname
    items = []
    for raw_name in dependencies:
        name = raw_name.strip()
        if not name:
            continue
        queries = dependency_queries(name, protocols)
        items.append(
            {
                "name": name,
                "cache_dir": str(cache_path / safe_name(name)),
                "base_queries": queries["base"],
                "async_queries": queries["async"],
                "queries": queries["all"],
            }
        )
    if not items:
        fail("at least one --dependency is required")
    return {
        "schema_version": "mpos-deps-search-plan-v1",
        "created_at_utc": utc_now(),
        "app": {"fullname": fullname},
        "cache": {
            "enabled": True,
            "path": str(cache_path),
            "search_plan_path": str(cache_path / "search_plan.json"),
        },
        "sources": SOURCES,
        "required_query_groups": {
            "base": ["<name> micropython", "<name> micropython driver"],
            "async": [
                "<name> micropython async",
                "<name> micropython asyncio",
                "<name> micropython uasyncio",
                "<name> micropython aio",
                "<protocol> micropython non-blocking",
                "<protocol> micropython await create_task sleep_ms",
            ],
        },
        "async_terms": ASYNC_TERMS,
        "dependencies": items,
    }


def write_cache(repo: Path, plan: dict[str, Any]) -> None:
    cache_path = repo / plan["cache"]["path"]
    cache_path.mkdir(parents=True, exist_ok=True)
    (cache_path / "search_plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for dep in plan["dependencies"]:
        dep_dir = repo / dep["cache_dir"]
        dep_dir.mkdir(parents=True, exist_ok=True)
        (dep_dir / "search_queries.json").write_text(
            json.dumps(
                {
                    "schema_version": "mpos-deps-search-queries-v1",
                    "created_at_utc": plan["created_at_utc"],
                    "name": dep["name"],
                    "base_queries": dep["base_queries"],
                    "async_queries": dep["async_queries"],
                    "queries": dep["queries"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MPOS dependency search query plan")
    parser.add_argument("--repo", default=".", help="MicroPythonOS repo root used when writing cache files")
    parser.add_argument("--fullname", required=True, help="MPOS app fullname")
    parser.add_argument("--dependency", action="append", default=[], help="Dependency name; repeat for multiple deps")
    parser.add_argument("--protocol", action="append", default=[], help="Protocol or feature keyword; repeat as needed")
    parser.add_argument("--cache-root", default="tmp/mpos-deps-cache", help="Repo-relative cache root")
    parser.add_argument("--write-cache", action="store_true", help="Create cache folders and write search query JSON files")
    args = parser.parse_args()

    plan = build_plan(args.fullname, args.dependency, args.protocol, args.cache_root)
    if args.write_cache:
        write_cache(Path(args.repo), plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

