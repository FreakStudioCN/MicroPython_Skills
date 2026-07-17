#!/usr/bin/env python3
"""Sync the Chinese skills repository to the English mirror repository.

This wrapper intentionally keeps translation logic in translate_to_english.py.
It adds git-flow behavior: export the committed source tree, translate/mirror it
to MicroPython_Skills_EN, optionally create an EN repo commit/branch, and
optionally push or open a PR.
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    text: bool = True,
    stdout: int | None = subprocess.PIPE,
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=text,
        stdout=stdout,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        out = proc.stdout if isinstance(proc.stdout, str) else ""
        err = proc.stderr if isinstance(proc.stderr, str) else ""
        raise RuntimeError(
            "command failed: {cmd}\nreturncode={rc}\nstdout={out}\nstderr={err}".format(
                cmd=" ".join(command),
                rc=proc.returncode,
                out=out[-2000:],
                err=err[-2000:],
            )
        )
    return proc


def git(repo: Path, *args: str, check: bool = True, stdout: int | None = subprocess.PIPE) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=repo, check=check, stdout=stdout)


def repo_root(start: Path) -> Path:
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=start)
    return Path(proc.stdout.strip()).resolve()


def default_english_repo(src_repo: Path) -> Path:
    env = os.environ.get("MICROPYTHON_SKILLS_EN_REPO", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    configured = git(src_repo, "config", "--get", "skills.englishRepo", check=False)
    if configured.returncode == 0 and configured.stdout.strip():
        return Path(configured.stdout.strip()).expanduser().resolve()
    return src_repo.parent / "MicroPython_Skills_EN"


def porcelain(repo: Path) -> str:
    return git(repo, "status", "--porcelain").stdout


def git_config_bool(repo: Path, name: str) -> bool:
    proc = git(repo, "config", "--bool", "--get", name, check=False)
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def require_clean(repo: Path, label: str) -> None:
    status = porcelain(repo)
    if status.strip():
        raise RuntimeError(f"{label} repository is dirty:\n{status}")


def export_head(src_repo: Path, ref: str, out_dir: Path) -> None:
    proc = git(src_repo, "archive", "--format=tar", ref, text=False)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as archive:
        archive.extractall(out_dir)


def current_commit(src_repo: Path) -> tuple[str, str]:
    full = git(src_repo, "rev-parse", "HEAD").stdout.strip()
    short = git(src_repo, "rev-parse", "--short", "HEAD").stdout.strip()
    return full, short


def resolve_python() -> str:
    return sys.executable or shutil.which("python3") or shutil.which("python") or "python"


def run_translation(args: argparse.Namespace, src_tree: Path, en_repo: Path) -> None:
    script = Path(__file__).resolve().parent / "translate_to_english.py"
    command = [
        resolve_python(),
        str(script),
        "--src",
        str(src_tree),
        "--dst",
        str(en_repo),
        "--backend",
        args.backend,
        "--rpm",
        str(args.rpm),
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    if args.api_key:
        command.extend(["--api-key", args.api_key])
    if args.no_resume:
        command.append("--no-resume")
    if args.dry_run:
        command.append("--dry-run")
    run(command, cwd=src_tree, stdout=None)


def ensure_branch(en_repo: Path, branch: str) -> None:
    git(en_repo, "checkout", "-B", branch, stdout=None)


def commit_english_repo(en_repo: Path, src_full: str, src_short: str, branch_prefix: str) -> bool:
    if not porcelain(en_repo).strip():
        print("English repo has no changes to commit.")
        return False

    branch = f"{branch_prefix.rstrip('/')}/{src_short}"
    ensure_branch(en_repo, branch)
    git(en_repo, "add", "-A", stdout=None)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = f"[auto-sync] {stamp} - mirror source {src_short}"
    body = f"Source repository commit: {src_full}"
    git(en_repo, "commit", "-m", message, "-m", body, stdout=None)
    print(f"Committed English sync on branch {branch}.")
    return True


def push_branch(en_repo: Path) -> None:
    branch = git(en_repo, "branch", "--show-current").stdout.strip()
    if not branch:
        raise RuntimeError("cannot push: English repo is not on a branch")
    git(en_repo, "push", "-u", "origin", branch, stdout=None)


def create_pr(en_repo: Path) -> None:
    if not shutil.which("gh"):
        print("gh CLI not found; skipping PR creation.")
        return
    branch = git(en_repo, "branch", "--show-current").stdout.strip()
    run(
        [
            "gh",
            "pr",
            "create",
            "--fill",
            "--head",
            branch,
        ],
        cwd=en_repo,
        check=False,
        stdout=None,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Translate and sync MicroPython_Skills to MicroPython_Skills_EN")
    parser.add_argument("--src-repo", default=".", help="Chinese source repository")
    parser.add_argument("--en-repo", help="English mirror repository; defaults to sibling MicroPython_Skills_EN")
    parser.add_argument("--source-mode", choices=["head", "worktree"], default="head")
    parser.add_argument("--ref", default="HEAD", help="Git ref to export when --source-mode=head")
    parser.add_argument("--backend", default=os.environ.get("SKILLS_TRANSLATE_BACKEND", "deepseek"))
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--rpm", type=int, default=40)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true", help="Commit changes in the English repo")
    parser.add_argument("--branch-prefix", default=os.environ.get("SKILLS_EN_BRANCH_PREFIX", "auto-sync"))
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--create-pr", action="store_true")
    parser.add_argument("--allow-dirty-en", action="store_true")
    parser.add_argument("--from-hook", action="store_true", help="Never fail the source commit hook")
    args = parser.parse_args(argv)

    try:
        if os.environ.get("SKILLS_SKIP_EN_SYNC") == "1":
            print("SKILLS_SKIP_EN_SYNC=1; skipping English sync.")
            return 0

        if not args.dry_run and not args.api_key:
            args.api_key = (
                os.environ.get("SKILLS_TRANSLATE_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("DEEPSEEK_API_KEY")
            )
        if not args.dry_run and not args.api_key:
            print(
                "No translation API key found; skipping English sync. "
                "Set SKILLS_TRANSLATE_API_KEY, ANTHROPIC_API_KEY, or DEEPSEEK_API_KEY."
            )
            return 0

        src_repo = repo_root(Path(args.src_repo).resolve())
        en_repo = Path(args.en_repo).expanduser().resolve() if args.en_repo else default_english_repo(src_repo)
        if not args.push and git_config_bool(src_repo, "skills.englishPush"):
            args.push = True
        if not args.create_pr and git_config_bool(src_repo, "skills.englishCreatePr"):
            args.create_pr = True

        if not en_repo.is_dir():
            raise RuntimeError(f"English repository not found: {en_repo}")
        if not (en_repo / ".git").exists():
            raise RuntimeError(f"English path is not a git repository: {en_repo}")
        if not args.allow_dirty_en:
            require_clean(en_repo, "English")

        src_full, src_short = current_commit(src_repo)

        if args.source_mode == "worktree":
            src_tree = src_repo
            run_translation(args, src_tree, en_repo)
        else:
            with tempfile.TemporaryDirectory(prefix="skills-src-head-") as temp:
                src_tree = Path(temp)
                export_head(src_repo, args.ref, src_tree)
                run_translation(args, src_tree, en_repo)

        committed = False
        if args.commit and not args.dry_run:
            committed = commit_english_repo(en_repo, src_full, src_short, args.branch_prefix)
        if args.push and committed:
            push_branch(en_repo)
        if args.create_pr and committed:
            create_pr(en_repo)

        return 0
    except Exception as exc:  # noqa: BLE001 - hook mode should report any failure.
        print(f"English sync failed: {exc}", file=sys.stderr)
        return 0 if args.from_hook else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
