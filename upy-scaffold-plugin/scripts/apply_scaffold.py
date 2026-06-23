#!/usr/bin/env python3
"""Apply scaffold file_operations and finalize upy-scaffold-plugin output.

This host-side runner keeps init_scaffold.py side-effect free, applies the
emitted file operations under the project root, runs the scaffold flake8 gate,
and writes the final phase_complete message when requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SCRIPT = ROOT / "scripts" / "init_scaffold.py"
SELECT_HW_SAMPLE = REPO / "upy-select-hw-plugin" / "sample" / "phase_complete.select_hw.success.json"


def utc_now() -> str:
    helper = REPO / "upy-project-gen-toolchain-spec" / "scripts" / "workflow_time.py"
    if helper.exists():
        result = subprocess.run(
            [sys.executable, str(helper), "--json"],
            text=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)["utc"]
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def extract_manifest(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.get("payload")
    if isinstance(payload, dict):
        manifest_content = payload.get("manifest_content")
        if isinstance(manifest_content, dict):
            return manifest_content
        manifest = payload.get("manifest")
        if isinstance(manifest, dict):
            return manifest
    manifest_content = data.get("manifest_content")
    if isinstance(manifest_content, dict):
        return manifest_content
    manifest = data.get("manifest")
    if isinstance(manifest, dict):
        return manifest
    return data


def load_manifest(path: Path) -> dict[str, Any]:
    return extract_manifest(load_json(path))


def run_renderer(
    mode: str,
    manifest: dict[str, Any],
    modules: str,
    custom_files: str,
    new_devices: str,
    fixed_utc: str | None = None,
) -> dict[str, Any]:
    cmd = [sys.executable, str(SCRIPT), "--mode", mode, "--manifest", "-"]
    if modules:
        cmd.extend(["--modules", modules])
    if custom_files:
        cmd.extend(["--custom-files", custom_files])
    if mode == "incremental":
        cmd.extend(["--new-devices", new_devices])
    env = None
    if fixed_utc:
        import os

        env = os.environ.copy()
        env["UPY_WORKFLOW_UTC_NOW"] = fixed_utc
    result = subprocess.run(
        cmd,
        input=json.dumps(manifest, ensure_ascii=False),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"renderer failed ({result.returncode}):\n{result.stderr}")
    return json.loads(result.stdout)


def validate_relative_posix_path(path: str) -> None:
    if not path or path.startswith("/") or "\\" in path:
        raise ValueError(f"path must be relative POSIX style: {path}")
    if len(path) >= 2 and path[1] == ":":
        raise ValueError(f"path must not contain a drive prefix: {path}")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError(f"path must not contain empty, '.', or '..' parts: {path}")


def target_path(project_dir: Path, rel_path: str) -> Path:
    validate_relative_posix_path(rel_path)
    root = project_dir.resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes project directory: {rel_path}")
    return target


def sha256_text(value: str, encoding: str) -> str:
    return hashlib.sha256(value.encode(encoding)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def apply_file_operations(
    project_dir: Path,
    output: dict[str, Any],
    *,
    force: bool,
    dry_run: bool,
) -> list[dict[str, Any]]:
    files_by_path = {item["path"]: item for item in output.get("files", [])}
    operations = output.get("file_operations", [])
    if len(files_by_path) != len(operations):
        raise AssertionError("files[] and file_operations[] length mismatch")

    manifest: list[dict[str, Any]] = []
    for operation in operations:
        if operation.get("type") != "file_operation":
            raise AssertionError(f"unsupported operation type: {operation}")
        payload = operation.get("payload", {})
        if payload.get("op") != "write":
            raise AssertionError(f"unsupported file operation: {payload}")
        rel_path = payload.get("path", "")
        if rel_path not in files_by_path:
            raise AssertionError(f"file operation path missing from files[]: {rel_path}")
        target = target_path(project_dir, rel_path)
        content = strip_bom(payload.get("content", ""))
        encoding = payload.get("encoding", "utf-8")
        desired_hash = sha256_text(content, encoding)
        before_hash = sha256_file(target) if target.exists() else None
        status = "created"
        reason = None
        if target.exists():
            if before_hash == desired_hash:
                status = "unchanged"
            elif force:
                status = "updated"
            else:
                status = "skipped"
                reason = "conflict_existing_file"

        if not dry_run and status in {"created", "updated"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding=encoding, newline="\n") as handle:
                handle.write(content)
        elif not dry_run and status == "unchanged":
            target.parent.mkdir(parents=True, exist_ok=True)

        manifest.append(
            {
                "path": rel_path,
                "status": status,
                "encoding": encoding,
                "bytes": len(content.encode(encoding)),
                "sha256": desired_hash if status != "skipped" else before_hash,
                "sha256_before": before_hash,
                "sha256_after": desired_hash if status in {"created", "updated", "unchanged"} else before_hash,
                "overwrite": bool(force and status == "updated"),
                "reason": reason,
            }
        )
    return manifest


def run_flake8(project_dir: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "flake8", "--jobs=1", "firmware", "tools"],
        cwd=project_dir,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": "python -m flake8 --jobs=1 firmware tools",
        "cwd": str(project_dir),
        "config": ".flake8",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def assert_required_outputs(project_dir: Path) -> None:
    required = [
        "project-manifest.json",
        "docs/.gitkeep",
        ".flake8",
        ".upy/schemas/project-manifest.schema.json",
        ".upy/scripts/validate_json.py",
        ".upy/scripts/init_scaffold.py",
        "firmware/main.py",
    ]
    missing = [path for path in required if not (project_dir / path).exists()]
    if missing:
        raise AssertionError(f"local actual project missing required files: {missing}")


def resolve_project_dir(args: argparse.Namespace) -> tuple[Path, Path | None, bool]:
    if args.project_dir:
        return Path(args.project_dir).resolve(), Path(args.session_dir).resolve() if args.session_dir else None, False
    if args.session_dir:
        session_dir = Path(args.session_dir).resolve()
        return (session_dir / "project").resolve(), session_dir, False
    return Path(tempfile.mkdtemp(prefix="upy_scaffold_actual_")).resolve(), None, True


def existing_project_updated_at(project_dir: Path) -> str | None:
    manifest_path = project_dir / "project-manifest.json"
    if not manifest_path.exists():
        return None
    try:
        data = load_json(manifest_path)
    except Exception:
        return None
    value = data.get("updated_at")
    return value if isinstance(value, str) and value else None


def relative_artifact_path(path: Path, artifact_root: Path | None) -> str:
    if artifact_root is not None:
        try:
            return path.resolve().relative_to(artifact_root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def protocol_source_path(path: Path, artifact_root: Path | None) -> str:
    if artifact_root is not None:
        try:
            return path.resolve().relative_to(artifact_root.resolve()).as_posix()
        except ValueError:
            pass
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return path.name


def protocol_artifact_root(artifact_root: Path | None) -> str:
    return "." if artifact_root else ""


def protocol_artifact_root_mode(artifact_root: Path | None) -> str:
    if artifact_root is None:
        return "local"
    try:
        if Path.cwd().resolve() == artifact_root.resolve():
            return "cwd"
    except OSError:
        pass
    return "session_parent"


def source_manifest_kind(source_data: dict[str, Any]) -> str:
    payload = source_data.get("payload")
    if source_data.get("type") == "phase_complete" or isinstance(payload, dict):
        return "phase_complete"
    if "manifest_content" in source_data:
        return "manifest_content_envelope"
    if "manifest" in source_data:
        return "manifest_envelope"
    return "manifest_content"


def source_phase(source_data: dict[str, Any], source_path: Path) -> str:
    payload = source_data.get("payload") if isinstance(source_data.get("payload"), dict) else {}
    for candidate in (
        source_data.get("phase"),
        payload.get("phase"),
        payload.get("source_phase"),
        extract_manifest(source_data).get("phase"),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    name = source_path.name
    if "upy_flash_mpy_firmware_plugin" in name:
        return "upy-flash-mpy-firmware-plugin"
    if "select_hw" in name or "select-hw" in name:
        return "select-hw"
    return "direct_manifest_input"


def build_file_manifest(project_dir: Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "file_manifest",
        "title": "Scaffold file manifest",
        "root": str(project_dir),
        "generated_at": utc_now(),
        "files": entries,
    }


def build_final_artifacts(draft_artifacts: list[dict[str, Any]], file_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for artifact in draft_artifacts:
        artifact_type = artifact.get("type")
        if artifact_type == "file_list":
            artifacts.append(
                {
                    "type": "file_list",
                    "title": "Scaffold 写入结果",
                    "files": [
                        {
                            "path": item["path"],
                            "status": item["status"],
                            "encoding": item.get("encoding", "utf-8"),
                            "bytes": item.get("bytes"),
                            "sha256": item.get("sha256"),
                        }
                        for item in file_manifest.get("files", [])
                    ],
                }
            )
        else:
            artifacts.append(deepcopy(artifact))
    artifacts.append(deepcopy(file_manifest))
    return artifacts


def parse_json_or_csv(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [item.strip() for item in text.split(",") if item.strip()]
    return parsed if isinstance(parsed, list) else [parsed]


def build_phase_complete(
    args: argparse.Namespace,
    source_data: dict[str, Any],
    output: dict[str, Any],
    project_dir: Path,
    session_dir: Path | None,
    file_manifest: dict[str, Any],
    lint: dict[str, Any] | None,
    result: str,
    structured_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    timestamp = utc_now()
    session_id = session_dir.name if session_dir else "local-actual"
    source_path = Path(args.manifest).resolve()
    artifact_root = session_dir.parent.parent if session_dir and session_dir.parent.name == "sessions" else session_dir
    phase_payload = output["phase_complete_payload"]
    project_artifact_path = relative_artifact_path(project_dir, artifact_root) if artifact_root else str(project_dir)
    file_manifest["title"] = "Scaffold 写入结果"
    file_manifest["root"] = project_artifact_path
    if session_dir:
        file_manifest["path"] = relative_artifact_path(session_dir / "scaffold_file_manifest.json", artifact_root)
    artifacts = build_final_artifacts(list(phase_payload.get("artifacts", [])), file_manifest)
    lint_payload = deepcopy(lint) if lint else None
    if lint_payload:
        lint_payload["cwd"] = project_artifact_path
    source_payload = {
        "source_phase": source_phase(source_data, source_path),
        "source_phase_complete_path": protocol_source_path(source_path, artifact_root),
        "source_manifest_kind": source_manifest_kind(source_data),
        "manifest_merge_strategy": "renderer_unwrap_manifest",
    }
    runtime_context = {
        "artifact_root": protocol_artifact_root(artifact_root),
        "artifact_root_mode": protocol_artifact_root_mode(artifact_root),
        "session_root": relative_artifact_path(session_dir, artifact_root) if session_dir else "",
        "project_root": project_artifact_path,
        "file_operation_root": project_artifact_path,
        "resource_root": ROOT.name,
    }
    permissions = [
        {
            "type": "file_operation",
            "root": project_artifact_path,
            "operation": "write",
            "file_count": len(file_manifest["files"]),
            "approved": True,
            "approved_at": timestamp,
            "idempotency_key": f"upy-scaffold-plugin:{session_id}:file-write:v1",
        }
    ]
    if lint:
        permissions.append(
            {
                "type": "script_run",
                "name": "flake8",
                "command": lint_payload["command"],
                "cwd": lint_payload["cwd"],
                "approved": True,
                "approved_at": lint_payload.get("completed_at", timestamp),
                "idempotency_key": f"upy-scaffold-plugin:{session_id}:script:flake8:v1",
            }
        )
    manifest_content = output["manifest_content"]
    manifest_scaffold = deepcopy(manifest_content.get("scaffold", {}))
    modules = manifest_scaffold.get("modules") or manifest_content.get("scaffold_modules") or parse_json_or_csv(args.modules)
    custom_files = manifest_scaffold.get("custom_files") or manifest_content.get("scaffold_custom_files") or parse_json_or_csv(args.custom_files)
    phase_next = phase_payload.get("next_phase") if result == "success" else None
    approval_payload = {
        "approval_id": "scaffold_config",
        "confirmed": True,
        "confirmed_at": timestamp,
        "mode": args.mode,
        "modules": modules,
        "custom_files": custom_files,
        "selected": {
            "mode": args.mode,
            "modules": modules,
            "custom_files": custom_files,
        },
        "raw_input": {
            "modules": args.modules,
            "custom_files": args.custom_files,
        },
        "source": "apply_scaffold.py",
    }
    file_status_counts = {
        state: sum(1 for entry in file_manifest["files"] if entry.get("status") == state)
        for state in sorted({entry.get("status") for entry in file_manifest["files"]})
    }
    scaffold_summary = {
        **manifest_scaffold,
        "result": result,
        "summary": phase_payload.get("summary"),
        "next_phase": phase_next,
        "mode": manifest_scaffold.get("mode") or manifest_content.get("scaffold_mode") or args.mode,
        "modules": modules,
        "custom_files": custom_files,
        "artifact_root": runtime_context["artifact_root"],
        "session_root": runtime_context["session_root"],
        "project_root": project_artifact_path,
        "file_operation_root": project_artifact_path,
        "file_manifest_path": file_manifest.get("path"),
        "phase_complete_path": relative_artifact_path(session_dir / "phase_complete.upy_scaffold_plugin.json", artifact_root) if session_dir else "",
        "file_count": len(file_manifest["files"]),
        "directory_count": len(output.get("directories", [])),
        "file_status_counts": file_status_counts,
        "lint": {
            "command": lint_payload.get("command"),
            "cwd": lint_payload.get("cwd"),
            "config": lint_payload.get("config"),
            "returncode": lint_payload.get("returncode"),
        } if lint_payload else None,
        "source": {
            "source_phase": source_payload["source_phase"],
            "source_phase_complete_path": source_payload["source_phase_complete_path"],
            "source_manifest_kind": source_payload["source_manifest_kind"],
        },
        "approval_id": approval_payload["approval_id"],
        "idempotency_key": f"upy-scaffold-plugin:{session_id}:phase-complete:v1",
        "incremental": args.mode == "incremental",
        "generate_scope": "new_devices_only" if args.mode == "incremental" else "full_project",
        "completed_at": timestamp if result == "success" else None,
    }
    payload = {
        "phase": "scaffold",
        "domain_phase": "scaffold",
        "result": result,
        "summary": phase_payload.get("summary"),
        "next_phase": phase_next,
        "source": source_payload,
        "scaffold": scaffold_summary,
        "runtime_context": runtime_context,
        "file_manifest": file_manifest,
        "artifacts": artifacts,
        "lint": lint_payload,
        "approval": approval_payload,
        "permissions": permissions,
        "warnings": phase_payload.get("warnings", []),
        "errors": [item["message"] for item in structured_errors],
        "structured_errors": structured_errors,
        "manifest_content": manifest_content,
        "phase_completed_at": timestamp if result == "success" else None,
    }
    return {
        "protocol_version": "1.0",
        "msg_id": f"local-actual-scaffold-{session_id}",
        "session_id": session_id,
        "phase": "upy-scaffold-plugin",
        "timestamp": timestamp,
        "type": "phase_complete",
        "idempotency_key": f"upy-scaffold-plugin:{session_id}:phase-complete:v1",
        "retry_of": None,
        "payload": payload,
    }


def run_actual_project(args: argparse.Namespace) -> dict[str, Any]:
    source_data = load_json(Path(args.manifest))
    manifest = extract_manifest(source_data)
    project_dir, session_dir, is_temp_project = resolve_project_dir(args)
    render_utc = existing_project_updated_at(project_dir) or utc_now()
    output = run_renderer(args.mode, manifest, args.modules, args.custom_files, args.new_devices, render_utc)
    project_dir.mkdir(parents=True, exist_ok=True)

    entries = apply_file_operations(project_dir, output, force=args.force, dry_run=args.dry_run)
    file_manifest = build_file_manifest(project_dir, entries)
    structured_errors: list[dict[str, Any]] = []
    conflicts = [entry for entry in entries if entry["status"] == "skipped"]
    if conflicts:
        structured_errors.append(
            {
                "code": "FILE_CONFLICT",
                "message": "target files already exist with different content; rerun with --force to overwrite",
                "severity": "error",
                "recoverable": True,
                "retryable": False,
                "source": "apply_scaffold.py",
                "field": "file_operations[].path",
                "files": [entry["path"] for entry in conflicts],
            }
        )

    lint = None
    if not args.dry_run and not structured_errors:
        assert_required_outputs(project_dir)
        lint = run_flake8(project_dir)
        lint["completed_at"] = utc_now()
        if lint["returncode"] != 0:
            structured_errors.append(
                {
                    "code": "SCAFFOLD_LINT_FAILED",
                    "message": "flake8 gate failed",
                    "severity": "error",
                    "recoverable": True,
                    "retryable": True,
                    "source": "apply_scaffold.py",
                    "field": "lint.returncode",
                }
            )

    status = "success" if not structured_errors else "partial"
    phase_complete = build_phase_complete(
        args,
        source_data,
        output,
        project_dir,
        session_dir,
        file_manifest,
        lint,
        status,
        structured_errors,
    )
    if args.write_phase_complete and session_dir and not args.dry_run:
        file_manifest_path = session_dir / "scaffold_file_manifest.json"
        file_manifest_path.write_text(
            json.dumps(phase_complete["payload"]["file_manifest"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        phase_path = session_dir / "phase_complete.upy_scaffold_plugin.json"
        phase_path.write_text(json.dumps(phase_complete, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "status": status,
        "project_dir": str(project_dir),
        "session_dir": str(session_dir) if session_dir else "",
        "file_count": len(entries),
        "file_status_counts": {state: sum(1 for entry in entries if entry["status"] == state) for state in sorted({entry["status"] for entry in entries})},
        "next_phase": phase_complete["payload"].get("next_phase"),
        "flake8": lint,
        "phase_complete": phase_complete,
        "_temp_project": is_temp_project,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply upy-scaffold output to a project and finalize phase_complete")
    parser.add_argument("--manifest", default=str(SELECT_HW_SAMPLE), help="manifest or phase_complete JSON")
    parser.add_argument("--session-dir", default="", help="session directory; default project dir becomes <session-dir>/project")
    parser.add_argument("--project-dir", default="", help="target project directory; defaults to a temp dir")
    parser.add_argument("--mode", default="timer", choices=["timer", "async", "thread", "incremental"])
    parser.add_argument("--modules", default="all", help="module selection for full mode")
    parser.add_argument("--custom-files", default="[]", help="extra custom files for full mode")
    parser.add_argument(
        "--new-devices",
        default='[{"name":"DHT22","driver":{"source":"upypi","install_cmd":"mpremote mip install dht"}}]',
        help="new devices JSON for incremental mode",
    )
    parser.add_argument("--force", action="store_true", help="allow writing into a non-empty project dir")
    parser.add_argument("--dry-run", action="store_true", help="render and plan file writes without touching the project")
    parser.add_argument("--write-phase-complete", action="store_true", help="write phase_complete.upy_scaffold_plugin.json under --session-dir")
    parser.add_argument("--keep", action="store_true", help="keep temp project dir after success")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    summary = run_actual_project(args)
    public_summary = {key: value for key, value in summary.items() if not key.startswith("_")}
    print(json.dumps(public_summary, ensure_ascii=False, indent=2))
    if summary.get("_temp_project") and not args.keep:
        shutil.rmtree(summary["project_dir"], ignore_errors=True)
    return 0 if summary["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
