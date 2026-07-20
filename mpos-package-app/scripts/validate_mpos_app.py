#!/usr/bin/env python3
"""Validate one MicroPythonOS App directory before MPK packaging."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mpos-app-validation-v1"
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")


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


def _display_path(path: Path, repo: Path | None = None) -> str:
    try:
        if repo is not None:
            return str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        pass
    return str(path)


def _load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001 - report parse/read errors in validation result.
        errors.append(f"Invalid JSON in {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"Manifest {path} must contain a JSON object")
        return {}
    return data


def _canonical_version(version: str) -> str | None:
    if not VERSION_RE.match(version):
        return None
    try:
        parts = [int(part) for part in version.split(".")]
    except ValueError:
        return None
    return ".".join(str(part) for part in parts)


def _find_manifest(app_dir: Path, warnings: list[str], errors: list[str]) -> tuple[Path | None, str]:
    root_manifest = app_dir / "MANIFEST.JSON"
    old_manifest = app_dir / "META-INF" / "MANIFEST.JSON"
    if root_manifest.is_file():
        if old_manifest.is_file():
            warnings.append("Both MANIFEST.JSON and META-INF/MANIFEST.JSON exist; using root MANIFEST.JSON")
        return root_manifest, "flat"
    if old_manifest.is_file():
        warnings.append("Deprecated manifest path META-INF/MANIFEST.JSON; prefer root MANIFEST.JSON")
        return old_manifest, "legacy"
    errors.append(f"Missing MANIFEST.JSON in {app_dir}")
    return None, "missing"


def _find_icon(app_dir: Path, warnings: list[str], errors: list[str]) -> tuple[Path | None, str]:
    root_icon = app_dir / "icon_64x64.png"
    old_icon = app_dir / "res" / "mipmap-mdpi" / "icon_64x64.png"
    if root_icon.is_file():
        if old_icon.is_file():
            warnings.append("Both icon_64x64.png and res/mipmap-mdpi/icon_64x64.png exist; using root icon")
        return root_icon, "flat"
    if old_icon.is_file():
        warnings.append("Deprecated icon path res/mipmap-mdpi/icon_64x64.png; prefer root icon_64x64.png")
        return old_icon, "legacy"
    errors.append(f"Missing icon_64x64.png in {app_dir}")
    return None, "missing"


def _validate_version(version: Any, errors: list[str]) -> str | None:
    if not isinstance(version, str) or not version:
        errors.append("Manifest missing non-empty version")
        return None
    canonical = _canonical_version(version)
    if canonical is None:
        errors.append(f"Invalid version {version!r}; expected integer dotted version")
        return None
    if canonical != version:
        errors.append(f"Version {version!r} is not canonical; expected {canonical!r}")
        return None
    return version


def _validate_component(
    component: Any,
    label: str,
    app_dir: Path,
    errors: list[str],
) -> None:
    if not isinstance(component, dict):
        errors.append(f"{label} must be an object")
        return

    entrypoint = component.get("entrypoint")
    classname = component.get("classname")

    if not isinstance(entrypoint, str) or not entrypoint:
        errors.append(f"{label}.entrypoint must be a non-empty string")
        return
    if not entrypoint.endswith(".py"):
        errors.append(f"{label}.entrypoint must end with .py: {entrypoint}")
        return
    if entrypoint.startswith("/") or ".." in Path(entrypoint).parts:
        errors.append(f"{label}.entrypoint must be a safe App-relative path: {entrypoint}")
        return

    entrypoint_path = app_dir / entrypoint
    if not entrypoint_path.is_file():
        errors.append(f"{label}.entrypoint does not exist: {entrypoint}")
        return

    if not isinstance(classname, str) or not classname:
        errors.append(f"{label}.classname must be a non-empty string")
        return

    try:
        source = entrypoint_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = entrypoint_path.read_text()
    except Exception as exc:  # noqa: BLE001 - report read failures in validation result.
        errors.append(f"Failed to read {entrypoint}: {exc}")
        return

    if classname not in source:
        errors.append(f"{label}.classname {classname!r} not found in {entrypoint}")


def _find_packaging_noise(app_dir: Path) -> list[str]:
    warnings: list[str] = []
    for path in app_dir.rglob("*"):
        rel_parts = path.relative_to(app_dir).parts
        name = path.name
        if ".git" in rel_parts:
            warnings.append(f"Packaging will exclude .git path: {path.relative_to(app_dir)}")
        elif "__pycache__" in rel_parts:
            warnings.append(f"Packaging will exclude __pycache__ path: {path.relative_to(app_dir)}")
        elif name.endswith(".pyc"):
            warnings.append(f"Packaging will exclude .pyc file: {path.relative_to(app_dir)}")
        elif "__MACOSX" in rel_parts or name.startswith("._") or name == ".DS_Store":
            warnings.append(f"Packaging will exclude platform metadata: {path.relative_to(app_dir)}")
    return warnings


def resolve_app_dir(repo: Path, app_fullname: str | None, app_dir: str | None) -> Path:
    if app_dir:
        path = Path(app_dir)
        if not path.is_absolute():
            path = repo / path
        return path
    if not app_fullname:
        raise ValueError("--app-fullname or --app-dir is required")
    return repo / "internal_filesystem" / "apps" / app_fullname


def validate_app(repo: Path | None, app_dir: Path, app_fullname: str | None = None) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    if not app_dir.is_dir():
        errors.append(f"App directory does not exist: {app_dir}")
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "app": {"fullname": app_fullname, "app_dir": _display_path(app_dir, repo)},
            "layout": {"manifest": "missing", "icon": "missing"},
            "checks": [],
            "warnings": warnings,
            "errors": errors,
        }

    manifest_path, manifest_layout = _find_manifest(app_dir, warnings, errors)
    icon_path, icon_layout = _find_icon(app_dir, warnings, errors)
    manifest_data: dict[str, Any] = {}
    if manifest_path is not None:
        manifest_data = _load_json(manifest_path, errors)

    dir_name = app_dir.name
    fullname = manifest_data.get("fullname") if manifest_data else app_fullname
    if not isinstance(fullname, str) or not fullname:
        errors.append("Manifest missing non-empty fullname")
    else:
        if fullname != dir_name:
            errors.append(f"Manifest fullname {fullname!r} does not match directory name {dir_name!r}")
        if app_fullname and fullname != app_fullname:
            errors.append(f"Manifest fullname {fullname!r} does not match requested app {app_fullname!r}")

    name = manifest_data.get("name") if manifest_data else None
    if not isinstance(name, str) or not name:
        errors.append("Manifest missing non-empty name")

    publisher = manifest_data.get("publisher") if manifest_data else None
    if not isinstance(publisher, str) or not publisher.strip():
        errors.append("Manifest missing non-empty publisher")

    version = _validate_version(manifest_data.get("version"), errors) if manifest_data else None

    activities = manifest_data.get("activities", []) if manifest_data else []
    services = manifest_data.get("services", []) if manifest_data else []
    if not isinstance(activities, list):
        errors.append("Manifest activities must be an array")
        activities = []
    if not isinstance(services, list):
        errors.append("Manifest services must be an array")
        services = []
    for idx, activity in enumerate(activities):
        _validate_component(activity, f"activities[{idx}]", app_dir, errors)
    for idx, service in enumerate(services):
        _validate_component(service, f"services[{idx}]", app_dir, errors)

    warnings.extend(_find_packaging_noise(app_dir))

    checks.append(
        {
            "name": "manifest",
            "required": True,
            "ok": manifest_path is not None and not any("Manifest" in err for err in errors),
            "path": _display_path(manifest_path, repo) if manifest_path else None,
            "layout": manifest_layout,
        }
    )
    checks.append(
        {
            "name": "icon",
            "required": True,
            "ok": icon_path is not None,
            "path": _display_path(icon_path, repo) if icon_path else None,
            "layout": icon_layout,
        }
    )

    app_info = {
        "fullname": fullname if isinstance(fullname, str) else app_fullname,
        "name": name,
        "publisher": publisher,
        "version": version,
        "app_dir": _display_path(app_dir, repo),
        "manifest": _display_path(manifest_path, repo) if manifest_path else None,
        "icon": _display_path(icon_path, repo) if icon_path else None,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not errors,
        "app": app_info,
        "layout": {"manifest": manifest_layout, "icon": icon_layout},
        "manifest": manifest_data,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="MicroPythonOS repository root; defaults to MPOS_REPO or current repo root")
    parser.add_argument("--app-fullname", help="App fullname, e.g. com.micropythonos.helloworld")
    parser.add_argument("--app-dir", help="Explicit App directory")
    parser.add_argument("--output", help="Write validation JSON to this path")
    parser.add_argument("--quiet", action="store_true", help="Only print errors")
    args = parser.parse_args()

    repo = resolve_repo_arg(args.repo)
    try:
        app_dir = resolve_app_dir(repo, args.app_fullname, args.app_dir).resolve()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = validate_app(repo, app_dir, args.app_fullname)
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
        source = result["app"].get("app_dir")
        print(f"{'OK' if result['ok'] else 'FAILED'}: {source}")

    if not result["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
