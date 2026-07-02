#!/usr/bin/env python3
"""Smoke tests for upy-wiring-plugin resources."""

from __future__ import annotations

import json
import os
import hashlib
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
PHASE = "upy-wiring-plugin"
PLUGIN_VALIDATOR = Path("C:/Users/Administrator/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py")
REAL_REPO = REPO if (REPO / "upy-project-gen-toolchain-spec").is_dir() else Path("G:/MicroPython_Skills")
SCHEMA = REAL_REPO / "upy-project-gen-toolchain-spec" / "wiring.schema.json"
SCHEMA_VALIDATOR = REAL_REPO / "upy-project-gen-toolchain-spec" / "scripts" / "validate_json.py"


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


def run_json(args: list[str]) -> dict[str, Any]:
    proc = run(args)
    if proc.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    if not proc.stdout.strip():
        raise AssertionError(f"command produced no JSON: {' '.join(args)}")
    return json.loads(proc.stdout)


def run_json_allow_failure(args: list[str]) -> tuple[int, dict[str, Any]]:
    proc = run(args)
    if not proc.stdout.strip():
        raise AssertionError(f"command produced no JSON: {' '.join(args)}\nstderr={proc.stderr}")
    return proc.returncode, json.loads(proc.stdout)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def topology_manifest() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "phase": "generate",
        "project_name": "voice_chatbot",
        "mcu": {
            "model": "ESP32-WROOM-32",
            "display_name": "ESP32 DevKit V1",
            "board_id": "esp32-devkit-v1",
        },
        "devices": [
            {"name": "INMP441", "type": "microphone", "interface": "I2S", "quantity": 1},
            {"name": "MAX98357 + Speaker", "type": "speaker", "interface": "I2S", "quantity": 1},
            {"name": "Tactile Button", "type": "button", "interface": "GPIO", "quantity": 1},
            {"name": "LED", "type": "led", "interface": "GPIO", "quantity": 1},
            {"name": "uopenai", "type": "middleware", "interface": "WiFi", "quantity": 1},
        ],
        "pinout": [
            {"device": "INMP441", "pin_name": "VDD", "gpio": "3V3", "type": "power_3v3", "source": "power"},
            {"device": "INMP441", "pin_name": "GND", "gpio": "GND", "type": "gnd", "source": "power"},
            {"device": "INMP441", "pin_name": "L/R", "gpio": "GND", "type": "gnd", "source": "power"},
            {"device": "INMP441", "pin_name": "SCK", "gpio": 26, "type": "i2s_bck", "bus": "i2s0"},
            {"device": "INMP441", "pin_name": "WS", "gpio": 25, "type": "i2s_ws", "bus": "i2s0"},
            {"device": "INMP441", "pin_name": "SD", "gpio": 27, "type": "i2s_data_in", "bus": "i2s0"},
            {"device": "MAX98357 + Speaker", "pin_name": "VIN", "gpio": "5V", "type": "power_5v", "source": "power"},
            {"device": "MAX98357 + Speaker", "pin_name": "GND", "gpio": "GND", "type": "gnd", "source": "power"},
            {"device": "MAX98357 + Speaker", "pin_name": "BCLK", "gpio": 14, "type": "i2s_bck", "bus": "i2s1"},
            {"device": "MAX98357 + Speaker", "pin_name": "LRC", "gpio": 32, "type": "i2s_ws", "bus": "i2s1"},
            {"device": "MAX98357 + Speaker", "pin_name": "DIN", "gpio": 33, "type": "i2s_data_out", "bus": "i2s1"},
            {"device": "MAX98357 + Speaker", "pin_name": "SD", "gpio": 21, "type": "gpio_out"},
            {"device": "MAX98357 + Speaker", "pin_name": "GAIN", "gpio": "GND", "type": "gnd", "source": "power"},
            {"device": "Tactile Button", "pin_name": "OUT", "gpio": 18, "type": "gpio_in_pullup"},
            {"device": "Tactile Button", "pin_name": "GND", "gpio": "GND", "type": "gnd", "source": "power"},
            {"device": "LED", "pin_name": "A", "gpio": 19, "type": "gpio_out"},
            {"device": "LED", "pin_name": "K", "gpio": "GND", "type": "gnd", "source": "power"},
        ],
    }


