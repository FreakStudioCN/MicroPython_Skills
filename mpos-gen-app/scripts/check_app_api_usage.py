#!/usr/bin/env python3
"""Check generated MPOS App API usage against MPOS/LVGL summaries."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_SKILL_ROOT = Path("/home/leeqingshui/MicroPython_Skills")
FULLNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
COMMON_WIDGETS = {"lv.obj", "lv.label"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def app_files(app_dir: Path) -> list[Path]:
    assets = app_dir / "assets"
    roots = [assets] if assets.is_dir() else [app_dir]
    files: list[Path] = []
    for root in roots:
        files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(set(files))


def attr_chain(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        base = attr_chain(node.value)
        if base:
            return base + [node.attr]
    return None


def expr_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        chain = attr_chain(node)
        if chain and chain[0] == "self":
            return ".".join(chain)
    return None


def literal_list(node: ast.AST) -> list[Any] | None:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    values: list[Any] = []
    for item in node.elts:
        if isinstance(item, ast.Constant):
            values.append(item.value)
        else:
            values.append({"dynamic": ast.unparse(item) if hasattr(ast, "unparse") else type(item).__name__})
    return values


class ApiIndex:
    def __init__(self, lvgl_summary: Path, mpos_summary: Path):
        self.lvgl = load_json(lvgl_summary)
        self.mpos = load_json(mpos_summary)
        self.lv_available: set[str] = set()
        self.mpos_available: set[str] = set()
        self.lv_kind: dict[str, str] = {}
        self.methods_by_parent: dict[str, set[str]] = {}
        self.widget_fqnames: set[str] = set()
        self.type_alias_names: set[str] = set()
        self._load_lvgl()
        self._load_mpos()

    def _load_lvgl(self) -> None:
        for alias in self.lvgl.get("type_aliases", []):
            if isinstance(alias, dict) and isinstance(alias.get("name"), str):
                self.type_alias_names.add(alias["name"])
        for symbol in self.lvgl.get("symbols", []):
            if not isinstance(symbol, dict):
                continue
            fqname = symbol.get("fqname")
            if not isinstance(fqname, str):
                continue
            self.lv_available.add(fqname)
            kind = str(symbol.get("kind") or "")
            self.lv_kind[fqname] = kind
            parent = symbol.get("parent")
            name = symbol.get("name")
            if kind == "widget":
                self.widget_fqnames.add(fqname)
            if kind == "method" and isinstance(parent, str) and isinstance(name, str):
                self.methods_by_parent.setdefault(parent, set()).add(name)

    def _load_mpos(self) -> None:
        for symbol in self.mpos.get("symbols", []):
            if not isinstance(symbol, dict):
                continue
            fqname = symbol.get("fqname")
            if isinstance(fqname, str):
                self.mpos_available.add(fqname)
            aliases = symbol.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str):
                        self.mpos_available.add(alias)
        root_exports = self.mpos.get("root_exports", {})
        if isinstance(root_exports, dict):
            exports = root_exports.get("exports", [])
            if isinstance(exports, list):
                for export in exports:
                    if isinstance(export, dict) and isinstance(export.get("name"), str):
                        self.mpos_available.add(f"mpos.{export['name']}")

    def has_lv_method(self, parent: str, method: str) -> bool:
        if method in self.methods_by_parent.get(parent, set()):
            return True
        if parent in self.widget_fqnames and method in self.methods_by_parent.get("lv.obj", set()):
            return True
        return False


class Analyzer:
    def __init__(self, repo: Path, app_dir: Path, api: ApiIndex):
        self.repo = repo
        self.app_dir = app_dir
        self.api = api
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.lv_aliases: set[str] = set()
        self.mpos_aliases: set[str] = set()
        self.inferred_types: dict[str, str] = {}
        self.literal_lists: dict[str, list[Any]] = {}
        self.widget_uses: set[str] = set()
        self._reported: set[tuple[str, str, int, str]] = set()

    def rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.repo.resolve()))
        except ValueError:
            return str(path)

    def report(self, level: str, code: str, path: Path, line: int, message: str, **extra: Any) -> None:
        key = (level, code, self.rel(path), line, message)
        if key in self._reported:
            return
        self._reported.add(key)
        item = {"code": code, "path": self.rel(path), "line": line, "message": message}
        item.update(extra)
        if level == "error":
            self.errors.append(item)
        else:
            self.warnings.append(item)

    def scan_imports_and_assignments(self, tree: ast.AST, path: Path) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "lvgl":
                        self.lv_aliases.add(alias.asname or alias.name)
                    if alias.name == "mpos":
                        self.mpos_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                if node.module == "mpos":
                    for alias in node.names:
                        if alias.name == "*":
                            self.report("warning", "MPOS_STAR_IMPORT", path, node.lineno, "from mpos import * cannot be fully API-checked")
                            continue
                        fqname = f"mpos.{alias.name}"
                        if fqname not in self.api.mpos_available:
                            self.report("error", "MPOS_SYMBOL_UNKNOWN", path, node.lineno, f"{fqname} is not present in mpos_api_summary.json")
            elif isinstance(node, ast.Assign):
                values = literal_list(node.value)
                call_type = self.call_lv_type(node.value)
                for target in node.targets:
                    key = expr_key(target)
                    if key and values is not None:
                        self.literal_lists[key] = values
                    if key and call_type:
                        self.inferred_types[key] = call_type
                        if call_type in self.api.widget_fqnames:
                            self.widget_uses.add(call_type)

    def call_lv_type(self, node: ast.AST) -> str | None:
        if not isinstance(node, ast.Call):
            return None
        chain = attr_chain(node.func)
        if not chain or chain[0] not in self.lv_aliases or len(chain) != 2:
            return None
        fqname = "lv." + chain[1]
        if fqname in self.api.lv_available:
            return fqname
        return None

    def check_lv_chain(self, chain: list[str], path: Path, line: int) -> None:
        if not chain or chain[0] not in self.lv_aliases or len(chain) < 2:
            return
        if len(chain) == 2 and chain[1] in self.api.type_alias_names:
            self.report(
                "error",
                "LVGL_TYPE_ALIAS_USED_AS_RUNTIME_API",
                path,
                line,
                f"lv.{chain[1]} is a type alias in lvgl.pyi, not a runtime API",
            )
            return
        fqname = "lv." + ".".join(chain[1:])
        if fqname in self.api.lv_available:
            return
        self.report("error", "LVGL_SYMBOL_UNKNOWN", path, line, f"{fqname} is not present in lvgl_api_summary.json")

    def check_mpos_chain(self, chain: list[str], path: Path, line: int) -> None:
        if not chain or chain[0] not in self.mpos_aliases or len(chain) < 2:
            return
        fqname = "mpos." + ".".join(chain[1:])
        if fqname in self.api.mpos_available:
            return
        root = "mpos." + chain[1]
        if root in self.api.mpos_available:
            return
        self.report("error", "MPOS_SYMBOL_UNKNOWN", path, line, f"{fqname} is not present in mpos_api_summary.json")

    def check_method_call(self, call: ast.Call, path: Path) -> None:
        if not isinstance(call.func, ast.Attribute):
            return
        receiver_key = expr_key(call.func.value)
        if not receiver_key:
            return
        receiver_type = self.inferred_types.get(receiver_key)
        if not receiver_type or not receiver_type.startswith("lv."):
            return
        method = call.func.attr
        if not self.api.has_lv_method(receiver_type, method):
            self.report(
                "error",
                "LVGL_METHOD_UNKNOWN",
                path,
                call.lineno,
                f"{receiver_type}.{method} is not present in lvgl_api_summary.json or inherited lv.obj methods",
            )
        if receiver_type == "lv.buttonmatrix" and method == "set_map":
            self.check_buttonmatrix_map(call, path)

    def check_buttonmatrix_map(self, call: ast.Call, path: Path) -> None:
        if not call.args:
            self.report("error", "BUTTONMATRIX_MAP_MISSING", path, call.lineno, "lv.buttonmatrix.set_map() requires a map argument")
            return
        values = literal_list(call.args[0])
        if values is None:
            key = expr_key(call.args[0])
            if key:
                values = self.literal_lists.get(key)
        if values is None:
            self.report(
                "warning",
                "BUTTONMATRIX_MAP_DYNAMIC",
                path,
                call.lineno,
                "buttonmatrix map is dynamic; verify it uses '\\n' row separators and final empty-string terminator",
            )
            return
        if not values:
            self.report("error", "BUTTONMATRIX_MAP_EMPTY", path, call.lineno, "buttonmatrix map must not be empty")
            return
        if values[-1] != "":
            self.report(
                "error",
                "BUTTONMATRIX_MAP_TERMINATOR",
                path,
                call.lineno,
                "standalone lv.buttonmatrix.set_map() map must terminate with an empty string",
                observed=values[-1],
            )
        if "\n" not in values:
            self.report(
                "error",
                "BUTTONMATRIX_MAP_ROW_SEPARATOR",
                path,
                call.lineno,
                "buttonmatrix map should use '\\n' entries to separate rows",
            )
        for index, value in enumerate(values):
            if isinstance(value, bytes):
                self.report(
                    "error",
                    "BUTTONMATRIX_MAP_BYTES",
                    path,
                    call.lineno,
                    "buttonmatrix map labels must be str, not bytes",
                    index=index,
                )
            elif isinstance(value, str) and any(ord(ch) > 127 for ch in value):
                self.report(
                    "warning",
                    "BUTTONMATRIX_MAP_NON_ASCII",
                    path,
                    call.lineno,
                    "buttonmatrix map contains non-ASCII labels; prefer ASCII unless verified on target LVGL font/input path",
                    index=index,
                    value=value,
                )

    def analyze_file(self, path: Path) -> None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except SyntaxError as exc:
            self.report("error", "PY_SYNTAX_ERROR", path, exc.lineno or 0, str(exc))
            return
        self.scan_imports_and_assignments(tree, path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                chain = attr_chain(node)
                if chain:
                    self.check_lv_chain(chain, path, node.lineno)
                    self.check_mpos_chain(chain, path, node.lineno)
            elif isinstance(node, ast.Call):
                self.check_method_call(node, path)

    def warn_zero_reference_widgets(self) -> None:
        app_roots = [
            self.repo / "internal_filesystem" / "apps",
            self.repo / "internal_filesystem" / "builtin" / "apps",
        ]
        for widget in sorted(self.widget_uses - COMMON_WIDGETS):
            name = widget.split(".", 1)[1]
            pattern = re.compile(rf"\blv\.{re.escape(name)}\s*\(")
            examples: list[str] = []
            for root in app_roots:
                if not root.is_dir():
                    continue
                for path in root.rglob("*.py"):
                    if self.app_dir in path.parents:
                        continue
                    try:
                        text = path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    if pattern.search(text):
                        examples.append(self.rel(path))
                        if len(examples) >= 5:
                            break
                if len(examples) >= 5:
                    break
            if not examples:
                self.warnings.append(
                    {
                        "code": "LVGL_WIDGET_ZERO_APP_REFERENCES",
                        "widget": widget,
                        "message": (
                            f"{widget} has no existing App usage examples in internal_filesystem/apps or builtin/apps; "
                            "verify API semantics carefully and consider simpler ordinary-button/flex layouts."
                        ),
                    }
                )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="MicroPythonOS repository root")
    parser.add_argument("--app-fullname", required=True, help="App fullname under internal_filesystem/apps")
    parser.add_argument("--app-dir", help="Explicit app directory")
    parser.add_argument("--lvgl-summary", help="Path to lvgl_api_summary.json")
    parser.add_argument("--mpos-summary", help="Path to mpos_api_summary.json")
    args = parser.parse_args(argv)

    repo = resolve_repo(args.repo)
    fullname = safe_fullname(args.app_fullname)
    app_dir = Path(args.app_dir).expanduser() if args.app_dir else repo / "internal_filesystem" / "apps" / fullname
    if not app_dir.is_absolute():
        app_dir = repo / app_dir
    lvgl_summary = Path(args.lvgl_summary) if args.lvgl_summary else DEFAULT_SKILL_ROOT / "mpos-dev" / "reference" / "lvgl_api_summary.json"
    mpos_summary = Path(args.mpos_summary) if args.mpos_summary else DEFAULT_SKILL_ROOT / "mpos-dev" / "reference" / "mpos_api_summary.json"

    if not app_dir.is_dir():
        result = {
            "schema_version": "mpos-gen-app-api-usage-v1",
            "ok": False,
            "repo": str(repo),
            "app": {
                "fullname": fullname,
                "app_dir": str(app_dir),
            },
            "api_references": {
                "lvgl_summary": str(lvgl_summary),
                "mpos_summary": str(mpos_summary),
            },
            "files_checked": [],
            "errors": [
                {
                    "code": "APP_DIR_MISSING",
                    "path": str(app_dir),
                    "line": 0,
                    "message": "target App directory does not exist",
                }
            ],
            "warnings": [],
        }
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 1

    analyzer = Analyzer(repo, app_dir.resolve(), ApiIndex(lvgl_summary, mpos_summary))
    files = app_files(app_dir)
    for path in files:
        analyzer.analyze_file(path)
    analyzer.warn_zero_reference_widgets()

    result = {
        "schema_version": "mpos-gen-app-api-usage-v1",
        "ok": not analyzer.errors,
        "repo": str(repo),
        "app": {
            "fullname": fullname,
            "app_dir": str(app_dir),
        },
        "api_references": {
            "lvgl_summary": str(lvgl_summary),
            "lvgl_generated_at": analyzer.api.lvgl.get("generated_at"),
            "mpos_summary": str(mpos_summary),
            "mpos_generated_at": analyzer.api.mpos.get("generated_at"),
        },
        "files_checked": [analyzer.rel(path) for path in files],
        "errors": analyzer.errors,
        "warnings": analyzer.warnings,
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
