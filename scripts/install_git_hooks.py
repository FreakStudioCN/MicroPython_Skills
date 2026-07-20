#!/usr/bin/env python3
"""Install repository-local git hooks for the skills repository."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def repo_root(start: Path) -> Path:
    proc = run(["git", "rev-parse", "--show-toplevel"], start)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "not inside a git repository")
    return Path(proc.stdout.strip()).resolve()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Install MicroPython_Skills git hooks")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--english-repo", help="Path to MicroPython_Skills_EN")
    parser.add_argument(
        "--push",
        dest="push",
        action="store_true",
        default=True,
        help="Configure hook to push the English sync branch (default)",
    )
    parser.add_argument(
        "--no-push",
        dest="push",
        action="store_false",
        help="Commit the English sync locally but do not push it",
    )
    parser.add_argument("--create-pr", action="store_true", help="Configure hook to create a PR with gh after push")
    parser.add_argument("--unset", action="store_true", help="Remove core.hooksPath from this repository")
    args = parser.parse_args(argv)
    if args.create_pr and not args.push:
        parser.error("--create-pr requires push to be enabled")

    root = repo_root(Path(args.repo).resolve())
    if args.unset:
        proc = run(["git", "config", "--unset", "core.hooksPath"], root)
        if proc.returncode not in (0, 5):
            raise RuntimeError(proc.stderr.strip())
        print("Removed core.hooksPath")
        return 0

    hooks_dir = root / ".githooks"
    hook = hooks_dir / "post-commit"
    if not hook.exists():
        raise RuntimeError(f"missing hook file: {hook}")

    try:
        mode = hook.stat().st_mode
        hook.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        # Windows may ignore POSIX executable bits; Git for Windows still runs
        # hooks through its shell when core.hooksPath points at the directory.
        pass

    proc = run(["git", "config", "core.hooksPath", ".githooks"], root)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())

    if args.english_repo:
        en_repo = Path(args.english_repo).expanduser().resolve()
        proc = run(["git", "config", "skills.englishRepo", str(en_repo)], root)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())
    proc = run(["git", "config", "skills.englishPush", "true" if args.push else "false"], root)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    if args.create_pr:
        proc = run(["git", "config", "skills.englishCreatePr", "true"], root)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())
    else:
        proc = run(["git", "config", "skills.englishCreatePr", "false"], root)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())

    print(f"Installed hooks for {root}")
    print("post-commit will run scripts/sync_english_repo.py after each source commit.")
    print("The English sync will commit changes and push them to origin." if args.push else "The English sync will commit locally but will not push.")
    log_proc = run(["git", "rev-parse", "--git-path", "english-sync.log"], root)
    if log_proc.returncode == 0:
        log_path = Path(log_proc.stdout.strip())
        if not log_path.is_absolute():
            log_path = root / log_path
        print(f"Hook log: {log_path.resolve()}")
    print("Set SKILLS_SKIP_EN_SYNC=1 to skip one commit, or run with no API key to make it a no-op.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
