#!/usr/bin/env python3
"""
Extract LVGL MicroPython API from lvgl_micropython/lvgl.pyi.

Outputs:
  reference/lvgl_api_summary.json
  reference/lvgl-api-reference.md

The source of truth for this skill is the generated MicroPython stub file:
  /home/leeqingshui/lvgl_micropython/lvgl.pyi

Use --from-build or --from-source only when lvgl.pyi must be regenerated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


GENERATOR = "extract_lvgl_api.py v5"


TYPE_ALIAS_RUNTIME_ENUM_OVERRIDES = {
    "event_code_t": "EVENT",
    "fs_whence_t": "FS_SEEK",
    "encoding_code128_t": "barcode.ENCODING_CODE128",
    "long_mode_t": "label.LONG_MODE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def line_for_offset(content: str, offset: int) -> int:
    return content[:offset].count("\n") + 1


def find_lvgl_micropython_root() -> str:
    candidates = [
        os.path.expanduser("~/lvgl_micropython"),
        "/home/leeqingshui/lvgl_micropython",
        os.path.expanduser("~/MicroPythonOS/lvgl_micropython"),
        "/home/leeqingshui/MicroPythonOS/lvgl_micropython",
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    raise FileNotFoundError("Cannot find lvgl_micropython. Set --lvgl-micropython-dir.")


def generate_from_build(lvgl_mpy_root: str) -> str:
    build_dir = os.path.join(
        lvgl_mpy_root, "lib", "micropython", "ports", "unix", "build-standard"
    )
    lv_mpy_json = os.path.join(build_dir, "lv_mpy.json")
    lvgl_api_json = os.path.join(build_dir, "lvgl_api.json")
    if not os.path.exists(lv_mpy_json):
        raise FileNotFoundError(
            f"{lv_mpy_json} not found. Run './scripts/build_mpos.sh unix' first."
        )
    if not os.path.exists(lvgl_api_json):
        raise FileNotFoundError(
            f"{lvgl_api_json} not found. Run './scripts/build_mpos.sh unix' first."
        )

    gen_dir = os.path.join(lvgl_mpy_root, "gen")
    sys.path.insert(0, gen_dir)
    import stub_gen

    stub_gen.run(lv_mpy_json, lvgl_api_json)
    output = os.path.join(lvgl_mpy_root, "lvgl.pyi")
    if not os.path.exists(output):
        raise RuntimeError("stub_gen.run() completed but lvgl.pyi was not created")
    return output


def generate_from_source(lvgl_mpy_root: str) -> str:
    gen_dir = os.path.join(lvgl_mpy_root, "gen")
    lib_dir = os.path.join(lvgl_mpy_root, "lib")
    lvgl_dir = os.path.join(lib_dir, "lvgl")
    lvgl_header = os.path.join(lvgl_dir, "lvgl.h")
    if not os.path.exists(lvgl_header):
        raise FileNotFoundError(f"LVGL header not found: {lvgl_header}")

    import tempfile

    with tempfile.TemporaryDirectory(suffix=".lvgl_gen") as tmpdir:
        metadata_path = os.path.join(tmpdir, "lvgl_metadata.json")
        c_output_path = os.path.join(tmpdir, "lv_mp.c")
        script = os.path.join(gen_dir, "lvgl_api_gen_mpy.py")
        cmd = [
            sys.executable,
            script,
            "-I",
            lib_dir,
            "-I",
            lvgl_dir,
            "--board=unix",
            "--module_name=lvgl",
            "--module_prefix=lv",
            f"--metadata={metadata_path}",
            f"--output={c_output_path}",
            lvgl_header,
        ]
        result = subprocess.run(cmd, cwd=lvgl_mpy_root, capture_output=True, text=True)
        if not os.path.exists(metadata_path):
            raise RuntimeError(
                "lvgl_api_gen_mpy.py failed:\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

        sys.path.insert(0, gen_dir)
        import stub_gen

        stub_gen.run(metadata_path, metadata_path)

    output = os.path.join(lvgl_mpy_root, "lvgl.pyi")
    if not os.path.exists(output):
        raise RuntimeError("stub_gen.run() completed but lvgl.pyi was not created")
    return output


def parse_method_defs(body: str, body_start_line: int) -> list[dict]:
    methods = []
    for dm in re.finditer(
        r"^\s{4}def (\w+)\((.*?)\)(?:\s*->\s*([^:\n]+))?\s*:",
        body,
        re.MULTILINE,
    ):
        params = dm.group(2).strip()
        returns = dm.group(3).strip() if dm.group(3) else None
        methods.append({
            "name": dm.group(1),
            "params": params,
            "returns": returns,
            "signature": f"{dm.group(1)}({params})" + (f" -> {returns}" if returns else ""),
            "source_line": body_start_line + body[:dm.start()].count("\n"),
        })
    return methods


def parse_enum_values(body: str) -> dict:
    values = {}
    for vm in re.finditer(
        r"^\s{3,8}(\w+)(?::\s*ClassVar\[int\])?\s*=\s*(.+)$",
        body,
        re.MULTILINE,
    ):
        name = vm.group(1)
        value = vm.group(2).strip()
        if name.startswith("_") and not re.match(r"_\d+$", name):
            continue
        values[name] = value
    return values


def parse_nested_enum_classes(body: str, owner_name: str, owner_start_line: int) -> list[dict]:
    enums = []
    for m in re.finditer(
        r"^\s{4}class (\w+)\(object\):\n(.*?)(?=^\s{4}class |^\s{4}def |\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    ):
        class_name = m.group(1)
        nested_body = m.group(2)
        if re.search(r"^\s{8}def ", nested_body, re.MULTILINE):
            continue
        values = parse_enum_values(nested_body)
        if not values:
            continue
        enums.append({
            "name": f"{owner_name}.{class_name}",
            "parent": owner_name,
            "values": values,
            "source_line": owner_start_line + body[:m.start()].count("\n"),
        })
    return enums


def parse_pyi(pyi_path: str) -> dict:
    with open(pyi_path, encoding="utf-8", errors="replace") as f:
        content = f.read()

    abs_path = os.path.abspath(pyi_path)
    result = {
        "source": {
            "kind": "mpy_stub",
            "path": abs_path,
            "sha256": sha256_file(abs_path),
        },
        "type_aliases": [],
        "enums": [],
        "data_classes": [],
        "widgets": [],
        "functions": [],
    }

    seen_type_aliases = set()
    for m in re.finditer(r"^(\w+_t|_mp_int_wrapper)\s*=\s*(int|float)\s*$", content, re.MULTILINE):
        alias_name = m.group(1)
        if alias_name in seen_type_aliases:
            continue
        seen_type_aliases.add(alias_name)
        result["type_aliases"].append({
            "name": alias_name,
            "target": m.group(2),
            "runtime_api": False,
            "runtime_enum": None,
            "source_line": line_for_offset(content, m.start()),
        })

    for m in re.finditer(
        r"^class (\w+)\(object\):\n(.*?)(?=^class |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    ):
        class_name = m.group(1)
        body = m.group(2)
        if re.search(r"^\s{4}def ", body, re.MULTILINE):
            continue
        values = parse_enum_values(body)
        if values and not class_name.startswith("_"):
            result["enums"].append({
                "name": class_name,
                "parent": None,
                "values": values,
                "source_line": line_for_offset(content, m.start()),
            })

    all_class_blocks = list(
        re.finditer(
            r"^class (\w+)\(([^)]*)\):\n(.*?)(?=^class |\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
    )

    for m in all_class_blocks:
        class_name = m.group(1)
        parent = m.group(2)
        body = m.group(3)
        class_line = line_for_offset(content, m.start())
        result["enums"].extend(parse_nested_enum_classes(body, class_name, class_line))

        if parent == "object" and not re.search(r"^\s{4}def ", body, re.MULTILINE):
            if re.search(r"^\s{4}\w+(?::\s*ClassVar\[int\])?\s*=", body, re.MULTILINE):
                continue

        body_start_line = class_line + 1
        methods = parse_method_defs(body, body_start_line)
        if parent == "obj" or class_name == "obj":
            result["widgets"].append({
                "name": class_name,
                "parent": parent if parent != "obj" else "object",
                "method_count": len(methods),
                "methods": methods,
                "source_line": class_line,
            })
        elif methods:
            result["data_classes"].append({
                "name": class_name,
                "parent": parent,
                "method_count": len(methods),
                "methods": methods,
                "source_line": class_line,
            })

    enum_names = {enum["name"] for enum in result["enums"]}
    for alias in result["type_aliases"]:
        if alias["name"] in TYPE_ALIAS_RUNTIME_ENUM_OVERRIDES:
            candidate = TYPE_ALIAS_RUNTIME_ENUM_OVERRIDES[alias["name"]]
            alias["runtime_enum"] = candidate if candidate in enum_names else None
        elif alias["name"].endswith("_t"):
            candidate = alias["name"][:-2].upper()
            if candidate in enum_names:
                alias["runtime_enum"] = candidate
            else:
                alias["runtime_enum"] = None

    for m in re.finditer(
        r"^def (\w+)\((.*?)\)(?:\s*->\s*([^:\n]+))?\s*:",
        content,
        re.MULTILINE,
    ):
        params = m.group(2).strip()
        returns = m.group(3).strip() if m.group(3) else None
        result["functions"].append({
            "name": m.group(1),
            "params": params,
            "returns": returns,
            "signature": f"{m.group(1)}({params})" + (f" -> {returns}" if returns else ""),
            "source_line": line_for_offset(content, m.start()),
        })

    return result


def build_symbols(api: dict) -> list[dict]:
    symbols = []
    source_path = api["source"]["path"]
    for enum in api["enums"]:
        enum_fqname = f"lv.{enum['name']}"
        symbols.append({
            "kind": "enum",
            "name": enum["name"],
            "fqname": enum_fqname,
            "module": "lvgl",
            "parent": f"lv.{enum['parent']}" if enum.get("parent") else None,
            "signature": enum["name"],
            "params": [],
            "returns": None,
            "description": None,
            "description_source": None,
            "notes": [],
            "examples": [],
            "source_path": source_path,
            "source_line": enum.get("source_line"),
            "availability": ["lvgl_binding"],
            "aliases": [],
            "deprecated": False,
            "values": enum["values"],
        })
        if isinstance(enum["values"], dict):
            for member_name, member_value in enum["values"].items():
                symbols.append({
                    "kind": "enum_member",
                    "name": member_name,
                    "fqname": f"{enum_fqname}.{member_name}",
                    "module": "lvgl",
                    "parent": enum_fqname,
                    "signature": f"{enum['name']}.{member_name}",
                    "params": [],
                    "returns": "int",
                    "description": None,
                    "description_source": None,
                    "notes": [],
                    "examples": [],
                    "source_path": source_path,
                    "source_line": enum.get("source_line"),
                    "availability": ["lvgl_binding"],
                    "aliases": [],
                    "deprecated": False,
                    "value": member_value,
                })
    for group_name, kind in [("data_classes", "data_class"), ("widgets", "widget")]:
        for cls in api[group_name]:
            class_fqname = f"lv.{cls['name']}"
            symbols.append({
                "kind": kind,
                "name": cls["name"],
                "fqname": class_fqname,
                "module": "lvgl",
                "parent": None,
                "signature": cls["name"],
                "params": [],
                "returns": None,
                "description": None,
                "description_source": None,
                "notes": [f"parent: {cls.get('parent', '')}"] if cls.get("parent") else [],
                "examples": [],
                "source_path": source_path,
                "source_line": cls.get("source_line"),
                "availability": ["lvgl_binding"],
                "aliases": [],
                "deprecated": False,
            })
            for method in cls["methods"]:
                symbols.append({
                    "kind": "method",
                    "name": method["name"],
                    "fqname": f"{class_fqname}.{method['name']}",
                    "module": "lvgl",
                    "parent": class_fqname,
                    "signature": method["signature"],
                    "params": [p.strip() for p in method["params"].split(",") if p.strip()],
                    "returns": method["returns"],
                    "description": None,
                    "description_source": None,
                    "notes": [],
                    "examples": [],
                    "source_path": source_path,
                    "source_line": method.get("source_line"),
                    "availability": ["lvgl_binding"],
                    "aliases": [],
                    "deprecated": False,
                })
    for fun in api["functions"]:
        symbols.append({
            "kind": "function",
            "name": fun["name"],
            "fqname": f"lv.{fun['name']}",
            "module": "lvgl",
            "parent": None,
            "signature": fun["signature"],
            "params": [p.strip() for p in fun["params"].split(",") if p.strip()],
            "returns": fun["returns"],
            "description": None,
            "description_source": None,
            "notes": [],
            "examples": [],
            "source_path": source_path,
            "source_line": fun.get("source_line"),
            "availability": ["lvgl_binding"],
            "aliases": [],
            "deprecated": False,
        })
    return symbols


def attach_metadata(api: dict, lvgl_mpy_root: str) -> dict:
    symbols = build_symbols(api)
    counts = {
        "type_aliases": len(api["type_aliases"]),
        "enums": len(api["enums"]),
        "enum_members": sum(len(e["values"]) for e in api["enums"] if isinstance(e["values"], dict)),
        "data_classes": len(api["data_classes"]),
        "data_class_methods": sum(s["method_count"] for s in api["data_classes"]),
        "widgets": len(api["widgets"]),
        "widget_methods": sum(w["method_count"] for w in api["widgets"]),
        "functions": len(api["functions"]),
        "symbols": len(symbols),
    }
    api["source"]["lvgl_micropython_root"] = os.path.abspath(lvgl_mpy_root)
    api["generated_at"] = utc_now()
    api["generator"] = GENERATOR
    api["counts"] = counts
    api["symbols"] = symbols
    return api


def md_escape(text: object) -> str:
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ")


def generate_markdown(api: dict) -> str:
    lines: list[str] = []
    lines.append("# LVGL MicroPython API Reference")
    lines.append("")
    lines.append(f"> Auto-generated by `{api['generator']}` at `{api['generated_at']}`.")
    lines.append("")
    lines.append("本文件从 `lvgl.pyi` 提取 MicroPython 可见的 LVGL binding API。机器可读版本见 `lvgl_api_summary.json`。")
    lines.append("注意：`*_t = int` 是 stub 里的类型别名，不是用户代码应直接调用的枚举值；实际枚举值使用 `lv.EVENT.CLICKED`、`lv.GRAD_DIR.VER`、`lv.DISPLAY_RENDER_MODE.PARTIAL` 这类 class member。")
    lines.append("")
    lines.append(f"- Source: `{api['source']['path']}`")
    lines.append(f"- SHA256: `{api['source']['sha256']}`")
    lines.append("")
    lines.append("## 目录")
    lines.append("")
    lines.append("1. [统计](#1-统计)")
    lines.append("2. [Enums](#2-enums)")
    lines.append("3. [Widget Classes](#3-widget-classes)")
    lines.append("4. [Data/Object Classes](#4-dataobject-classes)")
    lines.append("5. [Standalone Functions](#5-standalone-functions)")
    lines.append("")
    lines.append("## 1. 统计")
    lines.append("")
    lines.append("| 项 | 数量 |")
    lines.append("|---|---:|")
    for key in [
        "type_aliases", "enums", "enum_members", "widgets", "widget_methods",
        "data_classes", "data_class_methods", "functions", "symbols",
    ]:
        lines.append(f"| `{key}` | {api['counts'][key]} |")
    lines.append("")

    lines.append("## 2. Enums")
    lines.append("")
    lines.append("| 名称 | 成员 |")
    lines.append("|---|---|")
    for enum in api["enums"]:
        values = enum["values"]
        if isinstance(values, dict):
            sample = ", ".join(list(values.keys())[:12])
            suffix = "..." if len(values) > 12 else ""
            value_text = f"{len(values)} members: {sample}{suffix}"
        else:
            value_text = values
        lines.append(f"| `lv.{enum['name']}` | {md_escape(value_text)} |")
    lines.append("")

    lines.append("### Type Aliases")
    lines.append("")
    lines.append("这些名字来自 stub 类型标注，不按 API 入口使用。`实际枚举 class` 为空表示没有唯一运行时枚举映射，或该别名本身不是枚举入口。")
    lines.append("")
    lines.append("| 名称 | 目标类型 | 实际枚举 class |")
    lines.append("|---|---|---|")
    for alias in sorted(api["type_aliases"], key=lambda x: x["name"]):
        runtime_enum = f"`lv.{alias['runtime_enum']}`" if alias.get("runtime_enum") else ""
        lines.append(f"| `{alias['name']}` | `{alias['target']}` | {runtime_enum} |")
    lines.append("")

    lines.append("## 3. Widget Classes")
    lines.append("")
    for widget in sorted(api["widgets"], key=lambda x: x["name"]):
        parent = widget.get("parent") or "object"
        lines.append(f"### `lv.{widget['name']}`")
        lines.append("")
        lines.append(f"- Parent: `{parent}`")
        lines.append(f"- Methods: {widget['method_count']}")
        if widget["methods"]:
            lines.append("")
            for method in widget["methods"]:
                lines.append(f"- `{method['signature']}`")
        lines.append("")

    lines.append("## 4. Data/Object Classes")
    lines.append("")
    for data_class in sorted(api["data_classes"], key=lambda x: x["name"]):
        parent = data_class.get("parent") or "object"
        lines.append(f"### `lv.{data_class['name']}`")
        lines.append("")
        lines.append(f"- Parent: `{parent}`")
        lines.append(f"- Methods: {data_class['method_count']}")
        if data_class["methods"]:
            lines.append("")
            for method in data_class["methods"]:
                lines.append(f"- `{method['signature']}`")
        lines.append("")

    lines.append("## 5. Standalone Functions")
    lines.append("")
    lines.append("| 函数 | 返回 |")
    lines.append("|---|---|")
    for fun in sorted(api["functions"], key=lambda x: x["name"]):
        lines.append(f"| `lv.{fun['signature']}` | `{md_escape(fun.get('returns'))}` |")
    lines.append("")
    return "\n".join(lines) + "\n"


def print_summary(api: dict) -> None:
    print(f"\n{'=' * 60}")
    print("  LVGL Python API Summary")
    print(f"{'=' * 60}")
    print(f"  Type aliases:   {api['counts']['type_aliases']}")
    print(f"  Enum types:     {api['counts']['enums']}")
    print(f"  Enum members:   {api['counts']['enum_members']}")
    print(f"  Data classes:   {api['counts']['data_classes']} ({api['counts']['data_class_methods']} methods)")
    print(f"  Widget classes: {api['counts']['widgets']} ({api['counts']['widget_methods']} methods)")
    print(f"  Standalone fns: {api['counts']['functions']}")
    print(f"  Symbols:        {api['counts']['symbols']}")
    print()

    print("  --- Widget Classes ---")
    for w in sorted(api["widgets"], key=lambda x: x["method_count"], reverse=True):
        suffix = " (base)" if w["name"] == "obj" else ""
        print(f"  lv.{w['name']}{suffix}: {w['method_count']} methods")

    print("\n  --- Key Enums ---")
    for e in api["enums"]:
        if isinstance(e["values"], dict) and len(e["values"]) > 3:
            sample = ", ".join(list(e["values"].keys())[:6])
            print(f"  lv.{e['name']}: {len(e['values'])} members ({sample}...)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract LVGL Python API from MicroPythonOS lvgl_micropython"
    )
    parser.add_argument("--lvgl-micropython-dir", default=None, help="Path to lvgl_micropython directory")
    parser.add_argument("--from-build", action="store_true", help="Use existing build artifacts")
    parser.add_argument("--from-source", action="store_true", help="Parse C headers directly")
    parser.add_argument("--summary-only", action="store_true", help="Print summary and skip writing references")
    parser.add_argument("--output", default=None, help="Path to lvgl.pyi")
    args = parser.parse_args()

    lvgl_mpy_root = args.lvgl_micropython_dir or find_lvgl_micropython_root()
    print(f"LVGL micropython root: {lvgl_mpy_root}")

    pyi_path = args.output or os.path.join(lvgl_mpy_root, "lvgl.pyi")
    if args.from_build and args.from_source:
        raise ValueError("Use only one of --from-build or --from-source.")
    if args.from_build:
        print("Generating lvgl.pyi from build artifacts...")
        pyi_path = generate_from_build(lvgl_mpy_root)
    elif args.from_source:
        print("Generating lvgl.pyi from LVGL C headers...")
        pyi_path = generate_from_source(lvgl_mpy_root)
    elif not os.path.exists(pyi_path):
        raise FileNotFoundError(
            f"MicroPython API stub not found: {pyi_path}. "
            "Build lvgl_micropython first, or pass --from-build/--from-source explicitly."
        )

    print(f"Using MicroPython API stub: {pyi_path}")
    print("Parsing .pyi for API summary...")
    api = attach_metadata(parse_pyi(pyi_path), lvgl_mpy_root)
    print_summary(api)

    if args.summary_only:
        return

    reference_dir = Path(__file__).resolve().parent.parent / "reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    json_path = reference_dir / "lvgl_api_summary.json"
    md_path = reference_dir / "lvgl-api-reference.md"

    json_path.write_text(json.dumps(api, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(generate_markdown(api), encoding="utf-8")

    print(f"\nStructured API written to: {json_path}")
    print(f"Markdown API reference written to: {md_path}")


if __name__ == "__main__":
    main()