def legacy_i2s_wiring() -> dict[str, Any]:
    return {
        "meta": {
            "project": "voice_chatbot",
            "mcu_model": "ESP32-WROOM-32",
            "generated_at": "2026-07-01T11:00:00Z",
            "source_phase": "generate",
        },
        "mcu": {
            "name": "ESP32-WROOM-32",
            "package": "ESP32 DevKit V1",
            "pin_count": 30,
            "orientation": "vertical",
            "pins": [
                {"gpio": "3V3", "side": "left", "pos": 0, "label": "3.3V Power", "type": "power_3v3"},
                {"gpio": "5V", "side": "left", "pos": 1, "label": "5V Power", "type": "power_5v"},
                {"gpio": "GND", "side": "left", "pos": 2, "label": "Ground", "type": "gnd"},
                {"gpio": "14", "side": "right", "pos": 0, "label": "GPIO14 / I2S1 BCK -> MAX98357 BCLK", "type": "i2s"},
                {"gpio": "32", "side": "right", "pos": 1, "label": "GPIO32 / I2S1 WS -> MAX98357 LRC", "type": "i2s"},
                {"gpio": "33", "side": "right", "pos": 2, "label": "GPIO33 / I2S1 DATA OUT -> MAX98357 DIN", "type": "i2s"},
                {"gpio": "26", "side": "right", "pos": 3, "label": "GPIO26 / I2S0 BCK -> INMP441 SCK", "type": "i2s"},
                {"gpio": "25", "side": "right", "pos": 4, "label": "GPIO25 / I2S0 WS -> INMP441 WS", "type": "i2s"},
                {"gpio": "27", "side": "right", "pos": 5, "label": "GPIO27 / I2S0 DATA IN <- INMP441 SD", "type": "i2s"},
                {"gpio": "21", "side": "right", "pos": 6, "label": "GPIO21 / MAX98357 SD", "type": "gpio_out"},
                {"gpio": "19", "side": "right", "pos": 7, "label": "GPIO19 / LED", "type": "gpio_out"},
                {"gpio": "18", "side": "right", "pos": 8, "label": "GPIO18 / Button", "type": "gpio_in_pullup"},
            ],
        },
        "buses": [],
        "standalone": [
            {"name": "Tactile Button", "pin": "18", "type": "gpio_in_pullup", "active_level": "low"},
            {"name": "LED", "pin": "19", "type": "gpio_out", "active_level": "high"},
            {"name": "MAX98357 SD (Shutdown)", "pin": "21", "type": "gpio_out", "active_level": "high"},
        ],
        "power": [
            {"rail": "3.3V", "source_pins": ["3V3"], "consumers": ["INMP441"]},
            {"rail": "5V", "source_pins": ["5V"], "consumers": ["MAX98357 + Speaker"]},
            {"rail": "GND", "source_pins": ["GND"], "consumers": ["INMP441", "MAX98357 + Speaker", "LED", "Tactile Button"]},
        ],
        "alerts": [],
    }


