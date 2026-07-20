#!/usr/bin/env python3
"""Prepare the local MPOS desktop simulator without editing OS sources.

This helper creates temporary build shims for local dependency gaps and then
delegates to the repository's existing scripts/build_mpos.sh unix command.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def resolve_repo_arg(value: str | None) -> Path:
    repo = Path(value).expanduser() if value else default_repo()
    if repo is None:
        raise SystemExit(
            "ERROR: --repo is required when the current directory is not a MicroPythonOS repo "
            "and MPOS_REPO is unset"
        )
    repo = repo.resolve()
    if not is_repo_root(repo):
        raise SystemExit(f"ERROR: not a MicroPythonOS repo root: {repo}")
    return repo


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        **kwargs,
    )


def print_file_name(name: str) -> Path | None:
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cc:
        return None
    proc = run([cc, "-print-file-name=" + name])
    value = proc.stdout.strip()
    if not value or value == name:
        return None
    path = Path(value)
    return path if path.exists() else None


def find_local_libffi() -> Path | None:
    prefixes: list[Path] = []
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        prefixes.append(Path(conda_prefix))
    home = Path.home()
    prefixes.extend(
        [
            home / "miniconda3" / "envs" / "micropython",
            home / "miniconda3",
            home / ".local",
            Path("/usr/local"),
        ]
    )
    for prefix in prefixes:
        if (prefix / "include" / "ffi.h").exists() and (prefix / "lib" / "libffi.a").exists():
            return prefix
    return None


def pkg_config_has_static_libffi(real_pkg_config: str | None) -> bool:
    if not real_pkg_config:
        return False
    exists = run([real_pkg_config, "--exists", "libffi"])
    if exists.returncode != 0:
        return False
    return print_file_name("libffi.a") is not None


def write_fake_pkg_config(path: Path, libffi_prefix: Path, real_pkg_config: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    delegate = real_pkg_config or ""
    path.write_text(
        """#!/bin/sh
if [ "$1" = "--exists" ] && [ "$2" = "libffi" ]; then
    exit 0
fi
if [ "$1" = "--cflags" ] && [ "$2" = "libffi" ]; then
    printf '%s\\n' "-I__LIBFFI_PREFIX__/include"
    exit 0
fi
if [ "$1" = "--libs" ] && [ "$2" = "libffi" ]; then
    printf '%s\\n' "__LIBFFI_PREFIX__/lib/libffi.a"
    exit 0
fi
if [ "$1" = "--modversion" ] && [ "$2" = "libffi" ]; then
    printf '%s\\n' "local-static"
    exit 0
fi
if [ -n "__REAL_PKG_CONFIG__" ]; then
    exec "__REAL_PKG_CONFIG__" "$@"
