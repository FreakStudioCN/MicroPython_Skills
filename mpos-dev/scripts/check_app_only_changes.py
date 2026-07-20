#!/usr/bin/env python3
"""Report git changes outside the target MPOS App and mpos tmp artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


FULLNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def is_repo_root(path: Path) -> bool:
    return (path / "internal_filesystem" / "apps").is_dir() and (path / "scripts").is_dir()


def default_repo() -> Path | None:
    env_repo = os.environ.get("MPOS_REPO")
    if env_repo:
        return Path(env_repo)
    cwd = Path.cwd()
    if is_repo_root(cwd):
        return cwd
    return None


def resolve_repo(value: str | None) -> Path:
    repo = Path(value).expanduser() if value else default_repo()
    if repo is None:
        raise SystemExit("ERROR: --repo is required outside a MicroPythonOS repo")
    repo = repo.resolve()
    if not is_repo_root(repo):
        raise SystemExit(f"ERROR: not a MicroPythonOS repo root: {repo}")
    return repo


def safe_fullname(value: str) -> str:
    if not FULLNAME_RE.fullmatch(value or "") or "/" in value or "\\" in value:
        raise ValueError("app fullname must contain only letters, digits, dots, underscores, and hyphens")
    return value


def git_status(repo: Path) -> list[dict[str, Any]]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git status failed")
    changes: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        status = line[:2]
        path_text = line[3:]
        if " -> " in path_text:
            old, new = path_text.split(" -> ", 1)
            paths = [old, new]
        else:
            paths = [path_text]
        changes.append({"status": status, "path": path_text, "paths": paths})
    return changes


def is_allowed_path(path_text: str, fullname: str) -> bool:
    normalized = path_text.strip().lstrip("./")
    app_prefix = f"internal_filesystem/apps/{fullname}/"
    tmp_prefix = "tmp/mpos-"
    allowed_exact = {
        f"internal_filesystem/apps/{fullname}",
    }
    return (
        normalized in allowed_exact
        or normalized.startswith(app_prefix)
        or normalized.startswith(tmp_prefix)
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", required=True, help="Allowed target App fullname")
    parser.add_argument("--allow-clean", action="store_true", help="Succeed when there are no git changes")
    args = parser.parse_args(argv)

    repo = resolve_repo(args.repo)
    fullname = safe_fullname(args.app_fullname)
    warnings: list[str] = []
    errors: list[str] = []
    try:
        changes = git_status(repo)
    except Exception as exc:  # noqa: BLE001 - CLI should report structured tooling failure.
        result = {
            "schema_version": "mpos-app-only-changes-v1",
            "ok": False,
            "repo": str(repo),
            "app_fullname": fullname,
            "allowed_prefixes": [f"internal_filesystem/apps/{fullname}/", "tmp/mpos-"],
            "allowed_changes": [],
            "outside_changes": [],
            "warnings": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    allowed_changes = []
    outside_changes = []
    for change in changes:
        if all(is_allowed_path(path_text, fullname) for path_text in change["paths"]):
            allowed_changes.append(change)
        else:
            outside_changes.append(change)

    if outside_changes:
        errors.append(
            "Detected git changes outside the target App directory and tmp/mpos-* artifacts; "
            "mpos skills must not modify OS/build/framework/existing App files."
        )
    elif not changes and not args.allow_clean:
        warnings.append("No git changes detected")

    result = {
        "schema_version": "mpos-app-only-changes-v1",
        "ok": not outside_changes,
        "repo": str(repo),
        "app_fullname": fullname,
        "allowed_prefixes": [f"internal_filesystem/apps/{fullname}/", "tmp/mpos-"],
        "allowed_changes": allowed_changes,
        "outside_changes": outside_changes,
        "warnings": warnings,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
