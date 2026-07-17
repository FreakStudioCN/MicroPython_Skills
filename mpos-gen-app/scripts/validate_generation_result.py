#!/usr/bin/env python3
"""Validate an mpos-gen-app generation_result JSON file."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_GATES_FOR_SUCCESS = {
    "manifest",
    "cpython_syntax",
    "mpy_syntax",
    "mpy_imports",
    "make_lint",
    "flake8",
    "pylint",
}
PYLINT_STRONG_FAIL_BITS = 1 | 2 | 32


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}")
    require(isinstance(data, dict), "top-level JSON must be an object")
    return data


def _gate_errors(data: dict) -> list[str]:
    errors: list[str] = []
    gates = data.get("validation", {}).get("gates", [])
    if not isinstance(gates, list):
        return ["validation.gates must be a list"]
    by_name = {}
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            errors.append(f"validation.gates[{index}] must be an object")
            continue
        name = gate.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"validation.gates[{index}].name is required")
            continue
        by_name[name] = gate
        returncode = gate.get("returncode")
        if not isinstance(returncode, int):
            errors.append(f"{name}: returncode must be an integer")
            continue
        if name == "pylint":
            if returncode & PYLINT_STRONG_FAIL_BITS:
                errors.append(f"{name}: fatal/error/usage pylint bits are set in returncode {returncode}")
        elif gate.get("required", True) and returncode != 0:
            errors.append(f"{name}: required gate failed with returncode {returncode}")

    if data.get("result") == "success" and data.get("mode") != "plan":
        missing = sorted(REQUIRED_GATES_FOR_SUCCESS - set(by_name))
        if missing:
            errors.append("missing required success gates: " + ", ".join(missing))
    return errors


def validate(path: Path) -> None:
    data = _load(path)
    require(data.get("schema_version") == "mpos-gen-app-v1", "schema_version must be mpos-gen-app-v1")
    require(data.get("phase") == "generate", "phase must be generate")
    require(data.get("mode") in {"plan", "create", "update", "repair"}, "mode must be plan, create, update, or repair")
    require(data.get("result") in {"success", "partial", "failed"}, "result must be success, partial, or failed")
    require(isinstance(data.get("confirmed_by_user"), bool), "confirmed_by_user must be boolean")

    if data["mode"] == "plan":
        require(data["confirmed_by_user"] is False, "plan mode must not be confirmed_by_user=true")
    elif data["result"] == "success":
        require(data["confirmed_by_user"] is True, "successful write modes require confirmed_by_user=true")

    app = data.get("app")
    require(isinstance(app, dict), "app must be an object")
    fullname = app.get("fullname")
    require(isinstance(fullname, str) and fullname, "app.fullname is required")
    app_dir = app.get("app_dir")
    require(isinstance(app_dir, str) and app_dir.endswith(fullname), "app.app_dir must end with app.fullname")
    manifest = app.get("manifest")
    valid_manifest_paths = {
        f"{app_dir}/MANIFEST.JSON",
        f"{app_dir}/META-INF/MANIFEST.JSON",
    }
    require(
        isinstance(manifest, str) and manifest in valid_manifest_paths,
        "app.manifest must point to root MANIFEST.JSON; legacy META-INF/MANIFEST.JSON is accepted for existing apps",
    )
    assets_dir = app.get("assets_dir")
    require(isinstance(assets_dir, str) and assets_dir.endswith(f"{fullname}/assets"), "app.assets_dir must end with <fullname>/assets")

    for field in ("files_created", "files_modified"):
        value = data.get(field)
        require(isinstance(value, list), f"{field} must be a list")
        for item in value:
            require(isinstance(item, str), f"{field} entries must be strings")
            require("__pycache__" not in item and not item.endswith(".pyc"), f"{field} must not include Python cache artifacts")

    icon = data.get("icon", {})
    require(isinstance(icon, dict), "icon must be an object")
    if icon.get("generated"):
        icon_path = icon.get("path")
        valid_icon_paths = {
            f"{app_dir}/icon_64x64.png",
            f"{app_dir}/res/mipmap-mdpi/icon_64x64.png",
        }
        require(
            isinstance(icon_path, str) and icon_path in valid_icon_paths,
            "generated icon path must be root icon_64x64.png; legacy res/mipmap-mdpi/icon_64x64.png is accepted for existing apps",
        )

    deps = data.get("dependencies_integrated", [])
    require(isinstance(deps, list), "dependencies_integrated must be a list")
    for index, dep in enumerate(deps):
        require(isinstance(dep, dict), f"dependencies_integrated[{index}] must be an object")
        require(bool(dep.get("name")), f"dependencies_integrated[{index}].name is required")
        if dep.get("sync_needs_adapter"):
            adapter_path = dep.get("adapter_path")
            require(isinstance(adapter_path, str) and adapter_path.startswith("assets/"), f"{dep.get('name')}: sync dependency needs assets/ adapter_path")

    errors = _gate_errors(data)
    require(not errors, "; ".join(errors))

    handoff = data.get("handoff")
    require(isinstance(handoff, dict), "handoff must be an object")
    if data["mode"] == "plan":
        require(handoff.get("next_skill") == "mpos-gen-app", "plan mode should hand off back to mpos-gen-app")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_generation_result.py <generation_result.json>", file=sys.stderr)
        return 2
    validate(Path(argv[1]))
    print("Generation result is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
