#!/usr/bin/env python3
"""Smoke tests for upy-diagram-plugin resources."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SAMPLE = ROOT / "sample"
SCRIPTS = ROOT / "scripts"
PHASE = "upy-diagram-plugin"
PLUGIN_VALIDATOR = Path("C:/Users/Administrator/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py")
SKILL_VALIDATOR = Path("C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py")
REAL_REPO = REPO if (REPO / "upy-project-gen-toolchain-spec").is_dir() else Path("G:/MicroPython_Skills")
SCHEMA = REAL_REPO / "upy-project-gen-toolchain-spec" / "diagram.schema.json"
SCHEMA_VALIDATOR = REAL_REPO / "upy-project-gen-toolchain-spec" / "scripts" / "validate_json.py"
REQUIRED_FILES = [
    "docs/diagram.json",
    "docs/architecture.md",
    "docs/architecture.svg",
    "docs/architecture.png",
    "docs/architecture.html",
    "docs/flowchart.md",
    "docs/flowchart.svg",
    "docs/flowchart.png",
    "docs/flowchart.html",
    "docs/data_flow.md",
    "docs/data_flow.svg",
    "docs/data_flow.png",
    "docs/data_flow.html",
]


def run(args: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise AssertionError(f"{path} is not a JSON object")
    return data


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_skill_text_contract() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = [
        "name: upy-diagram-plugin",
        "optional_next_phases includes upy-diagram-plugin",
        "next_phase` 默认必须是 `null`",
        "不覆盖旧 `G:\\MicroPython_Skills\\upy-diagram`",
        "firmware/ 实际代码 > project-manifest.json > LLM 推断",
        "phase` | 必须统一为 `upy-diagram-plugin`",
        "session_id",
        "checkpoint / resume",
        "cancellation / retry / timeout",
        "permission prompts",
        "structured errors",
        "scripts/render_diagram_local.py",
        "scripts/diagram_manifest.py",
        "DIAGRAM_PROTOCOL_UNSUPPORTED",
        "DIAGRAM_CAPABILITY_MISSING",
        "DIAGRAM_RENDER_TIMEOUT",
        "DIAGRAM_PERMISSION_DENIED",
        "正式 success 必须生成 13 个文件",
        "本地 skill 调用测试",
        "LOCAL_TEST_ONLY",
        "本地直测不得写入正式 `project-manifest.json.diagrams`",
        "不得在 `phase_complete.payload.manifest_content.diagrams` 中伪装正式 diagrams",
        "manifest_content.test_artifacts.diagram.files",
        "`partial`、`failed` 和 `cancelled` 结果必须包含 `payload.checkpoint_info`",
        "正式 `success` 必须来自 `mode=full`",
        "确认其 SHA256 与 `<resource_root>/scripts/render_diagram_local.py` 一致",
        "不得复用旧直测产物作为正式成功",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise AssertionError(f"SKILL.md missing required text: {missing}")


def assert_plugin_json_shape() -> None:
    plugin = load_json(ROOT / ".codex-plugin" / "plugin.json")
    if plugin.get("name") != PHASE:
        raise AssertionError("plugin.json name mismatch")
    interface = plugin.get("interface", {})
    if "architecture" not in interface.get("shortDescription", ""):
        raise AssertionError("plugin interface metadata not customized for diagrams")
    if plugin.get("skills"):
        raise AssertionError("plugin.json should not point to missing ./skills")


def assert_sample_json() -> None:
    for path in sorted(SAMPLE.glob("*.json")):
        data = load_json(path)
        if data.get("phase") and data["phase"] not in (PHASE, "upy-generate-plugin"):
            raise AssertionError(f"{path.name} top-level phase mismatch")
        payload = data.get("payload")
        if isinstance(payload, dict) and payload.get("phase") and payload["phase"] not in (PHASE, "upy-generate-plugin"):
            raise AssertionError(f"{path.name} payload.phase mismatch")
        if data.get("type") == "phase_complete" and data.get("phase") == PHASE:
            if payload.get("next_phase") is not None:
                raise AssertionError(f"{path.name} must not route next_phase")
            if "file_manifest" not in payload:
                raise AssertionError(f"{path.name} missing file_manifest")
            result = payload.get("result")
            if result in ("partial", "failed", "cancelled") and "checkpoint_info" not in payload:
                raise AssertionError(f"{path.name} non-success result missing checkpoint_info")
            errors = payload.get("errors", [])
            if not isinstance(errors, list):
                raise AssertionError(f"{path.name} errors must be an array")
            for item in errors:
                if not isinstance(item, dict) or "code" not in item or "message" not in item:
                    raise AssertionError(f"{path.name} errors must be structured")
    success = load_json(SAMPLE / "phase_complete.upy_diagram_plugin.success.json")
    if success["payload"].get("checkpoint") != "phase_completed":
        raise AssertionError("success sample checkpoint mismatch")
    if success["payload"].get("mode") != "full":
        raise AssertionError("success sample must be mode=full")
    if success["payload"].get("invocation_mode") != "plugin_protocol":
        raise AssertionError("success sample must use invocation_mode=plugin_protocol")
    if success["payload"].get("local_test") is True:
        raise AssertionError("success sample must not be local_test")
    paths = {item["path"] for item in success["payload"]["artifacts"] if isinstance(item, dict) and "path" in item}
    missing = set(REQUIRED_FILES) - paths
    if missing:
        raise AssertionError(f"success sample missing required artifact paths: {missing}")
    files = success["payload"]["file_manifest"]["files"]
    if len(files) != len(REQUIRED_FILES):
        raise AssertionError("success sample file_manifest must include 13 files")
    start = load_json(SAMPLE / "start_phase.upy_diagram_plugin.full.json")
    caps = start["payload"]["capabilities"]
    for field in ("checkpoint_resume", "cancellation", "retry", "timeout", "permission_prompt", "artifact_manifest"):
        if caps.get(field) is not True:
            raise AssertionError(f"start_phase capability missing: {field}")
    direct = load_json(SAMPLE / "phase_complete.upy_diagram_plugin.direct_test.json")
    direct_payload = direct["payload"]
    if direct_payload.get("result") != "partial":
        raise AssertionError("direct test sample must be partial")
    if direct_payload.get("mode") != "direct_test" or direct_payload.get("invocation_mode") != "local_skill_test":
        raise AssertionError("direct test sample invocation fields mismatch")
    if "diagrams" in direct_payload.get("manifest_content", {}):
        raise AssertionError("direct test sample must not use formal manifest_content.diagrams")
    warning_codes = {
        item.get("code")
        for item in direct_payload.get("warnings", [])
        if isinstance(item, dict)
    }
    if "LOCAL_TEST_ONLY" not in warning_codes:
        raise AssertionError("direct test sample must include LOCAL_TEST_ONLY")


def assert_schema_and_render_md() -> None:
    if not SCHEMA.is_file() or not SCHEMA_VALIDATOR.is_file():
        raise AssertionError("diagram schema or schema validator missing")
    proc = run([
        sys.executable,
        str(SCHEMA_VALIDATOR),
        "--schema",
        str(SCHEMA),
        "--json",
        str(SAMPLE / "diagram.sample.json"),
    ])
    if proc.returncode != 0:
        raise AssertionError(f"diagram.sample.json schema validation failed\nstdout={proc.stdout}\nstderr={proc.stderr}")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "docs"
        out.mkdir(parents=True)
        proc = run([
            sys.executable,
            str(SCRIPTS / "render_diagram_local.py"),
            "--input",
            str(SAMPLE / "diagram.sample.json"),
            "--output",
            str(out),
            "--format",
            "md",
            "--json-summary",
        ])
        if proc.returncode != 0:
            raise AssertionError(f"render_diagram_local.py --format md failed\nstdout={proc.stdout}\nstderr={proc.stderr}")
        for name in ("architecture.md", "flowchart.md", "data_flow.md"):
            if not (out / name).is_file():
                raise AssertionError(f"render missing {name}")
        last_line = proc.stdout.strip().splitlines()[-1]
        summary = json.loads(last_line)
        if summary.get("status") != "ok":
            raise AssertionError("render json-summary status must be ok")
        summary_paths = {item["path"] for item in summary.get("files", [])}
        if {"architecture.md", "flowchart.md", "data_flow.md"} - summary_paths:
            raise AssertionError("render json-summary missing md outputs")

        hostile = load_json(SAMPLE / "diagram.sample.json")
        hostile["data_flow"] = [
            {
                "from": "drivers.tactile_button_driver",
                "to": "tasks.voice_chat_task",
                "data": "button.value()==0",
                "channel": "callback_param",
                "rate": "on_change (单次管道)",
            },
            {
                "from": "drivers.inmp441_driver",
                "to": "drivers.xfyun_asr_driver",
                "data": "PCM 16kHz audio buffer",
                "channel": "function_return",
                "rate": "30ms chunk (1600 bytes/chunk)",
            },
        ]
        hostile_input = Path(tmp) / "diagram.hostile.json"
        hostile_input.write_text(json.dumps(hostile, ensure_ascii=False), encoding="utf-8")
        proc = run([
            sys.executable,
            str(SCRIPTS / "render_diagram_local.py"),
            "--input",
            str(hostile_input),
            "--output",
            str(out),
            "--format",
            "md",
            "--json-summary",
        ])
        if proc.returncode != 0:
            raise AssertionError(f"hostile data_flow render failed\nstdout={proc.stdout}\nstderr={proc.stderr}")
        data_flow_text = (out / "data_flow.md").read_text(encoding="utf-8")
        for forbidden in ("@on_change (", "bytes/chunk", "button.value()==0"):
            if forbidden in data_flow_text:
                raise AssertionError(f"data_flow edge label was not sanitized: {forbidden}")
        edge_labels = [line.split("|", 2)[1] for line in data_flow_text.splitlines() if line.count("|") >= 2]
        if not edge_labels:
            raise AssertionError("hostile data_flow produced no edge labels")
        if any(len(label) > 80 for label in edge_labels):
            raise AssertionError(f"data_flow edge label too long: {edge_labels}")


def write_success_artifact_tree(root: Path) -> Path:
    phase = load_json(SAMPLE / "phase_complete.upy_diagram_plugin.success.json")
    for item in phase["payload"]["file_manifest"]["files"]:
        path = root / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (item["path"] + "\n").encode("utf-8")
        path.write_bytes(content)
        item["bytes"] = len(content)
        item["sha256"] = sha256_bytes(content)
    phase_path = root / "phase_complete.json"
    phase_path.write_text(json.dumps(phase, ensure_ascii=False, indent=2), encoding="utf-8")
    return phase_path


def run_manifest_validator(input_path: Path, *, artifact_root: Path | None = None, session_root: Path | None = None) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(SCRIPTS / "diagram_manifest.py"),
        "--validate-phase-complete",
        "--input",
        str(input_path),
    ]
    if artifact_root is not None:
        args.extend(["--artifact-root", str(artifact_root)])
    if session_root is not None:
        args.extend(["--session-root", str(session_root)])
    return run(args)


def assert_manifest_rejects(phase: dict[str, Any], expected_code: str, tmp: Path) -> None:
    path = tmp / f"{expected_code}.json"
    path.write_text(json.dumps(phase, ensure_ascii=False, indent=2), encoding="utf-8")
    proc = run_manifest_validator(path)
    if proc.returncode == 0:
        raise AssertionError(f"diagram_manifest.py accepted invalid case {expected_code}\nstdout={proc.stdout}")
    result = json.loads(proc.stdout)
    codes = {item.get("code") for item in result.get("errors", []) if isinstance(item, dict)}
    if expected_code not in codes:
        raise AssertionError(f"expected {expected_code}, got {result}")


def assert_diagram_manifest_validator() -> None:
    for name in (
        "phase_complete.upy_diagram_plugin.partial.json",
        "phase_complete.upy_diagram_plugin.direct_test.json",
        "phase_complete.upy_diagram_plugin.cancelled.json",
        "phase_complete.upy_diagram_plugin.timeout.json",
        "phase_complete.upy_diagram_plugin.permission_denied.json",
        "phase_complete.upy_diagram_plugin.capability_unavailable.json",
    ):
        proc = run_manifest_validator(SAMPLE / name)
        if proc.returncode != 0:
            raise AssertionError(f"diagram_manifest.py rejected {name}\nstdout={proc.stdout}\nstderr={proc.stderr}")
        result = json.loads(proc.stdout)
        if result.get("status") != "ok":
            raise AssertionError(f"diagram_manifest status not ok for {name}: {result}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        phase_path = write_success_artifact_tree(root)
        proc = run([
            sys.executable,
            str(SCRIPTS / "diagram_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(phase_path),
            "--artifact-root",
            str(root),
            "--session-root",
            str(root / "sessions" / "demo-session"),
        ])
        if proc.returncode != 0:
            raise AssertionError(f"diagram_manifest.py rejected real artifact tree\nstdout={proc.stdout}\nstderr={proc.stderr}")
        result = json.loads(proc.stdout)
        if result.get("status") != "ok":
            raise AssertionError(f"diagram_manifest status not ok: {result}")
        proc = run([
            sys.executable,
            str(SCRIPTS / "diagram_manifest.py"),
            "--build-file-manifest",
            "--artifact-root",
            str(root),
            "--output",
            str(root / "diagram_file_manifest.json"),
        ])
        if proc.returncode != 0:
            raise AssertionError(f"build-file-manifest failed\nstdout={proc.stdout}\nstderr={proc.stderr}")
        built = json.loads(proc.stdout)
        if len(built.get("file_manifest", {}).get("files", [])) != len(REQUIRED_FILES):
            raise AssertionError("build-file-manifest should report 13 files")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        direct = load_json(SAMPLE / "phase_complete.upy_diagram_plugin.direct_test.json")
        invalid = json.loads(json.dumps(direct))
        invalid["payload"]["result"] = "success"
        assert_manifest_rejects(invalid, "DIRECT_TEST_SUCCESS_INVALID", tmp)

        invalid = json.loads(json.dumps(direct))
        invalid["payload"]["warnings"] = []
        assert_manifest_rejects(invalid, "DIRECT_TEST_WARNING_MISSING", tmp)

        invalid = json.loads(json.dumps(direct))
        invalid["payload"]["manifest_content"]["diagrams"] = {
            "json": "docs/diagram.json",
            "generated_at": "2026-07-02T00:05:00Z",
        }
        assert_manifest_rejects(invalid, "DIRECT_TEST_MANIFEST_DIAGRAMS_INVALID", tmp)

        invalid = load_json(SAMPLE / "phase_complete.upy_diagram_plugin.timeout.json")
        invalid["payload"].pop("checkpoint_info", None)
        assert_manifest_rejects(invalid, "CHECKPOINT_INFO_MISSING", tmp)

        root = tmp / "root"
        phase_path = write_success_artifact_tree(root)
        phase = load_json(phase_path)
        session_root = root / "sessions" / "demo-session"
        session_root.mkdir(parents=True)
        sidecar = json.loads(json.dumps(phase["payload"]["file_manifest"]))
        sidecar["files"][0]["sha256"] = "0" * 64
        (session_root / "diagram_file_manifest.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        proc = run_manifest_validator(phase_path, artifact_root=root, session_root=session_root)
        if proc.returncode == 0:
            raise AssertionError("diagram_manifest.py accepted mismatched sidecar manifest")
        result = json.loads(proc.stdout)
        codes = {item.get("code") for item in result.get("errors", []) if isinstance(item, dict)}
        if "SIDECAR_FILE_MANIFEST_MISMATCH" not in codes:
            raise AssertionError(f"sidecar mismatch code missing: {result}")


def assert_validators() -> None:
    if PLUGIN_VALIDATOR.is_file():
        proc = run([sys.executable, str(PLUGIN_VALIDATOR), str(ROOT)])
        if proc.returncode != 0:
            raise AssertionError(f"plugin validator failed\nstdout={proc.stdout}\nstderr={proc.stderr}")
    if SKILL_VALIDATOR.is_file():
        proc = run([sys.executable, str(SKILL_VALIDATOR), str(ROOT)])
        if proc.returncode != 0:
            raise AssertionError(f"skill validator failed\nstdout={proc.stdout}\nstderr={proc.stderr}")


def main() -> int:
    tests = [
        assert_skill_text_contract,
        assert_plugin_json_shape,
        assert_sample_json,
        assert_schema_and_render_md,
        assert_diagram_manifest_validator,
        assert_validators,
    ]
    for test in tests:
        test()
        print(f"[OK] {test.__name__}")
    print("[OK] upy-diagram-plugin smoke tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
