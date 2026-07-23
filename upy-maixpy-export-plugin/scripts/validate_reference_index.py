#!/usr/bin/env python3
"""Validate the local MaixPy reference index for upy-maixpy-export-plugin."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


VALID_STATUSES = {"seed_reference", "needs_full_crawl", "not_codegen_ready"}
REQUIRED_ROOT_FILES = [
    "SKILL.md",
    ".codex-plugin/plugin.json",
    "references/official_links.json",
    "references/sipeed_source_index.json",
    "references/maixpy_api_index.md",
    "references/maixpy_api_module_index.md",
    "references/maixpy_api_crawl_manifest.json",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_module_index(path: Path) -> dict[str, str]:
    modules: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("| `maix."):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        module = cells[0].strip("`")
        local_reference = cells[2].strip("`")
        modules[module] = local_reference
    return modules


def parse_task_examples(path: Path) -> set[str]:
    examples: set[str] = set()
    pattern = re.compile(r"`(examples/[^`]+\.py)`")
    for match in pattern.finditer(read_text(path)):
        examples.add(match.group(1))
    return examples


def validate(skill_root: Path) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_ROOT_FILES:
        if not (skill_root / rel).exists():
            errors.append(f"missing required file: {rel}")

    module_index_path = skill_root / "references/maixpy_api_module_index.md"
    manifest_path = skill_root / "references/maixpy_api_crawl_manifest.json"
    task_index_path = skill_root / "references/maixpy_api_index.md"

    module_paths: dict[str, str] = {}
    if module_index_path.exists():
        module_paths = parse_module_index(module_index_path)
        if not module_paths:
            errors.append("maixpy_api_module_index.md has no module rows")
        for module, rel in module_paths.items():
            if not (skill_root / rel).exists():
                errors.append(f"module {module} local reference missing: {rel}")

    manifest_modules: dict[str, dict[str, object]] = {}
    if manifest_path.exists():
        try:
            data = json.loads(read_text(manifest_path))
            for item in data.get("modules", []):
                module = str(item.get("module", ""))
                status = str(item.get("status", ""))
                local_reference = str(item.get("local_reference", ""))
                if not module:
                    errors.append("manifest contains module entry without module")
                    continue
                manifest_modules[module] = item
                if status not in VALID_STATUSES:
                    errors.append(f"manifest module {module} has invalid status: {status}")
                if local_reference and not (skill_root / local_reference).exists():
                    errors.append(f"manifest module {module} local reference missing: {local_reference}")
        except json.JSONDecodeError as exc:
            errors.append(f"invalid maixpy_api_crawl_manifest.json: {exc}")

    if module_paths and manifest_modules:
        missing_in_manifest = sorted(set(module_paths) - set(manifest_modules))
        missing_in_index = sorted(set(manifest_modules) - set(module_paths))
        if missing_in_manifest:
            errors.append("modules missing from manifest: " + ", ".join(missing_in_manifest))
        if missing_in_index:
            errors.append("modules missing from module index: " + ", ".join(missing_in_index))

    if task_index_path.exists():
        for rel in sorted(parse_task_examples(task_index_path)):
            if not (skill_root / rel).exists():
                errors.append(f"task example missing: {rel}")

    needs_full_crawl = sorted(
        module
        for module, item in manifest_modules.items()
        if item.get("status") == "needs_full_crawl"
    )
    not_codegen_ready = sorted(
        module
        for module, item in manifest_modules.items()
        if item.get("status") == "not_codegen_ready"
    )
    if needs_full_crawl:
        warnings.append("modules still marked needs_full_crawl: " + ", ".join(needs_full_crawl))
    if not_codegen_ready:
        warnings.append("modules intentionally not codegen-ready: " + ", ".join(not_codegen_ready))

    summary = {
        "skill_root": str(skill_root),
        "module_count": len(module_paths),
        "manifest_module_count": len(manifest_modules),
        "needs_full_crawl_count": len(needs_full_crawl),
        "not_codegen_ready_count": len(not_codegen_ready),
        "warnings": warnings,
        "errors": errors,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    skill_root = Path(args.skill_root).resolve()
    errors, summary = validate(skill_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
