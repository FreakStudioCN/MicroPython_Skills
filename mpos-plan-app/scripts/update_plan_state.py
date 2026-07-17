#!/usr/bin/env python3
"""Discover, update, and invalidate MicroPythonOS app plan state."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FALLBACK_REPO = Path("/home/leeqingshui/MicroPythonOS")
STATE_ROOT = Path("tmp/mpos-plan-app")
SCHEMA_VERSION = "mpos-plan-app-v1"
ARTIFACT_BY_SCHEMA = {
    "mpos-analyze-v1": "analysis_result",
    "mpos-prepare-deps-v1": "dependency_handoff",
    "mpos-gen-app-v1": "generation_result",
    "mpos-test-app-v1": "app_test_result",
    "mpos-package-app-v1": "package_result",
    "mpos-deploy-app-v1": "deploy_result",
    "mpos-publish-app-v1": "publish_result",
}
ARTIFACT_KEYS = tuple(ARTIFACT_BY_SCHEMA.values())
DEFAULT_NEXT_BY_PHASE = {
    "analyze": "mpos-analyze-app",
    "prepare-deps": "mpos-prepare-deps",
    "generate": "mpos-gen-app",
    "test-app": "mpos-test-app",
    "package": "mpos-package-app",
    "deploy": "mpos-deploy-app",
    "publish": "mpos-publish-app",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_repo() -> Path:
    env_repo = os.environ.get("MPOS_REPO")
    if env_repo:
        return Path(env_repo)
    cwd = Path.cwd()
    if (cwd / "internal_filesystem" / "apps").is_dir() and (cwd / "scripts").is_dir():
        return cwd
    return FALLBACK_REPO


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def display_path(path: Path | str, repo: Path) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(repo.resolve()))
    except ValueError:
        return str(p)


def resolve_path(repo: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo / path


def state_dir(repo: Path, fullname: str) -> Path:
    return repo / STATE_ROOT / fullname


def state_path(repo: Path, fullname: str) -> Path:
    return state_dir(repo, fullname) / "plan_state.json"


def log_path(repo: Path, fullname: str) -> Path:
    return state_dir(repo, fullname) / "activity_log.jsonl"


def artifact_key_for(data: dict[str, Any]) -> str | None:
    schema = data.get("schema_version")
    if isinstance(schema, str) and schema in ARTIFACT_BY_SCHEMA:
        return ARTIFACT_BY_SCHEMA[schema]
    phase = data.get("phase")
    if phase == "analyze":
        return "analysis_result"
    if phase == "prepare-deps":
        return "dependency_handoff"
    if phase == "generate":
        return "generation_result"
    if phase == "test-app":
        return "app_test_result"
    if phase == "package":
        return "package_result"
    if phase == "deploy":
        return "deploy_result"
    if phase == "publish":
        return "publish_result"
    return None


def app_from_result(data: dict[str, Any]) -> dict[str, Any]:
    app = data.get("app") if isinstance(data.get("app"), dict) else {}
    fullname = app.get("fullname") or ""
    return {
        "fullname": fullname,
        "name": app.get("name") or fullname,
        "version": app.get("version") or "unknown",
        "app_dir": app.get("app_dir") or (f"internal_filesystem/apps/{fullname}" if fullname else ""),
    }


def default_state(fullname: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": "analyze",
        "result": "planned",
        "updated_at_utc": utc_now(),
        "app": {
            "fullname": fullname,
            "name": fullname,
            "version": "unknown",
            "app_dir": f"internal_filesystem/apps/{fullname}",
        },
        "intent": {
            "goal": "create-to-publish",
            "publish": True,
            "deploy_record_required": True,
            "deploy_record_policy": "desktop-or-web-preview-allowed",
        },
        "artifacts": {key: None for key in ARTIFACT_KEYS},
        "artifact_status": {},
        "invalidated": [],
        "pending_confirmations": [],
        "blocking_questions": [],
        "last_event": {
            "skill": "mpos-plan-app",
            "phase": "analyze",
            "result": "planned",
            "summary": "Project state initialized.",
        },
        "next_skill": "mpos-analyze-app",
        "handoff": {
            "next_skill": "mpos-analyze-app",
            "reason": "Analyze the app request before generation.",
        },
    }


def load_state(repo: Path, fullname: str) -> dict[str, Any]:
    path = state_path(repo, fullname)
    if path.is_file():
        data = load_json(path)
        if isinstance(data, dict):
            return data
    return default_state(fullname)


def save_state(repo: Path, fullname: str, state: dict[str, Any]) -> Path:
    path = state_path(repo, fullname)
    write_json(path, state)
    return path


def append_log(repo: Path, fullname: str, event: dict[str, Any]) -> None:
    path = log_path(repo, fullname)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def iter_result_json(repo: Path) -> list[tuple[float, Path, dict[str, Any]]]:
    results: list[tuple[float, Path, dict[str, Any]]] = []
    tmp = repo / "tmp"
    if not tmp.is_dir():
        return results
    for path in tmp.glob("mpos-*/*/*.json"):
        if "mpos-plan-app" in path.parts:
            continue
        try:
            data = load_json(path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        app = data.get("app")
        if not isinstance(app, dict) or not app.get("fullname"):
            continue
        results.append((path.stat().st_mtime, path, data))
    results.sort(key=lambda item: item[0], reverse=True)
    return results


def discover_fullname(repo: Path) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    seen = set()
    for mtime, path, data in iter_result_json(repo):
        app = app_from_result(data)
        fullname = app.get("fullname")
        if not fullname or fullname in seen:
            continue
        seen.add(fullname)
        candidates.append(
            {
                "fullname": fullname,
                "source": display_path(path, repo),
                "phase": data.get("phase"),
                "result": data.get("result"),
                "mtime": mtime,
            }
        )
    apps_dir = repo / "internal_filesystem" / "apps"
    if apps_dir.is_dir():
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir() or app_dir.name in seen:
                continue
            manifest = app_dir / "MANIFEST.JSON"
            legacy_manifest = app_dir / "META-INF" / "MANIFEST.JSON"
            source = manifest if manifest.is_file() else legacy_manifest
            if not source.is_file():
                continue
            candidates.append(
                {
                    "fullname": app_dir.name,
                    "source": display_path(source, repo),
                    "phase": "app-dir",
                    "result": "unknown",
                    "mtime": source.stat().st_mtime,
                }
            )
    candidates.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    selected = candidates[0]["fullname"] if candidates else None
    return {"selected_fullname": selected, "candidates": candidates[:10]}


def infer_fullname(repo: Path, args: argparse.Namespace) -> str:
    if getattr(args, "fullname", None):
        return args.fullname
    if getattr(args, "auto_fullname", False):
        discovered = discover_fullname(repo)
        selected = discovered.get("selected_fullname")
        if selected:
            return str(selected)
    raise SystemExit("ERROR: --fullname is required unless --auto-fullname can discover one")


def update_app_from_artifact(state: dict[str, Any], data: dict[str, Any]) -> None:
    app = app_from_result(data)
    current = state.setdefault("app", {})
    for key, value in app.items():
        if value and (not current.get(key) or current.get(key) == "unknown"):
            current[key] = value


def parse_artifact_arg(value: str) -> tuple[str | None, str]:
    if "=" in value:
        key, path = value.split("=", 1)
        return key.strip() or None, path.strip()
    return None, value


def record(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    fullname = infer_fullname(repo, args)
    state = load_state(repo, fullname)
    event_artifacts: dict[str, str] = {}
    artifact_status = state.setdefault("artifact_status", {})

    for artifact in args.artifact or []:
        explicit_key, path_text = parse_artifact_arg(artifact)
        path = resolve_path(repo, path_text)
        key = explicit_key
        status: dict[str, Any] = {"path": display_path(path, repo), "exists": path.is_file()}
        if path.is_file() and path.suffix.lower() == ".json":
            try:
                data = load_json(path)
            except Exception as exc:  # noqa: BLE001 - state log should record unreadable artifacts.
                status["read_error"] = str(exc)
            else:
                if isinstance(data, dict):
                    key = key or artifact_key_for(data)
                    status.update(
                        {
                            "schema_version": data.get("schema_version"),
                            "phase": data.get("phase"),
                            "result": data.get("result"),
                        }
                    )
                    update_app_from_artifact(state, data)
        if key is None:
            key = "artifact"
        if key in ARTIFACT_KEYS:
            state.setdefault("artifacts", {})[key] = display_path(path, repo)
            artifact_status[key] = status
        event_artifacts[key] = display_path(path, repo)

    phase = args.phase or state.get("phase") or "unknown"
    result = args.result or state.get("result") or "planned"
    next_skill = None if args.next_skill == "null" else args.next_skill
    if next_skill is None and args.next_skill is None:
        next_skill = DEFAULT_NEXT_BY_PHASE.get(phase)

    event = {
        "created_at_utc": utc_now(),
        "skill": args.skill,
        "phase": phase,
        "result": result,
        "summary": args.event or "",
        "artifacts": event_artifacts,
        "next_skill": next_skill,
        "reason": args.reason,
    }
    state["phase"] = phase
    state["result"] = result
    state["updated_at_utc"] = event["created_at_utc"]
    state["last_event"] = {
        "skill": args.skill,
        "phase": phase,
        "result": result,
        "summary": args.event or "",
    }
    state["next_skill"] = next_skill
    state["handoff"] = {"next_skill": next_skill, "reason": args.reason or args.event or ""}
    if args.blocking_question:
        state["blocking_questions"] = list(args.blocking_question)
    save_path = save_state(repo, fullname, state)
    append_log(repo, fullname, event)
    return {"state_path": display_path(save_path, repo), "log_path": display_path(log_path(repo, fullname), repo), "state": state}


def invalidate(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    fullname = infer_fullname(repo, args)
    state = load_state(repo, fullname)
    scopes = list(args.scope or [])
    entry = {
        "created_at_utc": utc_now(),
        "reason": args.reason,
        "scope": scopes,
        "confirmed": bool(args.confirmed),
    }
    state.setdefault("invalidated", []).append(entry)
    if args.confirmed:
        for key in scopes:
            if key in state.setdefault("artifact_status", {}):
                state["artifact_status"][key]["stale"] = True
        state["pending_confirmations"] = [
            item for item in state.get("pending_confirmations", [])
            if not (isinstance(item, dict) and item.get("type") == "invalidation" and item.get("scope") == scopes)
        ]
    else:
        state.setdefault("pending_confirmations", []).append(
            {
                "type": "invalidation",
                "scope": scopes,
                "reason": args.reason,
                "prompt": "Confirm invalidating stale artifacts before continuing.",
            }
        )
    state["updated_at_utc"] = entry["created_at_utc"]
    state["last_event"] = {
        "skill": "mpos-plan-app",
        "phase": state.get("phase", "unknown"),
        "result": "planned",
        "summary": "Invalidation confirmed." if args.confirmed else "Invalidation proposed.",
    }
    save_path = save_state(repo, fullname, state)
    append_log(
        repo,
        fullname,
        {
            "created_at_utc": entry["created_at_utc"],
            "skill": "mpos-plan-app",
            "phase": state.get("phase"),
            "result": "planned",
            "summary": state["last_event"]["summary"],
            "invalidated": entry,
        },
    )
    return {"state_path": display_path(save_path, repo), "log_path": display_path(log_path(repo, fullname), repo), "state": state}


def cmd_discover(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    result = discover_fullname(repo)
    selected = result.get("selected_fullname")
    if selected:
        result["state_path"] = display_path(state_path(repo, str(selected)), repo)
        result["log_path"] = display_path(log_path(repo, str(selected)), repo)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Discover the most recent MPOS App project")
    discover_parser.add_argument("--repo", default=str(default_repo()))

    record_parser = subparsers.add_parser("record", help="Record a skill event and update plan_state.json")
    record_parser.add_argument("--repo", default=str(default_repo()))
    record_parser.add_argument("--fullname")
    record_parser.add_argument("--auto-fullname", action="store_true")
    record_parser.add_argument("--skill", required=True)
    record_parser.add_argument("--phase")
    record_parser.add_argument("--result")
    record_parser.add_argument("--artifact", action="append", help="Artifact as kind=path or path")
    record_parser.add_argument("--next-skill")
    record_parser.add_argument("--reason")
    record_parser.add_argument("--event")
    record_parser.add_argument("--blocking-question", action="append")

    invalidate_parser = subparsers.add_parser("invalidate", help="Record proposed or confirmed artifact invalidation")
    invalidate_parser.add_argument("--repo", default=str(default_repo()))
    invalidate_parser.add_argument("--fullname")
    invalidate_parser.add_argument("--auto-fullname", action="store_true")
    invalidate_parser.add_argument("--reason", required=True)
    invalidate_parser.add_argument("--scope", action="append", required=True)
    invalidate_parser.add_argument("--confirmed", action="store_true")

    args = parser.parse_args()
    if args.command == "discover":
        result = cmd_discover(args)
    elif args.command == "record":
        result = record(args)
    elif args.command == "invalidate":
        result = invalidate(args)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