def write_phase_success_tree(root: Path, wiring: dict[str, Any]) -> Path:
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    wiring_path = docs / "wiring.json"
    wiring_path.write_text(json.dumps(wiring, ensure_ascii=False, indent=2), encoding="utf-8")
    if wiring.get("components") and wiring.get("connections"):
        for fmt in ("md", "html"):
            proc = run([
                sys.executable,
                str(SCRIPTS / "render_wiring_local.py"),
                "--input",
                str(wiring_path),
                "--output",
                str(docs),
                "--format",
                fmt,
            ])
            if proc.returncode != 0:
                raise AssertionError(f"render {fmt} for phase tree failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    phase = load_json(SAMPLE / "phase_complete.upy_wiring_plugin.success.json")
    files = []
    for artifact in phase["payload"]["artifacts"]:
        path = artifact["path"]
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            data = f"{path}\n".encode("utf-8")
            target.write_bytes(data)
        data = target.read_bytes()
        files.append({
            "path": path,
            "type": artifact["type"],
            "required": True,
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "source": "test",
            "checkpoint": "artifacts_rendered",
        })
    phase["payload"]["file_manifest"]["files"] = files
    phase_path = root / "phase_complete.json"
    phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
    return phase_path


def assert_plugin_json_shape() -> None:
    plugin = load_json(ROOT / ".codex-plugin" / "plugin.json")
    if plugin.get("name") != PHASE:
        raise AssertionError("plugin.json name mismatch")
    interface = plugin.get("interface", {})
    if "wiring diagrams" not in interface.get("shortDescription", ""):
        raise AssertionError("plugin interface metadata not customized")
    if plugin.get("skills"):
        raise AssertionError("plugin.json should not point to missing ./skills")


def assert_sample_json() -> None:
    for path in sorted(SAMPLE.glob("*.json")):
        data = load_json(path)
        if data.get("phase") and data["phase"] != PHASE:
            raise AssertionError(f"{path.name} top-level phase mismatch")
        payload = data.get("payload")
        if isinstance(payload, dict) and payload.get("phase") and payload["phase"] != PHASE:
            raise AssertionError(f"{path.name} payload.phase mismatch")
    partial = load_json(SAMPLE / "phase_complete.upy_wiring_plugin.partial.json")
    if partial["payload"]["next_phase"] is not None:
        raise AssertionError("partial wiring phase_complete must not route next_phase")
    success = load_json(SAMPLE / "phase_complete.upy_wiring_plugin.success.json")
    if success["payload"]["next_phase"] is not None:
        raise AssertionError("success wiring phase_complete must not route next_phase")
    paths = {item["path"] for item in success["payload"]["artifacts"] if isinstance(item, dict) and "path" in item}
    required = {"docs/wiring.json", "docs/wiring.md", "docs/wiring.html", "docs/wiring_pins.md", "docs/wiring.svg", "docs/wiring.png"}
    if required - paths:
        raise AssertionError(f"success sample missing required artifact paths: {required - paths}")
    if success["payload"].get("session_state", {}).get("checkpoint") != "phase_completed":
        raise AssertionError("success sample must record phase_completed session_state")
    if not success["payload"].get("file_manifest", {}).get("files"):
        raise AssertionError("success sample must include file_manifest files")
    wiring = load_json(SAMPLE / "wiring.sample.json")
    protocols = {conn.get("protocol") for conn in wiring.get("connections", []) if isinstance(conn, dict)}
    if "I2S" not in protocols:
        raise AssertionError("wiring sample must include component-level I2S connections")
    for item in wiring.get("standalone", []):
        pin = item.get("pin") if isinstance(item, dict) else None
        if isinstance(pin, str) and "," in pin:
            raise AssertionError("standalone sample must not use comma-separated multi-pin strings")


def assert_skill_text_contract() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = [
        "upy-generate-plugin success",
        "optional_next_phases includes upy-wiring-plugin",
        "next_phase` 默认必须是 `null`",
        "不覆盖旧 `G:\\MicroPython_Skills\\upy-wiring`",
        "不覆盖或改名 `G:\\MicroPython_Skills\\upy-deploy`",
        "firmware/ 实际代码 > project-manifest.json > LLM 推断",
        "approval_request(approval_id=\"wiring_network_render\")",
        "approval_request(approval_id=\"wiring_conflict_review\")",
        "scripts/derive_wiring_topology.py",
        "scripts/render_wiring_local.py",
        "scripts/wiring_manifest.py",
        "协议字段语义",
        "session_state.upy_wiring_plugin.json",
        "wiring_file_manifest.json",
        "PROTOCOL_UNSUPPORTED",
        "CAPABILITY_UNAVAILABLE",
        "CANCELLED_BY_USER",
        "IDEMPOTENCY_CONFLICT",
        "正式 success 必须生成 `wiring.svg` 和 `wiring.png`",
        "元器件级、引脚级标注的电气接线拓扑图",
        "components[]",
        "connections[]",
        "standalone.pin=\"14,32,33\"",
        "project-manifest.json pinout",
        "net_*",
        "alerts_sg",
        "白色或浅色背景",
        "docs/wiring.json",
        "docs/wiring_pins.md",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise AssertionError(f"SKILL.md missing required contract text: {missing}")


def assert_manifest_validator() -> None:
    start = run_json([
        sys.executable,
        str(SCRIPTS / "wiring_manifest.py"),
        "--validate-start-phase",
        "--input",
        str(SAMPLE / "start_phase.upy_wiring_plugin.full.json"),
    ])
    if start["status"] != "ok":
        raise AssertionError(f"start validation failed: {start}")
    direct = run_json([
        sys.executable,
        str(SCRIPTS / "wiring_manifest.py"),
        "--validate-start-phase",
        "--input",
        str(SAMPLE / "start_phase.upy_wiring_plugin.direct_test.json"),
    ])
    if direct["status"] != "ok":
        raise AssertionError(f"direct_test validation failed: {direct}")
    for name in (
        "phase_complete.upy_wiring_plugin.success.json",
        "phase_complete.upy_wiring_plugin.partial.json",
        "phase_complete.upy_wiring_plugin.cancelled.json",
        "phase_complete.upy_wiring_plugin.timeout.json",
        "phase_complete.upy_wiring_plugin.capability_unavailable.json",
        "phase_complete.upy_wiring_plugin.permission_denied.json",
    ):
        result = run_json([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(SAMPLE / name),
        ])
        if result["status"] != "ok":
            raise AssertionError(f"{name} validation failed: {result}")
    with tempfile.TemporaryDirectory(prefix="wiring-bad-phase-") as temp_dir:
        bad_path = Path(temp_dir) / "bad.json"
        bad = load_json(SAMPLE / "phase_complete.upy_wiring_plugin.success.json")
        bad["payload"]["next_phase"] = "upy-deploy-plugin"
        bad["payload"]["artifacts"] = [{"type": "wiring_json", "path": "docs/wiring.json"}]
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(bad_path),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"bad phase_complete must fail: {payload}")
        text = json.dumps(payload, ensure_ascii=False)
        if "next_phase must be null" not in text or "success artifacts missing" not in text:
            raise AssertionError(f"bad phase_complete errors incomplete: {payload}")
    with tempfile.TemporaryDirectory(prefix="wiring-bad-success-") as temp_dir:
        bad_path = Path(temp_dir) / "missing_images.json"
        bad = load_json(SAMPLE / "phase_complete.upy_wiring_plugin.success.json")
        bad["payload"]["artifacts"] = [
            item for item in bad["payload"]["artifacts"]
            if item.get("path") not in {"docs/wiring.svg", "docs/wiring.png"}
        ]
        bad["payload"]["file_manifest"]["files"] = [
            item for item in bad["payload"]["file_manifest"]["files"]
            if item.get("path") not in {"docs/wiring.svg", "docs/wiring.png"}
        ]
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(bad_path),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"success without SVG/PNG must fail: {payload}")
        if "docs/wiring.svg" not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError(f"missing image validation did not mention SVG/PNG: {payload}")
    with tempfile.TemporaryDirectory(prefix="wiring-bad-protocol-") as temp_dir:
        bad_path = Path(temp_dir) / "bad_protocol.json"
        bad = load_json(SAMPLE / "start_phase.upy_wiring_plugin.full.json")
        bad["protocol_version"] = "0.9"
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-start-phase",
            "--input",
            str(bad_path),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"bad protocol start must fail: {payload}")
        if "protocol_version must be 1.0" not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError(f"bad protocol error incomplete: {payload}")
    with tempfile.TemporaryDirectory(prefix="wiring-bad-network-") as temp_dir:
        bad_path = Path(temp_dir) / "bad_network_backend.json"
        bad = load_json(SAMPLE / "phase_complete.upy_wiring_plugin.success.json")
        bad["payload"]["render_policy"] = {
            "formats": ["json", "md", "html", "pins", "svg", "png"],
            "network_rendering": "deny",
            "timeout_ms": 30000,
        }
        bad["payload"]["render_result"]["svg"]["backend"] = "mermaid_ink"
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(bad_path),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"network backend under deny policy must fail: {payload}")
        if "network_rendering=deny" not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError(f"network deny backend error incomplete: {payload}")
    with tempfile.TemporaryDirectory(prefix="wiring-network-permission-") as temp_dir:
        bad_path = Path(temp_dir) / "bad_network_permission.json"
        bad = load_json(SAMPLE / "phase_complete.upy_wiring_plugin.success.json")
        bad["payload"]["render_policy"] = {
            "formats": ["json", "md", "html", "pins", "svg", "png"],
            "network_rendering": "ask",
            "timeout_ms": 30000,
        }
        bad["payload"]["render_result"]["svg"]["backend"] = "mermaid_ink"
        bad["payload"]["render_result"]["png"]["backend"] = "mermaid_ink"
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(bad_path),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"network backend without permission must fail: {payload}")
        if "network_permission approval evidence" not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError(f"network permission error incomplete: {payload}")
        good = bad
        good["payload"]["network_permission"] = {
            "approval_id": "wiring_network_render",
            "result": "render_all",
            "granted_at": "2026-07-01T06:40:00Z",
        }
        bad_path.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(bad_path),
        ])
        if result["status"] != "ok":
            raise AssertionError(f"network backend with permission should pass: {result}")
    with tempfile.TemporaryDirectory(prefix="wiring-artifact-root-") as temp_dir:
        root = Path(temp_dir)
        docs = root / "docs"
        phase_path = write_phase_success_tree(root, load_json(SAMPLE / "wiring.sample.json"))
        result = run_json([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(phase_path),
            "--artifact-root",
            str(root),
        ])
        if result["status"] != "ok":
            raise AssertionError(f"artifact-root validation failed for matching files: {result}")
        (docs / "wiring.png").write_bytes(b"changed")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(phase_path),
            "--artifact-root",
            str(root),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"artifact-root hash mismatch must fail: {payload}")
        if "sha256 mismatch" not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError(f"artifact-root mismatch error incomplete: {payload}")
    with tempfile.TemporaryDirectory(prefix="wiring-bad-multipin-") as temp_dir:
        root = Path(temp_dir)
        docs = root / "docs"
        docs.mkdir()
        wiring = load_json(SAMPLE / "wiring.sample.json")
        wiring["standalone"].append({
            "name": "Bad I2S Device",
            "pin": "14,32,33",
            "type": "gpio_out",
        })
        (docs / "wiring.json").write_text(json.dumps(wiring, ensure_ascii=False), encoding="utf-8")
        phase = load_json(SAMPLE / "phase_complete.upy_wiring_plugin.success.json")
        files = []
        for artifact in phase["payload"]["artifacts"]:
            path = artifact["path"]
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if path == "docs/wiring.json":
                data = (docs / "wiring.json").read_bytes()
            else:
                data = f"{path}\n".encode("utf-8")
                target.write_bytes(data)
            files.append({
                "path": path,
                "type": artifact["type"],
                "required": True,
                "sha256": sha256_bytes(data),
                "bytes": len(data),
                "source": "test",
                "checkpoint": "artifacts_rendered",
            })
        phase["payload"]["file_manifest"]["files"] = files
        phase_path = root / "phase_complete.json"
        phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(phase_path),
            "--artifact-root",
            str(root),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"comma-separated standalone pin must fail: {payload}")
        if "comma-separated multiple pins" not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError(f"multi-pin error incomplete: {payload}")
    with tempfile.TemporaryDirectory(prefix="wiring-bad-i2s-topology-") as temp_dir:
        root = Path(temp_dir)
        (root / "project-manifest.json").write_text(
            json.dumps(topology_manifest(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        phase_path = write_phase_success_tree(root, legacy_i2s_wiring())
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(phase_path),
            "--artifact-root",
            str(root),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"I2S pinout without component topology must fail: {payload}")
        text = json.dumps(payload, ensure_ascii=False)
        if "I2S pinout requires non-empty wiring.json components[]" not in text:
            raise AssertionError(f"I2S topology error did not mention missing components: {payload}")
        if "I2S pinout requires non-empty wiring.json connections[]" not in text:
            raise AssertionError(f"I2S topology error did not mention missing connections: {payload}")
    with tempfile.TemporaryDirectory(prefix="wiring-updated-at-") as temp_dir:
        session = Path(temp_dir)
        project = session / "project"
        project.mkdir()
        upstream_manifest = topology_manifest()
        upstream_manifest["updated_at"] = "2026-07-01T09:45:21Z"
        current_manifest = dict(upstream_manifest)
        current_manifest["updated_at"] = "2026-07-02T01:53:00Z"
        (project / "project-manifest.json").write_text(
            json.dumps(current_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        upstream_phase = {
            "type": "phase_complete",
            "phase": "upy-generate-plugin",
            "payload": {
                "phase": "upy-generate-plugin",
                "result": "success",
                "manifest_content": upstream_manifest,
            },
        }
        upstream_path = session / "phase_complete.upy_generate_plugin.json"
        upstream_path.write_text(json.dumps(upstream_phase, ensure_ascii=False, indent=2), encoding="utf-8")
        phase_path = write_phase_success_tree(project, load_json(SAMPLE / "wiring.sample.json"))
        phase = load_json(phase_path)
        phase["payload"]["source_phase_complete_path"] = "phase_complete.upy_generate_plugin.json"
        phase_path.write_text(json.dumps(phase, ensure_ascii=False), encoding="utf-8")
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(phase_path),
            "--artifact-root",
            str(project),
            "--session-root",
            str(session),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"wiring-updated project-manifest root updated_at must fail: {payload}")
        if "root updated_at must not be changed" not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError(f"updated_at immutability error incomplete: {payload}")
    with tempfile.TemporaryDirectory(prefix="wiring-session-state-") as temp_dir:
        session = Path(temp_dir)
        project = session / "project"
        project.mkdir()
        (project / "project-manifest.json").write_text(
            json.dumps(topology_manifest(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        phase_path = write_phase_success_tree(project, load_json(SAMPLE / "wiring.sample.json"))
        (session / "session_state.upy_wiring_plugin.json").write_text(
            json.dumps(
                {
                    "session_id": "demo-session",
                    "idempotency_key": "upy-wiring-plugin:demo-session:full:v1",
                    "mode": "direct_test",
                    "source": "test_only",
                    "checkpoint": "phase_completed",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        rc, payload = run_json_allow_failure([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(phase_path),
            "--artifact-root",
            str(project),
        ])
        if rc == 0 or payload.get("status") != "failed":
            raise AssertionError(f"formal success with direct_test session_state must fail: {payload}")
        if "session_state.mode=direct_test" not in json.dumps(payload, ensure_ascii=False):
            raise AssertionError(f"session_state consistency error incomplete: {payload}")


def assert_wiring_schema_and_render_local() -> None:
    schema_proc = run([
        sys.executable,
        str(SCHEMA_VALIDATOR),
        "--schema",
        str(SCHEMA),
        "--json",
        str(SAMPLE / "wiring.sample.json"),
    ])
    if schema_proc.returncode != 0:
        raise AssertionError(f"sample wiring schema validation failed:\nstdout={schema_proc.stdout}\nstderr={schema_proc.stderr}")
    with tempfile.TemporaryDirectory(prefix="wiring-render-") as temp_dir:
        docs = Path(temp_dir) / "docs"
        docs.mkdir()
        wiring_json = docs / "wiring.json"
        shutil.copy2(SAMPLE / "wiring.sample.json", wiring_json)
        for fmt in ("md", "html"):
            proc = run([
                sys.executable,
                str(SCRIPTS / "render_wiring_local.py"),
                "--input",
                str(wiring_json),
                "--output",
                str(docs),
                "--format",
                fmt,
            ])
            if proc.returncode != 0:
                raise AssertionError(f"render {fmt} failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
        for expected in ("wiring.md", "wiring.html", "wiring_pins.md"):
            if not (docs / expected).is_file():
                raise AssertionError(f"render did not create {expected}")
        md_text = (docs / "wiring.md").read_text(encoding="utf-8")
        pins_text = (docs / "wiring_pins.md").read_text(encoding="utf-8")
        required_terms = [
            "MAX98357 Audio Amplifier",
            "INMP441 Microphone",
            "GPIO14",
            "BCLK",
            "GPIO32",
            "LRC",
            "GPIO33",
            "DIN",
            "GPIO26",
            "SCK",
            "GPIO25",
            "WS",
            "GPIO27",
            "SD",
        ]
        for term in required_terms:
            if term not in md_text:
                raise AssertionError(f"wiring.md missing component topology term: {term}")
            if term not in pins_text:
                raise AssertionError(f"wiring_pins.md missing pin-to-pin term: {term}")
        if "subgraph alerts_sg" in md_text:
            raise AssertionError("component topology diagram must not render alerts in the main graph")
        if "net_" not in md_text:
            raise AssertionError("component topology diagram must use intermediate net_* label nodes")
        if "-->|" in md_text or "-.->|" in md_text:
            raise AssertionError("component topology diagram must not use long Mermaid edge labels")
        if "-]" in md_text:
            raise AssertionError("component topology net labels must not rely on Mermaid-escaped arrows")
        proc = run([
            sys.executable,
            str(SCRIPTS / "render_wiring_local.py"),
            "--input",
            str(wiring_json),
            "--output",
            str(docs),
            "--format",
            "svg",
            "--network-rendering",
            "deny",
            "--timeout-ms",
            "1000",
        ])
        if shutil.which("mmdc"):
            if proc.returncode != 0:
                raise AssertionError(f"render svg with local mmdc failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
        else:
            if proc.returncode == 0:
                raise AssertionError("render svg must fail with network denied when local mmdc is unavailable")
            if "Missing requested output" not in proc.stderr:
                raise AssertionError(f"render svg deny failure did not explain missing output:\nstdout={proc.stdout}\nstderr={proc.stderr}")


def assert_derive_wiring_topology() -> None:
    with tempfile.TemporaryDirectory(prefix="wiring-derive-topology-") as temp_dir:
        root = Path(temp_dir)
        docs = root / "docs"
        docs.mkdir()
        manifest_path = root / "project-manifest.json"
        wiring_path = docs / "wiring.json"
        manifest_path.write_text(json.dumps(topology_manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
        wiring_path.write_text(json.dumps(legacy_i2s_wiring(), ensure_ascii=False, indent=2), encoding="utf-8")
        result = run_json([
            sys.executable,
            str(SCRIPTS / "derive_wiring_topology.py"),
            "--wiring",
            str(wiring_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(wiring_path),
        ])
        if result["status"] != "ok":
            raise AssertionError(f"derive topology failed: {result}")
        derived = load_json(wiring_path)
        if not derived.get("components") or not derived.get("connections"):
            raise AssertionError("derive topology did not create components/connections")
        component_text = json.dumps(derived.get("components"), ensure_ascii=False)
        connection_text = json.dumps(derived.get("connections"), ensure_ascii=False)
        for term in (
            "MAX98357 Audio Amplifier",
            "INMP441 Microphone",
            "GPIO14",
            "BCLK",
            "GPIO32",
            "LRC",
            "GPIO33",
            "DIN",
            "GPIO26",
            "SCK",
            "GPIO25",
            "WS",
            "GPIO27",
            "SD",
        ):
            if term not in component_text and term not in connection_text:
                raise AssertionError(f"derived topology missing term: {term}")
        amp_sd = [
            conn for conn in derived.get("connections", [])
            if isinstance(conn, dict)
            and conn.get("to", {}).get("component") == "max98357_speaker"
            and conn.get("to", {}).get("pin") == "SD"
        ]
        if not amp_sd or amp_sd[0].get("protocol") != "GPIO":
            raise AssertionError(f"MAX98357 SD shutdown connection must be GPIO, got: {amp_sd}")
        schema_proc = run([
            sys.executable,
            str(SCHEMA_VALIDATOR),
            "--schema",
            str(SCHEMA),
            "--json",
            str(wiring_path),
        ])
        if schema_proc.returncode != 0:
            raise AssertionError(f"derived wiring schema validation failed:\nstdout={schema_proc.stdout}\nstderr={schema_proc.stderr}")
        for fmt in ("md", "html"):
            proc = run([
                sys.executable,
                str(SCRIPTS / "render_wiring_local.py"),
                "--input",
                str(wiring_path),
                "--output",
                str(docs),
                "--format",
                fmt,
            ])
            if proc.returncode != 0:
                raise AssertionError(f"derived render {fmt} failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
        md_text = (docs / "wiring.md").read_text(encoding="utf-8")
        pins_text = (docs / "wiring_pins.md").read_text(encoding="utf-8")
        for term in ("MAX98357 Audio Amplifier", "INMP441 Microphone", "GPIO14", "BCLK", "GPIO27", "SD"):
            if term not in md_text:
                raise AssertionError(f"derived wiring.md missing term: {term}")
            if term not in pins_text:
                raise AssertionError(f"derived wiring_pins.md missing term: {term}")
        if "subgraph alerts_sg" in md_text:
            raise AssertionError("derived component topology must not render alerts in the main graph")
        if "net_" not in md_text:
            raise AssertionError("derived component topology must use intermediate net_* label nodes")
        if "-->|" in md_text or "-.->|" in md_text:
            raise AssertionError("derived component topology must not use long Mermaid edge labels")
        if "-]" in md_text:
            raise AssertionError("derived component topology net labels must not rely on Mermaid-escaped arrows")
        phase_path = write_phase_success_tree(root, derived)
        result = run_json([
            sys.executable,
            str(SCRIPTS / "wiring_manifest.py"),
            "--validate-phase-complete",
            "--input",
            str(phase_path),
            "--artifact-root",
            str(root),
        ])
        if result["status"] != "ok":
            raise AssertionError(f"derived topology phase validation failed: {result}")


def assert_plugin_validator() -> None:
    if not PLUGIN_VALIDATOR.is_file():
        return
    proc = run([sys.executable, str(PLUGIN_VALIDATOR), str(ROOT)])
    if proc.returncode != 0:
        raise AssertionError(f"plugin validator failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")


def main() -> int:
    checks = [
        assert_plugin_json_shape,
        assert_sample_json,
        assert_skill_text_contract,
        assert_manifest_validator,
        assert_wiring_schema_and_render_local,
        assert_derive_wiring_topology,
        assert_plugin_validator,
    ]
    for check in checks:
        check()
    print("upy-wiring-plugin smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

