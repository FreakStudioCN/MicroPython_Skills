#!/usr/bin/env python3
"""Run upy-generate-plugin quality gates and emit one JSON report."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump
from ensure_pylintrc import ensure as ensure_pylintrc


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PYLINT_FATAL = 1
PYLINT_ERROR = 2
PYLINT_WARNING = 4
PYLINT_REFACTOR = 8
PYLINT_CONVENTION = 16
PYLINT_USAGE = 32
PYLINT_KNOWN_BITS = PYLINT_FATAL | PYLINT_ERROR | PYLINT_WARNING | PYLINT_REFACTOR | PYLINT_CONVENTION | PYLINT_USAGE
PYLINT_STRONG_FAIL_BITS = PYLINT_FATAL | PYLINT_ERROR | PYLINT_USAGE
PYLINT_WARN_BITS = PYLINT_WARNING | PYLINT_REFACTOR | PYLINT_CONVENTION


def run_cmd(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    payload: Any = None
    if result.stdout.strip().startswith("{"):
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = None
    return {
        "command": " ".join(cmd),
        "cwd": str(cwd) if cwd else "",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "payload": payload,
    }


def py_files_for_compile(project_dir: Path) -> list[Path]:
    roots = [
        project_dir / "firmware" / "main.py",
        project_dir / "firmware" / "conf.py",
        project_dir / "firmware" / "board.py",
        project_dir / "firmware" / "drivers",
        project_dir / "firmware" / "tasks",
        project_dir / "test" / "pc",
        project_dir / "test" / "device",
        project_dir / "device" / "tests",
        project_dir / "tools",
    ]
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
        elif root.is_dir():
            files.extend(root.rglob("*.py"))
    return sorted(set(files))


def run_py_compile(project_dir: Path) -> dict[str, Any]:
    files = py_files_for_compile(project_dir)
    errors = []
    with tempfile.TemporaryDirectory(prefix="upy_generate_pycompile_") as temp_dir:
        temp_root = Path(temp_dir)
        for index, path in enumerate(files):
            rel = path.relative_to(project_dir).as_posix()
            try:
                cfile = temp_root / f"{index}.pyc"
                py_compile.compile(str(path), cfile=str(cfile), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append({"code": "PY_COMPILE_FAILED", "path": rel, "message": str(exc)})
            except OSError as exc:
                errors.append({"code": "PY_COMPILE_OS_ERROR", "path": rel, "message": str(exc)})
    return {
        "check": "py_compile",
        "returncode": 0 if not errors else 2,
        "files_checked": len(files),
        "errors": errors,
        "warnings": [],
        "ok": not errors,
    }


def pylint_targets(project_dir: Path) -> list[str]:
    targets: list[Path] = []
    main_py = project_dir / "firmware" / "main.py"
    if main_py.exists():
        targets.append(main_py)
    drivers_dir = project_dir / "firmware" / "drivers"
    if drivers_dir.exists():
        targets.extend(sorted(drivers_dir.rglob("*.py")))
    tasks_dir = project_dir / "firmware" / "tasks"
    if tasks_dir.exists():
        targets.extend(path for path in sorted(tasks_dir.glob("*.py")) if path.name != "maintenance.py")
    return [path.relative_to(project_dir).as_posix() for path in targets]


def normalize_script_result(name: str, result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("payload")
    if isinstance(payload, dict):
        return {
            **result,
            "ok": bool(payload.get("ok", result["returncode"] == 0)),
            "errors": payload.get("errors", []),
            "warnings": payload.get("warnings", []),
        }
    return {
        **result,
        "ok": result["returncode"] == 0,
        "errors": [] if result["returncode"] == 0 else [{"code": f"{name.upper()}_FAILED", "message": result.get("stdout") or result.get("stderr")}],
        "warnings": [],
    }


def pylint_exit_categories(returncode: int) -> list[str]:
    categories = []
    for bit, label in (
        (PYLINT_FATAL, "fatal"),
        (PYLINT_ERROR, "error"),
        (PYLINT_WARNING, "warning"),
        (PYLINT_REFACTOR, "refactor"),
        (PYLINT_CONVENTION, "convention"),
        (PYLINT_USAGE, "usage"),
    ):
        if returncode & bit:
            categories.append(label)
    if returncode and not categories:
        categories.append(f"unknown:{returncode}")
    return categories


def normalize_pylint_result(result: dict[str, Any], strict: bool) -> dict[str, Any]:
    returncode = int(result.get("returncode", 0) or 0)
    categories = pylint_exit_categories(returncode)
    unknown_bits = returncode & ~PYLINT_KNOWN_BITS
    fail_bits = returncode if strict else (returncode & PYLINT_STRONG_FAIL_BITS) | unknown_bits
    ok = fail_bits == 0
    errors = []
    warnings = []
    if returncode:
        record = {
            "code": "PYLINT_EXIT_CODE",
            "returncode": returncode,
            "categories": categories,
            "message": "pylint returned " + ", ".join(categories),
        }
        if ok and (returncode & PYLINT_WARN_BITS):
            record["code"] = "PYLINT_NON_BLOCKING_MESSAGES"
            warnings.append(record)
        else:
            errors.append(record)
    return {
        **result,
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "policy": "strict_all_messages" if strict else "fail_on_fatal_error_usage",
        "exit_categories": categories,
    }


def run_quality(
    project_dir: Path,
    warn_only_lib_imports: bool,
    strict_pylint: bool = False,
    session_dir: Path | None = None,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    ensure_result = ensure_pylintrc(project_dir, force=False)
    checks["ensure_pylintrc"] = {"returncode": 0, "payload": ensure_result, "ok": True, "errors": [], "warnings": []}
    checks["generate_plan"] = normalize_script_result(
        "generate_plan",
        run_cmd(
            [
                sys.executable,
                str(SCRIPTS / "check_generate_plan.py"),
                "--project-dir",
                str(project_dir),
                "--require-plan",
                "--check-files",
            ]
        ),
    )
    checks["py_compile"] = run_py_compile(project_dir)
    checks["conf_contract"] = normalize_script_result(
        "conf_contract",
        run_cmd([sys.executable, str(SCRIPTS / "check_conf_contract.py"), "--project-dir", str(project_dir)]),
    )
    checks["driver_source_compile"] = normalize_script_result(
        "driver_source_compile",
        run_cmd([sys.executable, str(SCRIPTS / "check_driver_source_compile.py"), "--project-dir", str(project_dir)]),
    )
    flake8_paths = [name for name in ("firmware", "test", "device", "tools") if (project_dir / name).exists()]
    checks["flake8"] = normalize_script_result(
        "flake8",
        run_cmd(
            [
                sys.executable,
                "-m",
                "flake8",
                "--jobs=1",
                *flake8_paths,
                "--extend-exclude=firmware/lib",
                "--max-line-length=120",
            ],
            cwd=project_dir,
        ),
    )
    targets = pylint_targets(project_dir)
    if targets:
        checks["pylint"] = normalize_pylint_result(
            run_cmd([sys.executable, "-m", "pylint", *targets, "--rcfile=.pylintrc", "--persistent=n"], cwd=project_dir),
            strict=strict_pylint,
        )
    else:
        checks["pylint"] = {
            "returncode": 2,
            "ok": False,
            "errors": [
                {
                    "code": "PYLINT_TARGETS_MISSING",
                    "message": "No generate-owned firmware files were found for pylint",
                }
            ],
            "warnings": [],
        }
    checks["pc_unittest"] = normalize_script_result(
        "pc_unittest",
        run_cmd([sys.executable, "-m", "unittest", "discover", "-s", "test/pc"], cwd=project_dir),
    )
    checks["mpy_imports"] = normalize_script_result(
        "mpy_imports",
        run_cmd([sys.executable, str(SCRIPTS / "check_mpy_imports.py"), "--project-dir", str(project_dir)]),
    )
    lib_import_cmd = [
        sys.executable,
        str(SCRIPTS / "check_mpy_imports.py"),
        "--project-dir",
        str(project_dir),
        "--include-lib",
    ]
    lib_imports = normalize_script_result("mpy_imports_lib", run_cmd(lib_import_cmd))
    if warn_only_lib_imports and not lib_imports["ok"]:
        lib_imports["warnings"] = lib_imports.get("warnings", []) + lib_imports.get("errors", [])
        lib_imports["errors"] = []
        lib_imports["ok"] = True
        lib_imports["returncode"] = 0
        lib_imports["warn_only"] = True
    checks["mpy_imports_lib"] = lib_imports
    for name, script in (
        ("dead_config", "check_dead_config.py"),
        ("task_no_machine_import", "check_task_no_machine_import.py"),
        ("device_unittest_subset", "check_device_unittest_subset.py"),
        ("runtime_dependencies", "check_runtime_dependencies.py"),
        ("doc_evidence", "check_doc_evidence.py"),
        ("skeleton_compliance", "check_skeleton_compliance.py"),
        ("generated_semantics", "check_generated_semantics.py"),
        ("cloud_integrations", "check_cloud_integrations.py"),
    ):
        checks[name] = normalize_script_result(
            name,
            run_cmd([sys.executable, str(SCRIPTS / script), "--project-dir", str(project_dir)]),
        )
    if session_dir is not None:
        checks["session_state_checkpoint"] = normalize_script_result(
            "session_state_checkpoint",
            run_cmd(
                [
                    sys.executable,
                    str(SCRIPTS / "update_session_state.py"),
                    "--session-dir",
                    str(session_dir),
                    "--project-dir",
                    str(project_dir),
                    "--check",
                ]
            ),
        )

    structured_errors = []
    warnings = []
    for name, result in checks.items():
        for warning in result.get("warnings", []):
            warnings.append({**warning, "gate": name})
        if not result.get("ok", False):
            structured_errors.append(
                {
                    "code": f"{name.upper()}_FAILED",
                    "severity": "error",
                    "phase_step": name,
                    "retryable": True,
                    "message": f"{name} quality gate failed",
                    "details": {
                        "returncode": result.get("returncode"),
                        "errors": result.get("errors", []),
                        "stdout": result.get("stdout", ""),
                        "stderr": result.get("stderr", ""),
                    },
                }
            )
    return {
        "check": "quality_gates",
        "project_dir": str(project_dir),
        "session_dir": str(session_dir) if session_dir is not None else "",
        "checks": checks,
        "structured_errors": structured_errors,
        "warnings": warnings,
        "ok": not structured_errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Run upy-generate-plugin quality gates")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--session-dir", default="", help="Optional session root containing session_state.upy_generate_plugin.json")
    parser.add_argument("--strict-lib-imports", action="store_true", help="Fail on firmware/lib import risks")
    parser.add_argument("--strict-pylint", action="store_true", help="Fail on any nonzero pylint exit code")
    args = parser.parse_args()
    result = run_quality(
        Path(args.project_dir),
        warn_only_lib_imports=not args.strict_lib_imports,
        strict_pylint=args.strict_pylint,
        session_dir=Path(args.session_dir) if args.session_dir else None,
    )
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
