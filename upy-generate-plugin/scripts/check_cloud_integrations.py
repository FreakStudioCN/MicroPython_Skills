#!/usr/bin/env python3
"""Validate cloud/API integration metadata and secret hygiene."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "knowledge" / "cloud_service_catalog.json"
SECRET_NAME_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization|access[_-]?key)", re.IGNORECASE)
PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "change_me",
    "replace_me",
    "your_api_key",
    "your-token",
    "your_token",
    "placeholder",
    "none",
    "null",
}
ALLOWED_CREDENTIAL_STATUS = {"ready", "deferred_to_deploy", "mock_only", "not_required", "blocked"}
DEPLOY_READY_STATUS = {"ready", "deferred_to_deploy", "not_required"}
CLOUD_TRIGGER_RE = re.compile(
    r"(ASR|TTS|LLM|cloud|cloud_http|MQTT|IoT|webhook|speech|voice|urequests|http_post|CLOUD_[A-Z0-9_]+_URL)",
    re.IGNORECASE,
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_catalog() -> dict[str, dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return {}
    data = load_json(CATALOG_PATH)
    providers = data.get("providers", []) if isinstance(data, dict) else []
    return {item.get("id"): item for item in providers if isinstance(item, dict) and item.get("id")}


def load_manifest(project_dir: Path, manifest_path: str = "") -> dict[str, Any]:
    path = Path(manifest_path) if manifest_path else project_dir / "project-manifest.json"
    if not path.exists():
        return {}
    try:
        data = load_json(path)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def rel_path(project_dir: Path, path: Path) -> str:
    return path.relative_to(project_dir).as_posix()


def is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    if normalized in PLACEHOLDER_VALUES:
        return True
    if "replace" in normalized or "your_" in normalized or "example" in normalized:
        return True
    return False


def looks_like_secret_value(value: str) -> bool:
    stripped = value.strip()
    if is_placeholder(stripped):
        return False
    if len(stripped) >= 16 and re.search(r"[A-Za-z]", stripped) and re.search(r"\d", stripped):
        return True
    if stripped.startswith(("sk-", "sk_", "AKIA", "AIza", "xoxb-", "xoxp-")):
        return True
    if "Bearer " in stripped:
        return True
    return False


def scan_python_secrets(project_dir: Path) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    roots = [
        project_dir / "firmware" / "conf.py",
        project_dir / "firmware" / "main.py",
        project_dir / "firmware" / "tasks",
        project_dir / "firmware" / "drivers",
        project_dir / "test",
    ]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(root.rglob("*.py"))
    for path in sorted(set(files)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except SyntaxError:
            continue
        rel = rel_path(project_dir, path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            target_names = []
            for target in targets:
                if isinstance(target, ast.Name):
                    target_names.append(target.id)
                elif isinstance(target, ast.Attribute):
                    target_names.append(target.attr)
            if not any(SECRET_NAME_RE.search(name) for name in target_names):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str) and looks_like_secret_value(value.value):
                errors.append(
                    {
                        "code": "CLOUD_SECRET_HARDCODED",
                        "path": rel,
                        "line": node.lineno,
                        "name": ",".join(target_names),
                        "message": "Generated code must not contain real API keys, tokens, passwords, or secrets.",
                    }
                )
    return errors


def cloud_need_evidence(project_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    if CLOUD_TRIGGER_RE.search(manifest_text):
        evidence.append({"source": "project-manifest.json", "reason": "manifest contains cloud/API/voice keywords"})
    roots = [
        project_dir / "firmware" / "conf.py",
        project_dir / "firmware" / "tasks",
        project_dir / "firmware" / "drivers",
        project_dir / "firmware" / "main.py",
    ]
    for root in roots:
        files = [root] if root.is_file() else sorted(root.rglob("*.py")) if root.is_dir() else []
        for path in files:
            rel = rel_path(project_dir, path)
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if CLOUD_TRIGGER_RE.search(line):
                    evidence.append({"source": rel, "line": lineno, "reason": line.strip()[:160]})
                    break
    return evidence


def validate_integration(
    item: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    index: int,
    deploy_next_phase: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    provider_id = item.get("provider_id") or item.get("provider")
    if not isinstance(provider_id, str) or not provider_id:
        errors.append({"code": "CLOUD_PROVIDER_ID_MISSING", "index": index, "message": "cloud integration missing provider_id"})
        provider_id = ""
    catalog_item = catalog.get(provider_id)
    if not catalog_item and provider_id != "custom_http_proxy":
        warnings.append(
            {
                "code": "CLOUD_PROVIDER_UNKNOWN",
                "index": index,
                "provider_id": provider_id,
                "message": "Provider is not in cloud_service_catalog.json; official links must be verified manually.",
            }
        )
    category = item.get("category")
    if not isinstance(category, str) or not category:
        errors.append({"code": "CLOUD_CATEGORY_MISSING", "index": index, "provider_id": provider_id, "message": "category is required"})
    services = item.get("services")
    if not isinstance(services, list) or not services:
        errors.append({"code": "CLOUD_SERVICES_MISSING", "index": index, "provider_id": provider_id, "message": "services[] is required"})
    links = item.get("official_links")
    if not isinstance(links, dict):
        links = {}
    if provider_id != "custom_http_proxy":
        if not any(links.get(key) for key in ("docs", "product")) or not links.get("console"):
            errors.append(
                {
                    "code": "CLOUD_OFFICIAL_LINKS_MISSING",
                    "index": index,
                    "provider_id": provider_id,
                    "message": "Official docs/product and console links are required before asking the user to buy/enable tokens.",
                }
            )
    credential = item.get("credential_management")
    if not isinstance(credential, dict):
        errors.append(
            {
                "code": "CLOUD_CREDENTIAL_MANAGEMENT_MISSING",
                "index": index,
                "provider_id": provider_id,
                "message": "credential_management is required for cloud integrations.",
            }
        )
        credential = {}
    requires_credentials = bool(credential.get("requires_credentials", provider_id != "custom_http_proxy"))
    status = credential.get("status")
    if requires_credentials and status not in ALLOWED_CREDENTIAL_STATUS:
        errors.append(
            {
                "code": "CLOUD_CREDENTIAL_STATUS_INVALID",
                "index": index,
                "provider_id": provider_id,
                "status": status,
                "message": "credential_management.status must record ready/deferred/mock/blocked/not_required.",
            }
        )
    secret_names = credential.get("secret_names", item.get("secret_names", []))
    if requires_credentials and not isinstance(secret_names, list):
        errors.append({"code": "CLOUD_SECRET_NAMES_INVALID", "index": index, "provider_id": provider_id, "message": "secret_names must be a list"})
    if requires_credentials and isinstance(secret_names, list) and not secret_names:
        warnings.append({"code": "CLOUD_SECRET_NAMES_MISSING", "index": index, "provider_id": provider_id, "message": "Record expected secret names for deploy prompts."})
    if status == "blocked":
        errors.append(
            {
                "code": "CLOUD_CREDENTIALS_BLOCKED",
                "index": index,
                "provider_id": provider_id,
                "message": "Cloud credentials or account setup are blocked; generate cannot be deploy-ready.",
            }
        )
    deploy_ready = bool(item.get("deploy_ready", False))
    if deploy_next_phase and requires_credentials and status not in DEPLOY_READY_STATUS:
        errors.append(
            {
                "code": "CLOUD_CREDENTIALS_REQUIRED",
                "index": index,
                "provider_id": provider_id,
                "status": status,
                "message": "Deploy next_phase requires credentials ready, deferred_to_deploy, or not_required.",
            }
        )
    if deploy_next_phase and not deploy_ready and status != "deferred_to_deploy":
        errors.append(
            {
                "code": "CLOUD_DEPLOY_NOT_READY",
                "index": index,
                "provider_id": provider_id,
                "message": "next_phase=deploy requires deploy_ready=true or an explicit deferred_to_deploy prompt.",
            }
        )
    actions = item.get("user_action_required")
    if requires_credentials and status in {"deferred_to_deploy", "mock_only", "blocked"} and not isinstance(actions, list):
        errors.append(
            {
                "code": "CLOUD_USER_ACTIONS_MISSING",
                "index": index,
                "provider_id": provider_id,
                "message": "Unresolved cloud setup must include user_action_required[].",
            }
        )
    return errors, warnings


def check_project(project_dir: Path, manifest_path: str = "", next_phase: str = "") -> dict[str, Any]:
    manifest = load_manifest(project_dir, manifest_path)
    generate = manifest.get("generate") if isinstance(manifest.get("generate"), dict) else {}
    integrations = generate.get("cloud_integrations", [])
    errors = scan_python_secrets(project_dir)
    warnings: list[dict[str, Any]] = []
    evidence = cloud_need_evidence(project_dir, manifest)
    if integrations is None:
        integrations = []
    if not isinstance(integrations, list):
        errors.append({"code": "CLOUD_INTEGRATIONS_INVALID", "message": "generate.cloud_integrations must be a list when present"})
        integrations = []
    if evidence and not integrations:
        errors.append(
            {
                "code": "CLOUD_INTEGRATIONS_REQUIRED",
                "evidence": evidence[:10],
                "message": "Cloud/API/LLM/ASR/TTS/MQTT usage requires generate.cloud_integrations[] and a user credential/setup decision.",
            }
        )
    catalog = load_catalog()
    deploy_next_phase = next_phase == "upy-deploy-plugin"
    for index, item in enumerate(integrations):
        if not isinstance(item, dict):
            errors.append({"code": "CLOUD_INTEGRATION_INVALID", "index": index, "message": "cloud integration item must be an object"})
            continue
        item_errors, item_warnings = validate_integration(item, catalog, index, deploy_next_phase)
        errors.extend(item_errors)
        warnings.extend(item_warnings)
    return {
        "check": "cloud_integrations",
        "project_dir": str(project_dir),
        "integrations_checked": len(integrations),
        "cloud_need_evidence": evidence,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Validate generated cloud/API integration metadata")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--manifest", default="", help="Optional manifest path; defaults to project-manifest.json")
    parser.add_argument("--next-phase", default="", help="Optional phase_complete next_phase for deploy readiness checks")
    args = parser.parse_args()
    result = check_project(Path(args.project_dir), args.manifest, args.next_phase)
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
