#!/usr/bin/env python3
"""Check official MicroPython documentation evidence for hardware APIs."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "knowledge" / "micropython_official_library_index.json"
HARDWARE_MODULES = {
    "bluetooth",
    "dht",
    "esp",
    "esp32",
    "framebuf",
    "machine",
    "neopixel",
    "network",
    "onewire",
    "rp2",
}
MACHINE_CLASSES = {
    "ADC",
    "ADCBlock",
    "CAN",
    "DAC",
    "I2C",
    "I2S",
    "Pin",
    "PWM",
    "RTC",
    "SD",
    "SPI",
    "Signal",
    "SoftI2C",
    "SoftSPI",
    "Timer",
    "UART",
    "WDT",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_manifest(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "project-manifest.json"
    if not path.exists():
        return {}
    try:
        data = load_json(path)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def generate_section(manifest: dict[str, Any]) -> dict[str, Any]:
    generate = manifest.get("generate")
    return generate if isinstance(generate, dict) else {}


def doc_evidence(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    generate = generate_section(manifest)
    raw = generate.get("doc_evidence")
    if raw is None:
        raw = generate.get("official_doc_evidence")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def library_index() -> dict[str, dict[str, Any]]:
    try:
        data = load_json(INDEX_PATH)
    except (OSError, json.JSONDecodeError):
        return {}
    pages = data.get("pages") if isinstance(data, dict) else []
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(pages, list):
        return index
    for page in pages:
        if not isinstance(page, dict):
            continue
        module = str(page.get("module") or "")
        if module:
            index[module] = page
    return index


def indexed_urls(index: dict[str, dict[str, Any]]) -> set[str]:
    urls: set[str] = set()
    for page in index.values():
        url = page.get("url")
        if isinstance(url, str):
            urls.add(url.split("#", 1)[0])
        links = page.get("content_links")
        if isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and isinstance(link.get("url"), str):
                    urls.add(link["url"].split("#", 1)[0])
    return urls


def project_py_files(project_dir: Path) -> list[Path]:
    roots = [
        project_dir / "firmware" / "main.py",
        project_dir / "firmware" / "board.py",
        project_dir / "firmware" / "lib" / "scheduler",
        project_dir / "firmware" / "drivers",
        project_dir / "firmware" / "tasks",
    ]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(root.rglob("*.py"))
    return sorted(set(files))


def full_attr_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = full_attr_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def required_docs_for_file(project_dir: Path, path: Path) -> list[dict[str, Any]]:
    rel = path.relative_to(project_dir).as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError:
        return []
    requirements: list[dict[str, Any]] = []
    imported_machine_names: set[str] = set()
    machine_aliases: set[str] = {"machine"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in HARDWARE_MODULES:
                    module = root
                    asname = alias.asname or root
                    if root == "machine":
                        machine_aliases.add(asname)
                    requirements.append({"module": module, "path": rel, "line": node.lineno, "reason": f"imports {alias.name}"})
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in HARDWARE_MODULES:
                requirements.append({"module": root, "path": rel, "line": node.lineno, "reason": f"imports from {node.module}"})
            if node.module == "machine":
                for alias in node.names:
                    imported_machine_names.add(alias.asname or alias.name)
                    if alias.name in MACHINE_CLASSES:
                        requirements.append(
                            {
                                "module": f"machine.{alias.name}",
                                "path": rel,
                                "line": node.lineno,
                                "reason": f"imports machine.{alias.name}",
                            }
                        )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = full_attr_name(node.func)
        parts = name.split(".")
        if len(parts) >= 2 and parts[0] in machine_aliases and parts[1] in MACHINE_CLASSES:
            requirements.append(
                {
                    "module": f"machine.{parts[1]}",
                    "path": rel,
                    "line": getattr(node, "lineno", None),
                    "reason": f"calls {name}",
                }
            )
        elif parts and parts[0] in imported_machine_names:
            class_name = parts[0]
            if class_name in MACHINE_CLASSES:
                requirements.append(
                    {
                        "module": f"machine.{class_name}",
                        "path": rel,
                        "line": getattr(node, "lineno", None),
                        "reason": f"calls imported machine.{class_name}",
                    }
                )
    return requirements


def required_docs(project_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | None]] = set()
    for path in project_py_files(project_dir):
        for item in required_docs_for_file(project_dir, path):
            key = (item["module"], item["path"], item.get("line"))
            if key in seen:
                continue
            seen.add(key)
            records.append(item)
    return records


def parent_module(module: str) -> str:
    return module.split(".", 1)[0]


def evidence_matches(entry: dict[str, Any], module: str, valid_urls: set[str]) -> bool:
    entry_module = str(entry.get("module") or entry.get("api") or "")
    url = str(entry.get("url") or entry.get("docs") or "")
    url_base = url.split("#", 1)[0]
    if not url.startswith("https://docs.micropython.org/en/latest/"):
        return False
    if url_base not in valid_urls:
        return False
    if entry_module == module:
        return True
    if module.startswith("machine."):
        return False
    if entry_module == parent_module(module):
        return True
    return False


def check(project_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(project_dir)
    evidence = doc_evidence(manifest)
    required = required_docs(project_dir)
    index = library_index()
    valid_urls = indexed_urls(index)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for item in required:
        module = item["module"]
        if not any(evidence_matches(entry, module, valid_urls) for entry in evidence):
            errors.append(
                {
                    "code": "DOC_EVIDENCE_MISSING",
                    "module": module,
                    "path": item["path"],
                    "line": item.get("line"),
                    "reason": item.get("reason"),
                    "message": "hardware/peripheral MicroPython API usage must cite official MicroPython docs in generate.doc_evidence",
                }
            )
        page = index.get(module) or index.get(parent_module(module))
        if isinstance(page, dict) and page.get("has_real_content") is False:
            warnings.append(
                {
                    "code": "DOC_EVIDENCE_PAGE_MINIMAL",
                    "module": module,
                    "message": "official MicroPython page has little MicroPython-specific content; use extra port docs or mark partial if behavior is uncertain",
                }
            )
    for entry in evidence:
        url = str(entry.get("url") or entry.get("docs") or "")
        url_base = url.split("#", 1)[0]
        if url and (not url.startswith("https://docs.micropython.org/en/latest/") or url_base not in valid_urls):
            errors.append(
                {
                    "code": "DOC_EVIDENCE_URL_INVALID",
                    "url": url,
                    "message": "doc evidence must reference a fetched official MicroPython library page or linked official page",
                }
            )
    return {
        "check": "doc_evidence",
        "project_dir": str(project_dir),
        "required": required,
        "evidence": evidence,
        "index_path": str(INDEX_PATH),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    result = check(Path(args.project_dir))
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
