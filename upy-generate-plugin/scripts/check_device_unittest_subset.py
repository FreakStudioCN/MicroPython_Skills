#!/usr/bin/env python3
"""Check device tests only use the MicroPython unittest subset."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


ALLOWED_ASSERTS = {
    "assertAlmostEqual",
    "assertEqual",
    "assertFalse",
    "assertGreaterEqual",
    "assertIn",
    "assertIs",
    "assertIsInstance",
    "assertIsNone",
    "assertIsNot",
    "assertIsNotNone",
    "assertLessEqual",
    "assertNotAlmostEqual",
    "assertNotEqual",
    "assertRaises",
    "assertTrue",
    "assertWarns",
}
ALLOWED_TESTCASE_HELPERS = {
    "addCleanup",
    "doCleanups",
    "fail",
    "runTest",
    "setUp",
    "setUpClass",
    "skipTest",
    "subTest",
    "tearDown",
    "tearDownClass",
}
ALLOWED_UNITTEST_ATTRS = {
    "TestCase",
    "TestSuite",
    "TextTestRunner",
    "expectedFailure",
    "main",
    "skip",
    "skipIf",
    "skipUnless",
}
DISALLOWED_IMPORT_ROOTS = {
    "argparse",
    "asyncio",
    "dataclasses",
    "logging",
    "mock",
    "pathlib",
    "pytest",
    "requests",
    "subprocess",
    "tempfile",
    "typing",
    "unittest.mock",
}
DEVICE_TEST_DIRS = (("test", "device"), ("device", "tests"))
BEHAVIOR_MODULE_HINTS = {
    "conf",
    "protocol",
    "rotating_logger",
    "session_manager",
    "state",
}
BEHAVIOR_IMPORT_PREFIXES = ("drivers.", "tasks.", "lib.", "firmware.")


def import_root(module: str) -> str:
    if module.startswith("unittest.mock"):
        return "unittest.mock"
    return module.split(".", 1)[0]


def is_unittest_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "unittest"


def has_unittest_main(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "main" and is_unittest_name(func.value):
            return True
    return False


def import_name(alias: ast.alias, module: str | None = None) -> str:
    if module:
        return f"{module}.{alias.name}" if alias.name != "*" else module
    return alias.name


def has_behavior_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [import_name(alias) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [import_name(alias, node.module or "") for alias in node.names]
        for name in names:
            root = name.split(".", 1)[0]
            if root in BEHAVIOR_MODULE_HINTS or name.startswith(BEHAVIOR_IMPORT_PREFIXES):
                return True
    return False


def behavior_assert_count(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ALLOWED_ASSERTS:
            if func.attr == "assertTrue" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant):
                continue
            if func.attr == "assertFalse" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant):
                continue
            count += 1
    return count


def check_file(path: Path, project_dir: Path) -> list[dict[str, Any]]:
    rel = path.relative_to(project_dir).as_posix()
    errors: list[dict[str, Any]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        return [{"code": "DEVICE_TEST_SYNTAX_ERROR", "path": rel, "line": exc.lineno, "message": str(exc)}]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = import_root(alias.name)
                if root in DISALLOWED_IMPORT_ROOTS:
                    errors.append(
                        {
                            "code": "DEVICE_UNITTEST_IMPORT_UNSUPPORTED",
                            "path": rel,
                            "line": node.lineno,
                            "module": alias.name,
                            "message": "device tests must avoid CPython-only test/runtime modules",
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = import_root(module)
            imported_names = {alias.name for alias in node.names}
            if root in DISALLOWED_IMPORT_ROOTS or (module == "unittest" and "mock" in imported_names):
                errors.append(
                    {
                        "code": "DEVICE_UNITTEST_IMPORT_UNSUPPORTED",
                        "path": rel,
                        "line": node.lineno,
                        "module": module,
                        "names": sorted(imported_names),
                        "message": "device tests must avoid CPython-only test/runtime modules",
                    }
                )
        if isinstance(node, ast.Attribute) and node.attr.startswith("assert"):
            if node.attr not in ALLOWED_ASSERTS:
                errors.append(
                    {
                        "code": "DEVICE_UNITTEST_ASSERT_UNSUPPORTED",
                        "path": rel,
                        "line": node.lineno,
                        "assert_method": node.attr,
                        "message": "device tests must use MicroPython unittest assert subset",
                    }
                )
        if isinstance(node, ast.Attribute) and is_unittest_name(node.value):
            if node.attr not in ALLOWED_UNITTEST_ATTRS:
                errors.append(
                    {
                        "code": "DEVICE_UNITTEST_ATTR_UNSUPPORTED",
                        "path": rel,
                        "line": node.lineno,
                        "unittest_attr": node.attr,
                        "message": "device tests must use MicroPython unittest module subset",
                    }
                )
    if not has_behavior_import(tree):
        errors.append(
            {
                "code": "DEVICE_UNITTEST_BEHAVIOR_IMPORT_MISSING",
                "path": rel,
                "message": "device tests must exercise generated protocol/state/task/driver/config code, not only unittest/import smoke",
            }
        )
    if behavior_assert_count(tree) < 2:
        errors.append(
            {
                "code": "DEVICE_UNITTEST_BEHAVIOR_ASSERTS_MISSING",
                "path": rel,
                "message": "device tests must contain at least two non-trivial behavior assertions",
            }
        )
    return errors


def check(project_dir: Path) -> dict[str, Any]:
    files: list[Path] = []
    test_dirs = []
    for parts in DEVICE_TEST_DIRS:
        device_dir = project_dir.joinpath(*parts)
        test_dirs.append(device_dir.relative_to(project_dir).as_posix())
        if device_dir.exists():
            files.extend(sorted(device_dir.glob("test*.py")))
    errors = []
    warnings = []
    for path in files:
        file_errors = check_file(path, project_dir)
        errors.extend(file_errors)
        if not file_errors:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            if not has_unittest_main(tree):
                warnings.append(
                    {
                        "code": "DEVICE_UNITTEST_MAIN_MISSING",
                        "path": path.relative_to(project_dir).as_posix(),
                        "message": "device tests should call unittest.main() for mpremote run compatibility",
                    }
                )
    return {
        "check": "device_unittest_subset",
        "files_checked": len(files),
        "test_dirs": test_dirs,
        "allowed_asserts": sorted(ALLOWED_ASSERTS),
        "allowed_unittest_attrs": sorted(ALLOWED_UNITTEST_ATTRS),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Check MicroPython unittest assert subset")
    parser.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    result = check(Path(args.project_dir))
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
