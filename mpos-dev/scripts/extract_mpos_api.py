#!/usr/bin/env python3
"""
Extract MicroPython-facing API documentation from the MicroPythonOS codebase.

Outputs:
  reference/mpos-api-reference.md
  reference/mpos_api_summary.json

The extractor indexes:
  1. Native modules registered with MP_REGISTER_MODULE, normalized to
     MicroPython import/call syntax.
  2. Native module globals and type locals exposed to MicroPython.
  3. Root mpos public exports from internal_filesystem/lib/mpos/__init__.py __all__.
  4. Public top-level Python classes/functions/constants under internal_filesystem/lib/mpos.

It intentionally avoids private underscore-prefixed Python symbols.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path


GENERATOR = "extract_mpos_api.py v3"


NATIVE_SIGNATURE_OVERRIDES = {
    ("adc_mic", "read"): "read(chunk_samples, unit_id, adc_channel_list, adc_channel_num, sample_rate_hz, atten)",
    ("pdm_mic", "PDM_Mic"): "PDM_Mic(clk, data, rate=16000, bufsize=4096)",
    ("pdm_mic", "PDM_Mic.start"): "start()",
    ("pdm_mic", "PDM_Mic.stop"): "stop()",
    ("pdm_mic", "PDM_Mic.readinto"): "readinto(buffer)",
    ("pdm_mic", "PDM_Mic.deinit"): "deinit()",
    ("qrdecode", "qrdecode"): "qrdecode(buffer, width, height)",
    ("qrdecode", "qrdecode_rgb565"): "qrdecode_rgb565(buffer, width, height)",
    ("rvswd", "RVSWD"): "RVSWD(swdio, swclk)",
    ("rvswd", "RVSWD.reset"): "reset()",
    ("rvswd", "RVSWD.write_reg"): "write_reg(reg, val)",
    ("rvswd", "RVSWD.read_reg"): "read_reg(reg)",
    ("rvswd", "RVSWD.halt"): "halt()",
    ("rvswd", "RVSWD.resume"): "resume()",
    ("rvswd", "RVSWD.reset_and_run"): "reset_and_run()",
    ("rvswd", "RVSWD.read_memory"): "read_memory(addr)",
    ("rvswd", "RVSWD.write_memory"): "write_memory(addr, val)",
    ("rvswd", "RVSWD.read_vendor_bytes"): "read_vendor_bytes()",
    ("rvswd", "RVSWD.v20x_program"): "v20x_program(firmware, callback=None)",
    ("rvswd", "RVSWD.v20x_unlock_flash"): "v20x_unlock_flash()",
    ("rvswd", "RVSWD.v20x_lock_flash"): "v20x_lock_flash()",
    ("rvswd", "RVSWD.v20x_write_flash"): "v20x_write_flash(addr, data, callback=None)",
    ("rvswd", "RVSWD.v20x_clear_ops"): "v20x_clear_ops()",
    ("rvswd", "RVSWD.x03x_program"): "x03x_program(firmware, callback=None)",
    ("rvswd", "RVSWD.x03x_unlock_flash"): "x03x_unlock_flash()",
    ("rvswd", "RVSWD.x03x_lock_flash"): "x03x_lock_flash()",
    ("rvswd", "RVSWD.x03x_write_flash"): "x03x_write_flash(addr, data, callback=None)",
    ("rvswd", "RVSWD.x03x_clear_ops"): "x03x_clear_ops()",
    ("webcam", "Webcam"): "Webcam",
    ("webcam", "init"): 'init(device="/dev/video0", *, width, height)',
    ("webcam", "capture_frame"): "capture_frame(camera, format)",
    ("webcam", "deinit"): "deinit(camera)",
    ("webcam", "free_buffer"): "free_buffer(camera)",
    ("webcam", "reconfigure"): "reconfigure(camera, *, width=None, height=None)",
}


NATIVE_RETURN_OVERRIDES = {
    ("adc_mic", "read"): "bytes",
    ("pdm_mic", "PDM_Mic.start"): "None",
    ("pdm_mic", "PDM_Mic.stop"): "None",
    ("pdm_mic", "PDM_Mic.readinto"): "int",
    ("pdm_mic", "PDM_Mic.deinit"): "None",
    ("qrdecode", "qrdecode"): "bytes",
    ("qrdecode", "qrdecode_rgb565"): "bytes",
    ("rvswd", "RVSWD.reset"): "None",
    ("rvswd", "RVSWD.write_reg"): "None",
    ("rvswd", "RVSWD.read_reg"): "int",
    ("rvswd", "RVSWD.halt"): "None",
    ("rvswd", "RVSWD.resume"): "None",
    ("rvswd", "RVSWD.reset_and_run"): "None",
    ("rvswd", "RVSWD.read_memory"): "int",
    ("rvswd", "RVSWD.write_memory"): "None",
    ("rvswd", "RVSWD.read_vendor_bytes"): "tuple[int, int, int, int]",
    ("rvswd", "RVSWD.v20x_program"): "None",
    ("rvswd", "RVSWD.v20x_unlock_flash"): "None",
    ("rvswd", "RVSWD.v20x_lock_flash"): "None",
    ("rvswd", "RVSWD.v20x_write_flash"): "None",
    ("rvswd", "RVSWD.v20x_clear_ops"): "None",
    ("rvswd", "RVSWD.x03x_program"): "None",
    ("rvswd", "RVSWD.x03x_unlock_flash"): "None",
    ("rvswd", "RVSWD.x03x_lock_flash"): "None",
    ("rvswd", "RVSWD.x03x_write_flash"): "None",
    ("rvswd", "RVSWD.x03x_clear_ops"): "None",
    ("webcam", "init"): "Webcam",
    ("webcam", "capture_frame"): "memoryview",
    ("webcam", "deinit"): "None",
    ("webcam", "free_buffer"): "None",
    ("webcam", "reconfigure"): "None",
}


NATIVE_NOTES = {
    ("webcam", "Webcam"): ["Instances are returned by webcam.init(...)."],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def find_mpos_root() -> str:
    candidates = [
        os.path.expanduser("~/MicroPythonOS"),
        "/home/leeqingshui/MicroPythonOS",
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    script_dir = Path(__file__).resolve().parent.parent.parent.parent
    if os.path.isdir(script_dir / "MicroPythonOS"):
        return str(script_dir / "MicroPythonOS")
    raise FileNotFoundError("Cannot find MicroPythonOS directory. Use --mpos-dir.")


def rel_to(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def module_name_for(path: Path, mpos_lib: Path) -> str:
    rel = path.relative_to(mpos_lib)
    if rel.name == "__init__.py":
        parts = rel.parent.parts
    else:
        parts = rel.with_suffix("").parts
    return "mpos" if not parts else "mpos." + ".".join(parts)


def first_doc_line(doc: str | None) -> str | None:
    if not doc:
        return None
    for line in doc.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def line_for_offset(content: str, offset: int) -> int:
    return content[:offset].count("\n") + 1


def parse_python_file(path: Path) -> ast.Module | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.parse(read_text(path), filename=str(path))
    except SyntaxError:
        return None


def format_arg(arg: ast.arg, default: ast.expr | None = None) -> str:
    text = arg.arg
    if arg.annotation:
        text += f": {ast.unparse(arg.annotation)}"
    if default is not None:
        text += f" = {ast.unparse(default)}"
    return text


def format_arguments(args: ast.arguments) -> str:
    parts: list[str] = []
    positional = list(args.posonlyargs) + list(args.args)
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)

    for index, arg in enumerate(positional):
        if index == len(args.posonlyargs) and args.posonlyargs:
            parts.append("/")
        parts.append(format_arg(arg, defaults[index]))

    if args.vararg:
        parts.append("*" + format_arg(args.vararg))
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        parts.append(format_arg(arg, default))

    if args.kwarg:
        parts.append("**" + format_arg(args.kwarg))

    return ", ".join(parts)


def function_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    returns = ast.unparse(node.returns) if node.returns else None
    return {
        "name": node.name,
        "params": format_arguments(node.args),
        "returns": returns,
        "signature": f"{node.name}({format_arguments(node.args)})"
        + (f" -> {returns}" if returns else ""),
        "doc": ast.get_docstring(node),
        "source_line": node.lineno,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "public": not node.name.startswith("_"),
    }


def class_info(node: ast.ClassDef) -> dict:
    methods = []
    for item in ast.iter_child_nodes(node):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info = function_info(item)
            if item.name == "__init__" or info["public"]:
                methods.append(info)
    return {
        "name": node.name,
        "bases": [ast.unparse(b) for b in node.bases],
        "doc": ast.get_docstring(node),
        "source_line": node.lineno,
        "methods": methods,
        "public": not node.name.startswith("_"),
    }


def constant_info(node: ast.Assign | ast.AnnAssign, extra_public_names: set[str] | None = None) -> list[dict]:
    extra_public_names = extra_public_names or set()
    targets: list[ast.expr] = []
    value: ast.expr | None = None
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
        value = node.value
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
        value = node.value

    constants = []
    for target in targets:
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        if name.startswith("_"):
            continue
        is_constant = name.isupper() or name.startswith("CURRENT_")
        is_extra_public = name in extra_public_names
        if not is_constant and not is_extra_public:
            continue
        constants.append({
            "name": name,
            "value": ast.unparse(value) if value is not None else None,
            "source_line": node.lineno,
            "kind": "constant" if is_constant else "variable",
        })
    return constants


def extract_import_map(tree: ast.Module) -> dict:
    import_map = {}
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ImportFrom) or node.level == 0:
            continue
        base_module = node.module or ""
        for alias in node.names:
            public_name = alias.asname or alias.name
            if node.module is None:
                import_map[public_name] = {"module": alias.name, "symbol": None}
            else:
                import_map[public_name] = {"module": base_module, "symbol": alias.name}
    return import_map


def extract_all_names(tree: ast.Module) -> list[str]:
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        if isinstance(node.value, (ast.Tuple, ast.List)):
            names = []
            for item in node.value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    names.append(item.value)
            return names
    return []


def module_path(mpos_lib: Path, module_name: str) -> Path | None:
    rel = Path(*module_name.split(".")) if module_name else Path("__init__")
    py_file = mpos_lib / rel.with_suffix(".py")
    if py_file.exists():
        return py_file
    init_file = mpos_lib / rel / "__init__.py"
    if init_file.exists():
        return init_file
    package_dir = mpos_lib / rel
    if package_dir.is_dir():
        return package_dir
    return None


def resolve_root_export(mpos_lib: Path, public_name: str, spec: dict) -> dict | None:
    module_name = spec["module"]
    symbol_name = spec["symbol"]

    if symbol_name is None:
        path = module_path(mpos_lib, module_name)
        if not path:
            return None
        return {
            "kind": "module",
            "name": public_name,
            "source_name": module_name.split(".")[-1] if module_name else public_name,
            "module": "mpos" if not module_name else f"mpos.{module_name}",
            "file": rel_to(path, mpos_lib),
            "source_line": None,
        }

    path = module_path(mpos_lib, module_name)
    if path and path.is_file():
        tree = parse_python_file(path)
        if tree:
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef) and node.name == symbol_name:
                    info = class_info(node)
                    info.update({
                        "kind": "class",
                        "name": public_name,
                        "source_name": symbol_name,
                        "module": f"mpos.{module_name}" if module_name else "mpos",
                        "file": rel_to(path, mpos_lib),
                    })
                    return info
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    for const in constant_info(node, {symbol_name}):
                        if const["name"] == symbol_name:
                            return {
                                "kind": const["kind"],
                                "name": public_name,
                                "source_name": symbol_name,
                                "module": f"mpos.{module_name}" if module_name else "mpos",
                                "file": rel_to(path, mpos_lib),
                                "source_line": const["source_line"],
                                "value": const["value"],
                                "doc": None,
                            }
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
                    info = function_info(node)
                    info.update({
                        "kind": "function",
                        "name": public_name,
                        "source_name": symbol_name,
                        "module": f"mpos.{module_name}" if module_name else "mpos",
                        "file": rel_to(path, mpos_lib),
                    })
                    return info

    submodule = f"{module_name}.{symbol_name}" if module_name else symbol_name
    submodule_path = module_path(mpos_lib, submodule)
    if submodule_path:
        return {
            "kind": "module",
            "name": public_name,
            "source_name": symbol_name,
            "module": f"mpos.{submodule}",
            "file": rel_to(submodule_path, mpos_lib),
            "source_line": None,
        }

    return None


def extract_mpos_root_exports(mpos_root: Path) -> dict:
    mpos_lib = mpos_root / "internal_filesystem" / "lib" / "mpos"
    init_path = mpos_lib / "__init__.py"
    tree = ast.parse(read_text(init_path), filename=str(init_path))

    import_map = extract_import_map(tree)
    exported_names = extract_all_names(tree)

    result = {
        "source": rel_to(init_path, mpos_root),
        "exports": [],
        "modules": [],
        "missing": [],
    }

    for name in exported_names:
        spec = import_map.get(name)
        if not spec:
            result["missing"].append(name)
            continue
        resolved = resolve_root_export(mpos_lib, name, spec)
        if not resolved:
            result["missing"].append(name)
            continue
        if resolved["kind"] == "module":
            result["modules"].append(resolved)
        else:
            result["exports"].append(resolved)

    return result


def root_export_lookup(root_exports: dict) -> dict[tuple[str, str], str]:
    lookup = {}
    for entry in root_exports["exports"]:
        lookup[(entry["file"], entry.get("source_name") or entry["name"])] = entry["name"]
    return lookup


def index_python_source(mpos_root: Path, root_exports: dict) -> tuple[list[dict], list[dict]]:
    mpos_lib = mpos_root / "internal_filesystem" / "lib" / "mpos"
    root_lookup = root_export_lookup(root_exports)
    source_index: list[dict] = []
    symbols: list[dict] = []

    for path in sorted(mpos_lib.rglob("*.py")):
        rel_file = rel_to(path, mpos_lib)
        module = module_name_for(path, mpos_lib)
        tree = parse_python_file(path)
        file_info = {
            "file": rel_file,
            "module": module,
            "sha256": sha256_file(path),
            "classes": [],
            "functions": [],
            "constants": [],
            "root_exports": [],
            "parse_error": tree is None,
        }

        if tree is None:
            source_index.append(file_info)
            continue

        root_names_in_file = {
            source_name
            for (file_name, source_name), _public_name in root_lookup.items()
            if file_name == rel_file
        }

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                info = class_info(node)
                if not info["public"]:
                    continue
                root_alias = root_lookup.get((rel_file, info["name"]))
                if root_alias:
                    file_info["root_exports"].append(root_alias)
                file_info["classes"].append({
                    "name": info["name"],
                    "method_count": sum(
                        1 for m in info["methods"]
                        if m["public"] and not m["name"].startswith("__")
                    ),
                    "source_line": info["source_line"],
                    "root_export": root_alias,
                })
                class_fqname = f"{module}.{info['name']}"
                availability = ["module_public"]
                aliases = []
                if root_alias:
                    availability.append("root_export")
                    aliases.append(f"mpos.{root_alias}")
                symbols.append({
                    "kind": "class",
                    "name": info["name"],
                    "fqname": class_fqname,
                    "module": module,
                    "parent": None,
                    "signature": info["name"],
                    "params": [],
                    "returns": None,
                    "description": first_doc_line(info["doc"]),
                    "description_source": "docstring" if info["doc"] else None,
                    "notes": [],
                    "examples": [],
                    "source_path": rel_to(path, mpos_root),
                    "source_line": info["source_line"],
                    "availability": availability,
                    "aliases": aliases,
                    "deprecated": False,
                    "bases": info["bases"],
                })

                for method in info["methods"]:
                    if method["name"] == "__init__":
                        method_kind = "constructor"
                    elif method["public"] and not method["name"].startswith("__"):
                        method_kind = "method"
                    else:
                        continue
                    params = [p.strip() for p in method["params"].split(",") if p.strip()]
                    symbols.append({
                        "kind": method_kind,
                        "name": method["name"],
                        "fqname": f"{class_fqname}.{method['name']}",
                        "module": module,
                        "parent": class_fqname,
                        "signature": method["signature"],
                        "params": params,
                        "returns": method["returns"],
                        "description": first_doc_line(method["doc"]),
                        "description_source": "docstring" if method["doc"] else None,
                        "notes": [],
                        "examples": [],
                        "source_path": rel_to(path, mpos_root),
                        "source_line": method["source_line"],
                        "availability": ["module_public_member"] + (["root_export_member"] if root_alias else []),
                        "aliases": [f"mpos.{root_alias}.{method['name']}"] if root_alias else [],
                        "deprecated": False,
                    })

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                info = function_info(node)
                if not info["public"]:
                    continue
                root_alias = root_lookup.get((rel_file, info["name"]))
                if root_alias:
                    file_info["root_exports"].append(root_alias)
                file_info["functions"].append({
                    "name": info["name"],
                    "source_line": info["source_line"],
                    "root_export": root_alias,
                })
                availability = ["module_public"]
                aliases = []
                if root_alias:
                    availability.append("root_export")
                    aliases.append(f"mpos.{root_alias}")
                symbols.append({
                    "kind": "function",
                    "name": info["name"],
                    "fqname": f"{module}.{info['name']}",
                    "module": module,
                    "parent": None,
                    "signature": info["signature"],
                    "params": [p.strip() for p in info["params"].split(",") if p.strip()],
                    "returns": info["returns"],
                    "description": first_doc_line(info["doc"]),
                    "description_source": "docstring" if info["doc"] else None,
                    "notes": [],
                    "examples": [],
                    "source_path": rel_to(path, mpos_root),
                    "source_line": info["source_line"],
                    "availability": availability,
                    "aliases": aliases,
                    "deprecated": False,
                })

            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                for info in constant_info(node, root_names_in_file):
                    root_alias = root_lookup.get((rel_file, info["name"]))
                    if root_alias:
                        file_info["root_exports"].append(root_alias)
                    file_info["constants"].append(info)
                    symbols.append({
                        "kind": info["kind"],
                        "name": info["name"],
                        "fqname": f"{module}.{info['name']}",
                        "module": module,
                        "parent": None,
                        "signature": info["name"],
                        "params": [],
                        "returns": None,
                        "description": None,
                        "description_source": None,
                        "notes": [],
                        "examples": [],
                        "source_path": rel_to(path, mpos_root),
                        "source_line": info["source_line"],
                        "availability": ["module_public"] + (["root_export"] if root_alias else []),
                        "aliases": [f"mpos.{root_alias}"] if root_alias else [],
                        "deprecated": False,
                        "value": info["value"],
                    })

        source_index.append(file_info)

    return source_index, symbols


def extract_c_fun_objs(content: str) -> dict:
    fun_objs = {}
    for m in re.finditer(r"MP_DEFINE_CONST_FUN_OBJ(_\w+)?\(([^)]+)\)", content):
        args = [p.strip() for p in m.group(2).split(",")]
        if len(args) < 2:
            continue
        fun_objs[args[0]] = {
            "c_func": args[-1],
            "macro_suffix": m.group(1) or "",
            "source_line": line_for_offset(content, m.start()),
        }
    return fun_objs


def extract_c_type_defs(content: str) -> dict:
    type_defs = {}
    for m in re.finditer(r"MP_DEFINE_CONST_OBJ_TYPE\(\s*(\w+)\s*,\s*MP_QSTR_(\w+)\s*,(.*?)\);", content, re.DOTALL):
        var_name = m.group(1)
        body = m.group(3)
        locals_match = re.search(r"locals_dict\s*,\s*&(\w+)", body)
        type_defs[var_name] = {
            "name": m.group(2),
            "locals_dict": locals_match.group(1) if locals_match else None,
            "has_constructor": "make_new" in body,
            "source_line": line_for_offset(content, m.start()),
        }

    for m in re.finditer(r"static\s+const\s+mp_obj_type_t\s+(\w+)\s*=\s*\{(.*?)\};", content, re.DOTALL):
        var_name = m.group(1)
        body = m.group(2)
        name_match = re.search(r"\.name\s*=\s*MP_QSTR_(\w+)", body)
        if not name_match:
            continue
        locals_match = re.search(r"\.locals_dict\s*=\s*&?(\w+)", body)
        type_defs.setdefault(var_name, {
            "name": name_match.group(1),
            "locals_dict": locals_match.group(1) if locals_match else None,
            "has_constructor": ".make_new" in body or "make_new" in body,
            "source_line": line_for_offset(content, m.start()),
        })
    return type_defs


def extract_c_maps(content: str) -> tuple[dict, dict]:
    map_tables = {}
    for m in re.finditer(r"static\s+const\s+mp_rom_map_elem_t\s+(\w+)\[\]\s*=\s*\{(.*?)\};", content, re.DOTALL):
        table_name = m.group(1)
        body = m.group(2)
        entries = []
        for e in re.finditer(
            r"\{\s*MP_ROM_QSTR\(MP_QSTR_(\w+)\)\s*,\s*"
            r"(?:MP_ROM_PTR\(&(\w+)\)|MP_ROM_QSTR\(MP_QSTR_(\w+)\)|MP_ROM_INT\(([^)]+)\))\s*\}",
            body,
            re.DOTALL,
        ):
            entries.append({
                "name": e.group(1),
                "ptr": e.group(2),
                "qstr": e.group(3),
                "int": e.group(4),
                "source_line": line_for_offset(content, m.start() + e.start()),
            })
        map_tables[table_name] = entries

    dict_to_table = {}
    for m in re.finditer(r"(?:static\s+)?MP_DEFINE_CONST_DICT\((\w+)\s*,\s*(\w+)\s*\);", content):
        dict_to_table[m.group(1)] = m.group(2)
    return map_tables, dict_to_table


def extract_module_globals(content: str, map_tables: dict, dict_to_table: dict) -> list:
    globals_match = re.search(r"\.globals\s*=\s*\(mp_obj_dict_t\s*\*\)\s*&\s*(\w+)", content)
    if not globals_match:
        return []
    dict_name = globals_match.group(1)
    table_name = dict_to_table.get(dict_name)
    return map_tables.get(table_name, [])


def find_c_function_signature(content: str, func_name: str) -> tuple[str, int | None]:
    if not func_name:
        return "", None
    escaped = re.escape(func_name)
    pattern = rf"(static\s+)?mp_obj_t\s+{escaped}\s*\(([^)]*)\)"
    m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if m:
        params = re.sub(r"\s+", " ", m.group(2).strip())
        return f"({params})", line_for_offset(content, m.start())
    return "", None


def find_c_docstring(content: str, func_name: str) -> str:
    if not func_name:
        return ""
    lines = content.split("\n")
    func_escaped = re.escape(func_name)

    for i, line in enumerate(lines):
        if not re.search(rf"\b{func_escaped}\s*\(", line):
            continue
        if "mp_obj_t" not in line:
            continue

        previous = i - 1
        if previous < 0:
            return ""
        stripped = lines[previous].strip()

        if stripped.startswith("//"):
            doc_lines = []
            j = previous
            while j >= 0 and lines[j].strip().startswith("//"):
                comment = lines[j].strip().lstrip("/ ").strip()
                if comment and set(comment) != {"-"}:
                    doc_lines.insert(0, comment)
                j -= 1
            return " ".join(doc_lines).strip()

        if stripped.endswith("*/"):
            doc_lines = []
            j = previous
            while j >= 0:
                comment = lines[j].strip()
                comment = comment.removeprefix("/*").removeprefix("*").removesuffix("*/").strip()
                if comment and set(comment) != {"-"}:
                    doc_lines.insert(0, comment)
                if "/*" in lines[j]:
                    break
                j -= 1
            return " ".join(doc_lines).strip()

    return ""


def clean_native_doc(text: str | None) -> str | None:
    if not text:
        return None
    parts = []
    for raw in text.replace("→", "->").split():
        token = raw.strip()
        if not token:
            continue
        if set(token) <= {"-"}:
            continue
        parts.append(token)
    cleaned = " ".join(parts).strip()
    return cleaned or None


def native_signature(module: str, public_name: str, owner: str | None = None) -> str:
    key_name = f"{owner}.{public_name}" if owner else public_name
    return NATIVE_SIGNATURE_OVERRIDES.get((module, key_name), f"{public_name}(...)")


def native_returns(module: str, public_name: str, owner: str | None = None) -> str | None:
    key_name = f"{owner}.{public_name}" if owner else public_name
    return NATIVE_RETURN_OVERRIDES.get((module, key_name))


def native_notes(module: str, public_name: str, owner: str | None = None) -> list[str]:
    key_name = f"{owner}.{public_name}" if owner else public_name
    return list(NATIVE_NOTES.get((module, key_name), []))


def params_from_signature(signature: str) -> list[str]:
    match = re.search(r"\((.*)\)", signature)
    if not match:
        return []
    params = match.group(1).strip()
    if not params:
        return []
    return [p.strip() for p in params.split(",") if p.strip()]


def extract_c_modules(mpos_root: Path) -> dict:
    c_src = mpos_root / "c_mpos" / "src"
    if not c_src.is_dir():
        return {}

    modules = {}
    for path in sorted(c_src.glob("*.c")):
        content = read_text(path)
        mod_match = re.search(r"MP_REGISTER_MODULE\(MP_QSTR_(\w+)", content)
        if not mod_match:
            continue

        mod_name = mod_match.group(1)
        info = {
            "name": mod_name,
            "functions": [],
            "classes": {},
            "constants": [],
        }

        fun_objs = extract_c_fun_objs(content)
        type_defs = extract_c_type_defs(content)
        map_tables, dict_to_table = extract_c_maps(content)
        module_entries = extract_module_globals(content, map_tables, dict_to_table)

        for entry in module_entries:
            public_name = entry["name"]
            if public_name == "__name__":
                continue
            ptr = entry.get("ptr")
            if ptr in type_defs:
                type_def = type_defs[ptr]
                class_name = public_name or type_def["name"]
                methods = []
                locals_dict = type_def.get("locals_dict")
                if locals_dict:
                    locals_table = dict_to_table.get(locals_dict)
                    for method_entry in map_tables.get(locals_table, []):
                        method_name = method_entry["name"]
                        if method_name == "__del__":
                            continue
                        method_ptr = method_entry.get("ptr")
                        fun = fun_objs.get(method_ptr, {})
                        if not fun:
                            continue
                        signature = native_signature(mod_name, method_name, class_name)
                        methods.append({
                            "name": method_name,
                            "signature": signature,
                            "params": params_from_signature(signature),
                            "returns": native_returns(mod_name, method_name, class_name),
                            "doc": clean_native_doc(find_c_docstring(content, fun.get("c_func", ""))),
                        })

                class_signature = native_signature(mod_name, class_name)
                info["classes"][class_name] = {
                    "initializable": type_def.get("has_constructor", False),
                    "signature": class_signature,
                    "params": params_from_signature(class_signature),
                    "notes": native_notes(mod_name, class_name),
                    "methods": methods,
                }
            elif ptr in fun_objs:
                fun = fun_objs[ptr]
                signature = native_signature(mod_name, public_name)
                info["functions"].append({
                    "name": public_name,
                    "signature": signature,
                    "params": params_from_signature(signature),
                    "returns": native_returns(mod_name, public_name),
                    "doc": clean_native_doc(find_c_docstring(content, fun["c_func"])),
                })
            elif entry.get("int") is not None or entry.get("qstr") is not None:
                info["constants"].append({
                    "name": public_name,
                    "value": None,
                })

        modules[mod_name] = info

    return modules


def native_symbols(native_modules: dict) -> list[dict]:
    symbols = []
    for mod_name, info in sorted(native_modules.items()):
        symbols.append({
            "kind": "module",
            "name": mod_name,
            "fqname": mod_name,
            "module": mod_name,
            "parent": None,
            "signature": mod_name,
            "params": [],
            "returns": None,
            "description": None,
            "description_source": None,
            "notes": [],
            "examples": [],
            "source_path": None,
            "source_line": None,
            "availability": ["native_mpy_module"],
            "aliases": [],
            "deprecated": False,
        })
        for fun in info["functions"]:
            symbols.append({
                "kind": "function",
                "name": fun["name"],
                "fqname": f"{mod_name}.{fun['name']}",
                "module": mod_name,
                "parent": mod_name,
                "signature": fun["signature"],
                "params": fun.get("params", []),
                "returns": fun.get("returns"),
                "description": first_doc_line(fun.get("doc")),
                "description_source": "comment" if fun.get("doc") else None,
                "notes": [],
                "examples": [],
                "source_path": None,
                "source_line": None,
                "availability": ["native_mpy_module"],
                "aliases": [],
                "deprecated": False,
            })
        for cls_name, cls in info["classes"].items():
            class_fqname = f"{mod_name}.{cls_name}"
            symbols.append({
                "kind": "class",
                "name": cls_name,
                "fqname": class_fqname,
                "module": mod_name,
                "parent": mod_name,
                "signature": cls.get("signature", f"{cls_name}(...)"),
                "params": cls.get("params", []),
                "returns": None,
                "description": None,
                "description_source": None,
                "notes": cls.get("notes", []),
                "examples": [],
                "source_path": None,
                "source_line": None,
                "availability": ["native_mpy_module"],
                "aliases": [],
                "deprecated": False,
                "initializable": bool(cls.get("initializable")),
            })
            for method in cls["methods"]:
                symbols.append({
                    "kind": "method",
                    "name": method["name"],
                    "fqname": f"{class_fqname}.{method['name']}",
                    "module": mod_name,
                    "parent": class_fqname,
                    "signature": method["signature"],
                    "params": method.get("params", []),
                    "returns": method.get("returns"),
                    "description": first_doc_line(method.get("doc")),
                    "description_source": "comment" if method.get("doc") else None,
                    "notes": [],
                    "examples": [],
                    "source_path": None,
                    "source_line": None,
                    "availability": ["native_mpy_module"],
                    "aliases": [],
                    "deprecated": False,
                })
        for const in info["constants"]:
            symbols.append({
                "kind": "constant",
                "name": const["name"],
                "fqname": f"{mod_name}.{const['name']}",
                "module": mod_name,
                "parent": mod_name,
                "signature": const["name"],
                "params": [],
                "returns": None,
                "description": None,
                "description_source": None,
                "notes": [],
                "examples": [],
                "source_path": None,
                "source_line": None,
                "availability": ["native_mpy_module"],
                "aliases": [],
                "deprecated": False,
                "value": const["value"],
            })
    return symbols


def counts_for(native_modules: dict, root_exports: dict, source_index: list[dict], symbols: list[dict]) -> dict:
    return {
        "native_modules": len(native_modules),
        "native_classes": sum(len(m["classes"]) for m in native_modules.values()),
        "native_methods": sum(len(c["methods"]) for m in native_modules.values() for c in m["classes"].values()),
        "native_functions": sum(len(m["functions"]) for m in native_modules.values()),
        "native_constants": sum(len(m["constants"]) for m in native_modules.values()),
        "python_files": len(source_index),
        "python_public_classes": sum(len(f["classes"]) for f in source_index),
        "python_public_functions": sum(len(f["functions"]) for f in source_index),
        "python_public_constants": sum(len(f["constants"]) for f in source_index),
        "root_export_classes": sum(1 for e in root_exports["exports"] if e["kind"] == "class"),
        "root_export_functions": sum(1 for e in root_exports["exports"] if e["kind"] == "function"),
        "root_export_variables": sum(1 for e in root_exports["exports"] if e["kind"] in {"constant", "variable"}),
        "root_export_modules": len(root_exports["modules"]),
        "root_export_missing": len(root_exports["missing"]),
        "symbols": len(symbols),
    }


def build_summary(mpos_root: Path) -> dict:
    root_exports = extract_mpos_root_exports(mpos_root)
    source_index, python_symbols = index_python_source(mpos_root, root_exports)
    native_modules = extract_c_modules(mpos_root)
    symbols = native_symbols(native_modules) + python_symbols
    generated_at = utc_now()
    return {
        "source": {
            "mpos_root": str(mpos_root),
            "python_root": str(mpos_root / "internal_filesystem" / "lib" / "mpos"),
        },
        "generated_at": generated_at,
        "generator": GENERATOR,
        "counts": counts_for(native_modules, root_exports, source_index, symbols),
        "native_modules": native_modules,
        "root_exports": root_exports,
        "source_index": source_index,
        "symbols": symbols,
    }


def md_escape(text: object) -> str:
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ")


def drop_self(params: str | None) -> str:
    if not params:
        return ""
    parts = [p.strip() for p in params.split(",") if p.strip()]
    if parts and parts[0].split(":", 1)[0].strip() in {"self", "cls"}:
        parts = parts[1:]
    return ", ".join(parts)


def generate_markdown(summary: dict) -> str:
    native_modules = summary["native_modules"]
    root_exports = summary["root_exports"]
    source_index = summary["source_index"]
    counts = summary["counts"]

    lines: list[str] = []
    lines.append("# MicroPythonOS API Reference")
    lines.append("")
    lines.append(f"> Auto-generated by `{summary['generator']}` at `{summary['generated_at']}`.")
    lines.append("")
    lines.append("本文件记录 MicroPython 用户可调用的 API：native MicroPython 模块、`mpos.__all__` 根导出，以及 `internal_filesystem/lib/mpos` 下非下划线 public Python 类/函数/常量。")
    lines.append("机器可读版本见 `mpos_api_summary.json`。")
    lines.append("")
    lines.append("## 目录")
    lines.append("")
    lines.append("1. [统计](#1-统计)")
    lines.append("2. [全源码索引](#2-全源码索引)")
    lines.append("3. [Native MicroPython 模块](#3-native-micropython-模块)")
    lines.append("4. [mpos 根导出 API](#4-mpos-根导出-api)")
    lines.append("5. [模块级 public Python API](#5-模块级-public-python-api)")
    lines.append("6. [App 开发速查](#6-app-开发速查)")
    lines.append("")

    lines.append("## 1. 统计")
    lines.append("")
    lines.append("| 项 | 数量 |")
    lines.append("|---|---:|")
    for key in [
        "python_files", "python_public_classes", "python_public_functions",
        "python_public_constants", "root_export_classes", "root_export_functions",
        "root_export_variables", "root_export_modules", "native_modules", "native_classes",
        "native_methods", "native_functions", "native_constants", "symbols",
    ]:
        lines.append(f"| `{key}` | {counts[key]} |")
    lines.append("")

    lines.append("## 2. 全源码索引")
    lines.append("")
    lines.append("索引范围：`internal_filesystem/lib/mpos/**/*.py`。`root exports` 表示该文件中的符号被 `from mpos import ...` 直接导出。")
    lines.append("")
    lines.append("| 文件 | 模块 | class | function | constant | root exports |")
    lines.append("|---|---|---:|---:|---:|---|")
    for item in source_index:
        root_names = ", ".join(sorted(set(item["root_exports"])))
        lines.append(
            f"| `{md_escape(item['file'])}` | `{md_escape(item['module'])}` | "
            f"{len(item['classes'])} | {len(item['functions'])} | {len(item['constants'])} | "
            f"{md_escape(root_names)} |"
        )
    lines.append("")

    lines.append("## 3. Native MicroPython 模块")
    lines.append("")
    lines.append(f"共 {len(native_modules)} 个 native MicroPython 模块。")
    lines.append("")
    for mod_name in sorted(native_modules.keys()):
        info = native_modules[mod_name]
        lines.append(f"### `{mod_name}`")
        lines.append("")
        if info["classes"]:
            for cls_name, cls in info["classes"].items():
                lines.append(f"#### class `{mod_name}.{cls_name}`")
                lines.append("")
                if cls.get("initializable"):
                    lines.append(f"- 构造: `{mod_name}.{cls.get('signature', cls_name)}`")
                else:
                    lines.append(f"- 类型: `{mod_name}.{cls_name}`")
                for note in cls.get("notes", []):
                    lines.append(f"- 说明: {md_escape(note)}")
                if cls["methods"]:
                    lines.append("")
                    lines.append("| 方法 | MicroPython 调用 | 返回 | 说明 |")
                    lines.append("|---|---|---|---|")
                    for method in cls["methods"]:
                        lines.append(
                            f"| `{method['name']}` | `{md_escape(method['signature'])}` | "
                            f"`{md_escape(method.get('returns'))}` | {md_escape(first_doc_line(method.get('doc')))} |"
                        )
                lines.append("")
        if info["functions"]:
            lines.append("#### 模块函数")
            lines.append("")
            lines.append("| 函数 | MicroPython 调用 | 返回 | 说明 |")
            lines.append("|---|---|---|---|")
            for fun in info["functions"]:
                lines.append(
                    f"| `{fun['name']}` | `{md_escape(fun['signature'])}` | "
                    f"`{md_escape(fun.get('returns'))}` | {md_escape(first_doc_line(fun.get('doc')))} |"
                )
            lines.append("")
        if info["constants"]:
            lines.append("#### 常量")
            lines.append("")
            for const in info["constants"]:
                if const.get("value") is None:
                    lines.append(f"- `{const['name']}`")
                else:
                    lines.append(f"- `{const['name']}` = `{const['value']}`")
            lines.append("")
        if not info["classes"] and not info["functions"] and not info["constants"]:
            lines.append("*(无公共 API)*")
            lines.append("")

    lines.append("## 4. mpos 根导出 API")
    lines.append("")
    lines.append("来源：`internal_filesystem/lib/mpos/__init__.py` 的 `__all__`。这是 `from mpos import ...` 的稳定入口索引。")
    lines.append("")
    for entry in root_exports["exports"]:
        if entry["kind"] == "class":
            bases = ", ".join(entry.get("bases", [])) or "object"
            lines.append(f"### `mpos.{entry['name']}`")
            lines.append("")
            lines.append(f"- 类型: class")
            lines.append(f"- 源文件: `{entry['file']}`")
            lines.append(f"- 基类: `{bases}`")
            if entry.get("doc"):
                lines.append(f"- 说明: {md_escape(first_doc_line(entry['doc']))}")
            init = next((m for m in entry.get("methods", []) if m["name"] == "__init__"), None)
            if init:
                lines.append(f"- 构造: `{entry['name']}({drop_self(init['params'])})`")
            public_methods = [
                m for m in entry.get("methods", [])
                if m["public"] and not m["name"].startswith("__")
            ]
            if public_methods:
                lines.append("")
                lines.append("公共方法:")
                for method in public_methods:
                    lines.append(f"- `{method['signature']}`")
            lines.append("")
        elif entry["kind"] == "function":
            lines.append(f"### `mpos.{entry['name']}`")
            lines.append("")
            lines.append(f"- 类型: function")
            lines.append(f"- 源文件: `{entry['file']}`")
            lines.append(f"- 签名: `{entry['signature']}`")
            if entry.get("doc"):
                lines.append(f"- 说明: {md_escape(first_doc_line(entry['doc']))}")
            lines.append("")
        elif entry["kind"] in {"constant", "variable"}:
            lines.append(f"### `mpos.{entry['name']}`")
            lines.append("")
            lines.append(f"- 类型: {entry['kind']}")
            lines.append(f"- 源文件: `{entry['file']}`")
            lines.append(f"- 值: `{md_escape(entry.get('value'))}`")
            lines.append("")
    if root_exports["modules"]:
        lines.append("### 导出的子模块")
        lines.append("")
        for module in root_exports["modules"]:
            lines.append(f"- `mpos.{module['name']}` -> `{module['file']}`")
        lines.append("")
    if root_exports["missing"]:
        lines.append("### 未解析导出")
        lines.append("")
        for name in root_exports["missing"]:
            lines.append(f"- `{name}`")
        lines.append("")

    lines.append("## 5. 模块级 public Python API")
    lines.append("")
    lines.append("本节来自 `internal_filesystem/lib/mpos/**/*.py` 的 AST 索引，列出非下划线 public 类、函数、常量及类公共方法。")
    lines.append("")
    symbols_by_module: dict[str, list[dict]] = {}
    for symbol in summary["symbols"]:
        if not symbol["module"].startswith("mpos"):
            continue
        if symbol["kind"] in {"class", "function", "constant", "constructor", "method"}:
            symbols_by_module.setdefault(symbol["module"], []).append(symbol)

    for module in sorted(symbols_by_module):
        top_level = [
            s for s in symbols_by_module[module]
            if s["kind"] in {"class", "function", "constant"}
        ]
        if not top_level:
            continue
        lines.append(f"### `{module}`")
        lines.append("")
        for symbol in top_level:
            alias = f" aliases: {', '.join(symbol['aliases'])}" if symbol.get("aliases") else ""
            if symbol["kind"] == "class":
                lines.append(f"- class `{symbol['name']}`{alias}")
                methods = [
                    s for s in symbols_by_module[module]
                    if s.get("parent") == symbol["fqname"] and s["kind"] in {"constructor", "method"}
                ]
                for method in methods:
                    lines.append(f"  - `{method['signature']}`")
            elif symbol["kind"] == "function":
                lines.append(f"- function `{symbol['signature']}`{alias}")
            elif symbol["kind"] == "constant":
                value = f" = `{symbol.get('value')}`" if symbol.get("value") is not None else ""
                lines.append(f"- constant `{symbol['name']}`{value}")
        lines.append("")

    lines.append("## 6. App 开发速查")
    lines.append("")
    lines.append("### 文件结构")
    lines.append("")
    lines.append("```text")
    lines.append("internal_filesystem/apps/com.micropythonos.<name>/")
    lines.append("├── MANIFEST.JSON")
    lines.append("├── icon_64x64.png")
    lines.append("├── assets/main.py")
    lines.append("```")
    lines.append("")
    lines.append("### Activity 模板")
    lines.append("")
    lines.append("```python")
    lines.append("import lvgl as lv")
    lines.append("from mpos import Activity")
    lines.append("")
    lines.append("")
    lines.append("class MyActivity(Activity):")
    lines.append("    def __init__(self):")
    lines.append("        super().__init__()")
    lines.append("")
    lines.append("    def onCreate(self):")
    lines.append("        screen = lv.obj()")
    lines.append("        label = lv.label(screen)")
    lines.append("        label.set_text(\"Hello MPOS!\")")
    lines.append("        label.center()")
    lines.append("        self.setContentView(screen)")
    lines.append("```")
    lines.append("")
    lines.append("### 常用导入")
    lines.append("")
    lines.append("```python")
    lines.append("from mpos import Activity, App, Intent")
    lines.append("from mpos import AppManager, SharedPreferences")
    lines.append("from mpos import CameraManager, AudioManager")
    lines.append("```")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract MicroPythonOS public API references")
    parser.add_argument("--mpos-dir", default=None, help="Path to MicroPythonOS checkout")
    args = parser.parse_args()

    mpos_root = Path(args.mpos_dir or find_mpos_root()).resolve()
    print(f"Scanning MicroPythonOS at: {mpos_root}")

    summary = build_summary(mpos_root)

    output_dir = Path(__file__).resolve().parent.parent / "reference"
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / "mpos-api-reference.md"
    json_path = output_dir / "mpos_api_summary.json"

    md_path.write_text(generate_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = summary["counts"]
    print(f"  Wrote Markdown API reference to: {md_path}")
    print(f"  Wrote JSON API summary to: {json_path}")
    print(f"  Python files indexed: {counts['python_files']}")
    print(
        "  Python public API: "
        f"{counts['python_public_classes']} class(es), "
        f"{counts['python_public_functions']} function(s), "
        f"{counts['python_public_constants']} constant(s)"
    )
    print(
        "  Root exports: "
        f"{counts['root_export_classes']} class(es), "
        f"{counts['root_export_functions']} function(s), "
        f"{counts['root_export_variables']} variable(s), "
        f"{counts['root_export_modules']} module(s)"
    )
    print(
        "  Native MicroPython modules: "
        f"{counts['native_modules']} module(s), "
        f"{counts['native_classes']} class(es), "
        f"{counts['native_methods']} method(s), "
        f"{counts['native_functions']} function(s), "
        f"{counts['native_constants']} constant(s)"
    )
    print(f"  Total symbols: {counts['symbols']}")


if __name__ == "__main__":
    main()