fi
exit 1
""".replace("__LIBFFI_PREFIX__", str(libffi_prefix)).replace("__REAL_PKG_CONFIG__", delegate),
        encoding="utf-8",
    )
    path.chmod(0o755)


def ensure_empty_static_library(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = run(["ar", "rcs", str(path)])
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.strip() or "failed to create static archive")


def check_webrepl_import(repo: Path, timeout: int) -> dict[str, Any]:
    binary = repo / "lvgl_micropython" / "build" / "lvgl_micropy_unix"
    check: dict[str, Any] = {
        "name": "desktop_import_webrepl",
        "ok": False,
        "binary": str(binary),
        "errors": [],
        "warnings": [],
    }
    if not binary.exists():
        check["status"] = "missing_binary"
        check["errors"].append("lvgl_micropy_unix does not exist")
        return check
    try:
        proc = run(
            [str(binary), "-c", "import _webrepl; print('webrepl-native-ok')"],
            cwd=str(repo / "internal_filesystem"),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        check["status"] = "timeout"
        check["errors"].append(f"import _webrepl timed out after {timeout}s")
        return check
    check["returncode"] = proc.returncode
    check["stdout_tail"] = proc.stdout[-2000:]
    if proc.returncode == 0 and "webrepl-native-ok" in proc.stdout:
        check.update(ok=True, status="passed")
    else:
        check["status"] = "failed"
        check["errors"].append("desktop binary could not import _webrepl")
    return check


def prepare_env(repo: Path, temp_dir: Path) -> tuple[dict[str, str], dict[str, Any]]:
    env = os.environ.copy()
    info: dict[str, Any] = {
        "uses_fake_pkg_config": False,
        "uses_empty_libv4l2": False,
        "warnings": [],
    }

    real_pkg_config = shutil.which("pkg-config")
    if not pkg_config_has_static_libffi(real_pkg_config):
        libffi_prefix = find_local_libffi()
        if libffi_prefix is None:
            info["warnings"].append("static libffi not found in system or known user prefixes")
        else:
            fake_pkg_config = temp_dir / "bin" / "pkg-config"
            write_fake_pkg_config(fake_pkg_config, libffi_prefix, real_pkg_config)
            env["PATH"] = str(fake_pkg_config.parent) + os.pathsep + env.get("PATH", "")
            info.update(
                {
                    "uses_fake_pkg_config": True,
                    "libffi_prefix": str(libffi_prefix),
                    "fake_pkg_config": str(fake_pkg_config),
                }
            )

    if print_file_name("libv4l2.a") is None:
        stub = temp_dir / "lib" / "libv4l2.a"
        ensure_empty_static_library(stub)
        env["LIBRARY_PATH"] = str(stub.parent) + os.pathsep + env.get("LIBRARY_PATH", "")
        info.update(
            {
                "uses_empty_libv4l2": True,
                "empty_libv4l2": str(stub),
            }
        )

    info["path_prefix"] = env.get("PATH", "").split(os.pathsep)[:3]
    info["library_path"] = env.get("LIBRARY_PATH")
    return env, info


def build_unix(repo: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    script = repo / "scripts" / "build_mpos.sh"
    check: dict[str, Any] = {
        "name": "build_mpos_unix",
        "ok": False,
        "command": f"{script} unix",
        "errors": [],
        "warnings": [],
    }
    if not script.exists():
        check["status"] = "missing_tool"
        check["errors"].append(f"{script} does not exist")
        return check
    try:
        proc = run([str(script), "unix"], cwd=str(repo), env=env, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        check["status"] = "timeout"
        check["errors"].append(f"build_mpos.sh unix timed out after {timeout}s")
        check["stdout_tail"] = (exc.stdout or "")[-4000:]
        return check
    check["returncode"] = proc.returncode
    check["stdout_tail"] = proc.stdout[-6000:]
    if proc.returncode == 0:
        check.update(ok=True, status="passed")
    else:
        check["status"] = "failed"
        check["errors"].append(f"build_mpos.sh unix exited with {proc.returncode}")
    return check


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Prepare MPOS desktop simulator tooling without editing OS sources")
    parser.add_argument("--repo", help="MicroPythonOS repository root; defaults to MPOS_REPO or current repo root")
    parser.add_argument("--build", action="store_true", help="Run scripts/build_mpos.sh unix with temporary dependency shims")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output", help="Optional JSON result path")
    args = parser.parse_args(argv)

    repo = resolve_repo_arg(args.repo)
    result: dict[str, Any] = {
        "schema_version": "mpos-test-app-desktop-tooling-v1",
        "phase": "prepare-desktop-tooling",
        "created_at_utc": utc_now(),
        "repo": str(repo),
        "checks": [],
        "environment": {},
    }

    pre = check_webrepl_import(repo, min(args.timeout, 30))
    result["checks"].append(pre)
    if pre["ok"] and not args.build:
        result["result"] = "success"
    elif not args.build:
        result["result"] = "needs_build"
        result["next_command"] = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--repo",
            str(repo),
            "--build",
        ]
    else:
        temp_root = repo / "tmp" / "mpos-test-app" / "desktop-tooling"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="shim-", dir=temp_root) as temp:
            env, env_info = prepare_env(repo, Path(temp))
            result["environment"] = env_info
            build = build_unix(repo, env, args.timeout)
            result["checks"].append(build)
            post = check_webrepl_import(repo, min(args.timeout, 30))
            result["checks"].append(post)
            result["result"] = "success" if build["ok"] and post["ok"] else "failed"

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["result"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
