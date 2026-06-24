#!/usr/bin/env python3
"""Validate firmware/conf.py contract used by generated runtime code."""

from __future__ import annotations

import argparse
import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


SECRET_NAME_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization|access[_-]?key)", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"^(YOUR_|REPLACE_|CHANGE_|TODO|PLACEHOLDER)", re.IGNORECASE)


def rel_path(project_dir: Path, path: Path) -> str:
    return path.relative_to(project_dir).as_posix()


def parse_python(path: Path) -> tuple[ast.Module | None, list[dict[str, Any]]]:
    try:
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path)), []
    except SyntaxError as exc:
        return None, [{"code": "CONF_CONTRACT_SYNTAX_ERROR", "path": str(path), "line": exc.lineno, "message": str(exc)}]


def conf_assignments(conf_path: Path, project_dir: Path) -> tuple[list[tuple[str, ast.AST, int]], list[dict[str, Any]]]:
    tree, errors = parse_python(conf_path)
    if tree is None:
        return [], errors
    assignments: list[tuple[str, ast.AST, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    assignments.append((target.id, node.value, node.lineno))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id.isupper():
            assignments.append((node.target.id, node.value, node.lineno))
    _ = project_dir
    return assignments, errors


def firmware_py_files(project_dir: Path) -> list[Path]:
    root = project_dir / "firmware"
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if path.name != "conf.py")


def conf_attribute_refs(project_dir: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for path in firmware_py_files(project_dir):
        tree, _errors = parse_python(path)
        if tree is None:
            continue
        rel = rel_path(project_dir, path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "conf":
                refs.append({"name": node.attr, "path": rel, "line": node.lineno})
    return refs


def imported_conf_names(project_dir: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for path in firmware_py_files(project_dir):
        tree, _errors = parse_python(path)
        if tree is None:
            continue
        rel = rel_path(project_dir, path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "conf":
                for alias in node.names:
                    if alias.name != "*":
                        refs.append({"name": alias.name, "path": rel, "line": node.lineno})
                    else:
                        refs.append({"name": "*", "path": rel, "line": node.lineno})
    return refs


def literal_string(value: ast.AST) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def check_project(project_dir: Path, deploy_ready: bool = False) -> dict[str, Any]:
    conf_path = project_dir / "firmware" / "conf.py"
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not conf_path.exists():
        return {
            "check": "conf_contract",
            "project_dir": str(project_dir),
            "defined": [],
            "refs": [],
            "errors": [{"code": "CONF_FILE_MISSING", "path": "firmware/conf.py", "message": "firmware/conf.py is required"}],
            "warnings": [],
            "ok": False,
        }
    assignments, parse_errors = conf_assignments(conf_path, project_dir)
    errors.extend(parse_errors)
    names = [name for name, _value, _line in assignments]
    counts = Counter(names)
    for name, count in sorted(counts.items()):
        if count > 1:
            lines = [line for item_name, _value, line in assignments if item_name == name]
            errors.append(
                {
                    "code": "CONF_DUPLICATE_CONSTANT",
                    "constant": name,
                    "path": "firmware/conf.py",
                    "lines": lines,
                    "message": f"{name} is defined {count} times in firmware/conf.py",
                }
            )
    defined = set(names)
    refs = conf_attribute_refs(project_dir) + imported_conf_names(project_dir)
    for ref in refs:
        name = ref["name"]
        if name == "*":
            errors.append(
                {
                    "code": "CONF_STAR_IMPORT",
                    "path": ref["path"],
                    "line": ref["line"],
                    "message": "from conf import * is not allowed in generated firmware",
                }
            )
        elif name not in defined:
            errors.append(
                {
                    "code": "CONF_REFERENCE_MISSING",
                    "constant": name,
                    "path": ref["path"],
                    "line": ref["line"],
                    "message": f"{ref['path']} references conf.{name}, but firmware/conf.py does not define it",
                }
            )
    for name, value, line in assignments:
        text = literal_string(value)
        if SECRET_NAME_RE.search(name) and text and text.strip() and not PLACEHOLDER_RE.search(text):
            errors.append(
                {
                    "code": "CONF_SECRET_VALUE",
                    "constant": name,
                    "path": "firmware/conf.py",
                    "line": line,
                    "message": "Secret-like config constants must not contain real values",
                }
            )
        if text and PLACEHOLDER_RE.search(text):
            record = {
                "code": "CONF_PLACEHOLDER_VALUE",
                "constant": name,
                "path": "firmware/conf.py",
                "line": line,
                "message": f"{name} still contains a placeholder value",
            }
            if deploy_ready:
                errors.append(record)
            else:
                warnings.append(record)
    return {
        "check": "conf_contract",
        "project_dir": str(project_dir),
        "defined": sorted(defined),
        "refs": refs,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Validate generated firmware/conf.py contract")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--deploy-ready", action="store_true", help="Treat placeholder values as deploy blockers")
    args = parser.parse_args()
    result = check_project(Path(args.project_dir), deploy_ready=args.deploy_ready)
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
