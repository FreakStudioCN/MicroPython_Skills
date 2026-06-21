#!/usr/bin/env python3
"""Smoke tests for upy-select-hw-plugin."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
REPO_ROOT = SKILL_DIR.parent
SAMPLE_DIR = SKILL_DIR / "sample"
SELECT_HW_MANIFEST = SKILL_DIR / "scripts" / "select_hw_manifest.py"
BOARD_ROOT = REPO_ROOT / "upy-analyze-plugin" / "boards"
PLUGIN_VALIDATOR = Path("C:/Users/Administrator/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py")
EXPECTED_ARTIFACTS = [
    "select_hw_draft.json",
    "select_hw_manifest.after.json",
    "phase_complete.select_hw.success.json",
    "pin_assignment_log.md",
    "select_hw_phase_log.md",
]


def run(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        cmd,
        cwd=str(SKILL_DIR),
        input=input_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def check_sample_json() -> None:
    paths = sorted(SAMPLE_DIR.glob("*.json"))
    if not paths:
        raise AssertionError("no sample JSON files found")
    for path in paths:
        load_json(path)


def check_manifest_validation() -> None:
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--input",
            str(SAMPLE_DIR / "select_hw_draft.json"),
            "--board-root",
            str(BOARD_ROOT),
        ]
    )
    if proc.returncode != 0:
        raise AssertionError(f"select_hw_manifest.py rejected draft:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    result = json.loads(proc.stdout)
    if result.get("status") != "ok":
        raise AssertionError(f"draft validation did not return ok: {result}")
    manifest = result.get("manifest")
    if manifest.get("phase") != "select-hw":
        raise AssertionError("normalized manifest phase is not select-hw")
    if manifest.get("final_status") != "hardware_selected":
        raise AssertionError("normalized manifest final_status is not hardware_selected")


def check_formatted_output_validation() -> None:
    with tempfile.TemporaryDirectory(prefix="select-hw-") as temp_dir:
        output_path = Path(temp_dir) / "select_hw_validated.json"
        proc = run(
            [
                sys.executable,
                str(SELECT_HW_MANIFEST),
                "--input",
                str(SAMPLE_DIR / "select_hw_draft.json"),
                "--write-path",
                str(output_path),
                "--board-root",
                str(BOARD_ROOT),
            ]
        )
        if proc.returncode != 0:
            raise AssertionError(f"select_hw_manifest.py failed --write-path:\nstdout={proc.stdout}\nstderr={proc.stderr}")
        if not output_path.is_file():
            raise AssertionError("--write-path did not create select_hw_validated.json")
        with open(output_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("phase") != "select-hw":
            raise AssertionError("formatted output phase is not select-hw")
        validate_proc = run(
            [
                sys.executable,
                str(SELECT_HW_MANIFEST),
                "--validate-manifest-content",
                "--input",
                str(output_path),
                "--board-root",
                str(BOARD_ROOT),
            ]
        )
        if validate_proc.returncode != 0:
            raise AssertionError(
                "select_hw_manifest.py rejected formatted output:\n"
                f"stdout={validate_proc.stdout}\nstderr={validate_proc.stderr}"
            )


def check_board_unavailable_sample() -> None:
    msg = load_json(SAMPLE_DIR / "approval_request.board_unavailable.json")
    payload = msg.get("payload", {})
    if msg.get("type") != "approval_request":
        raise AssertionError("board_unavailable sample is not an approval_request")
    if payload.get("approval_id") != "board_unavailable":
        raise AssertionError("board_unavailable sample has wrong approval_id")
    action_values = {item.get("value") for item in payload.get("actions", [])}
    expected = {"use_recommended_similar", "select_known_board", "manual_wiring_description", "save_partial"}
    if action_values != expected:
        raise AssertionError(f"board_unavailable actions mismatch: {action_values}")
    manual_fields = {item.get("name") for item in payload.get("manual_wiring_schema", {}).get("fields", [])}
    required_fields = {"mcu_pin", "device", "device_pin", "signal"}
    if not required_fields.issubset(manual_fields):
        raise AssertionError(f"manual wiring schema missing fields: {required_fields - manual_fields}")


def check_no_mcu_preferred_candidates() -> None:
    sys.path.insert(0, str(TEST_DIR))
    try:
        import select_hw_runner  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    manifest = draft["upstream_manifest"]
    manifest["requirements"]["mcu_specified"] = None
    candidates = select_hw_runner.select_board_candidates(manifest, limit=3)
    families = {candidate.get("chip_family") for candidate in candidates}
    preferred = {"rp2", "esp32", "esp32s2", "esp32s3", "esp32c3", "esp32c6"}
    if not candidates:
        raise AssertionError("no candidates returned for no-MCU manifest")
    if not families.issubset(preferred):
        raise AssertionError(f"no-MCU candidates include non-preferred families: {families - preferred}")
    if "rp2" not in families or not any(str(family).startswith("esp32") for family in families):
        raise AssertionError(f"no-MCU candidates should include both Pico/RP2 and ESP32 families: {families}")


def check_phase_complete_validation() -> None:
    success_path = SAMPLE_DIR / "phase_complete.select_hw.success.json"
    partial_path = SAMPLE_DIR / "phase_complete.select_hw.partial.json"
    compare_path = SAMPLE_DIR / "select_hw_manifest.after.json"
    for path in [success_path, partial_path]:
        expected = [item if item != "phase_complete.select_hw.success.json" else path.name for item in EXPECTED_ARTIFACTS]
        expected_args = [arg for item in expected for arg in ["--expected-artifact", item]]
        proc = run(
            [
                sys.executable,
                str(SELECT_HW_MANIFEST),
                "--validate-phase-complete",
                "--input",
                str(path),
                "--compare-manifest",
                str(compare_path),
                "--artifact-root",
                str(SAMPLE_DIR),
                "--board-root",
                str(BOARD_ROOT),
                "--strict-board-pins",
                *expected_args,
            ]
        )
        if proc.returncode != 0:
            raise AssertionError(f"phase_complete validation failed for {path.name}:\nstdout={proc.stdout}\nstderr={proc.stderr}")
        result = json.loads(proc.stdout)
        if result.get("status") != "ok":
            raise AssertionError(f"phase_complete validation did not return ok for {path.name}: {result}")


def check_phase_complete_requires_logs() -> None:
    phase_complete = load_json(SAMPLE_DIR / "phase_complete.select_hw.success.json")
    bad = json.loads(json.dumps(phase_complete))
    artifacts = bad["payload"]["artifacts"]
    for artifact in artifacts:
        if artifact.get("type") != "file_list":
            continue
        artifact["files"] = [
            item for item in artifact.get("files", []) if item.get("path") not in {"pin_assignment_log.md", "select_hw_phase_log.md"}
        ]
    expected_args = [arg for item in EXPECTED_ARTIFACTS for arg in ["--expected-artifact", item]]
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--validate-phase-complete",
            "--stdin",
            "--compare-manifest",
            str(SAMPLE_DIR / "select_hw_manifest.after.json"),
            "--artifact-root",
            str(SAMPLE_DIR),
            "--board-root",
            str(BOARD_ROOT),
            "--strict-board-pins",
            *expected_args,
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("phase_complete validation should fail when log artifacts are not declared")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "pin_assignment_log.md" not in joined or "select_hw_phase_log.md" not in joined:
        raise AssertionError(f"missing log artifacts were not reported: {result}")


def check_adc2_wifi_digital_warning() -> None:
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--input",
            str(SAMPLE_DIR / "select_hw_draft.json"),
            "--board-root",
            str(BOARD_ROOT),
        ]
    )
    if proc.returncode != 0:
        raise AssertionError(f"sample draft should pass while reporting ADC2 digital warning:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("warnings", []))
    for gpio in ["GPIO4", "GPIO5"]:
        if gpio not in joined:
            raise AssertionError(f"ADC2 digital warning should include {gpio}: {result}")
    if "digital signals" not in joined:
        raise AssertionError(f"ADC2 warning should explain digital use is allowed: {result}")


def check_strict_board_pin_validation() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    bad_draft = json.loads(json.dumps(draft))
    bad_draft["hardware_plan"]["pinout"][0]["gpio"] = 8
    bad_draft["hardware_plan"]["pinout"][0]["source"] = "auto_assigned"
    bad_draft["hardware_plan"]["pinout"][0]["notes"] = ""
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
            "--strict-board-pins",
        ],
        input_text=json.dumps(bad_draft, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("strict board pin validation should reject strapping/default-bus deviation")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []) + result.get("warnings", []))
    if "strapping" not in joined and "default" not in joined:
        raise AssertionError(f"strict board pin validation did not report expected issue: {result}")


def check_user_wiring_and_onboard_validation() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(draft, ensure_ascii=False),
    )
    if proc.returncode != 0:
        raise AssertionError(f"user_wiring sample should pass board validation:\nstdout={proc.stdout}\nstderr={proc.stderr}")

    occupied_draft = json.loads(json.dumps(draft))
    occupied_draft["hardware_plan"]["pinout"][3]["gpio"] = 8
    occupied_draft["hardware_plan"]["pinout"][3]["source"] = "auto_assigned"
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(occupied_draft, ensure_ascii=False),
    )
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []) + result.get("warnings", []))
    if "onboard peripheral" not in joined:
        raise AssertionError(f"onboard occupied pin warning was not reported: {result}")


def check_runner_bridge() -> None:
    proc = run([sys.executable, str(TEST_DIR / "run_local_mock_session.py")])
    combined = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise AssertionError(f"runner bridge failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    if "PHASE COMPLETE" not in combined:
        raise AssertionError(f"runner bridge did not reach phase_complete:\n{combined}")
    if "flash-mpy-firmware" not in combined:
        raise AssertionError(f"runner bridge did not emit flash-mpy-firmware next phase:\n{combined}")
    for path in ["pin_assignment_log.md", "select_hw_phase_log.md"]:
        if path not in combined:
            raise AssertionError(f"runner bridge phase_complete did not declare {path}:\n{combined}")


def check_plugin_manifest() -> None:
    if not PLUGIN_VALIDATOR.exists():
        print(f"[SKIP] plugin validator not found: {PLUGIN_VALIDATOR}")
        return
    proc = run([sys.executable, str(PLUGIN_VALIDATOR), str(SKILL_DIR)])
    if proc.returncode != 0:
        raise AssertionError(f"plugin validator failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")


def main() -> int:
    checks = [
        ("sample json", check_sample_json),
        ("manifest validation", check_manifest_validation),
        ("formatted output validation", check_formatted_output_validation),
        ("board unavailable sample", check_board_unavailable_sample),
        ("no mcu preferred candidates", check_no_mcu_preferred_candidates),
        ("phase_complete validation", check_phase_complete_validation),
        ("phase_complete requires logs", check_phase_complete_requires_logs),
        ("adc2 wifi digital warning", check_adc2_wifi_digital_warning),
        ("strict board pin validation", check_strict_board_pin_validation),
        ("user wiring and onboard validation", check_user_wiring_and_onboard_validation),
        ("runner bridge", check_runner_bridge),
        ("plugin manifest", check_plugin_manifest),
    ]
    for name, check in checks:
        check()
        print(f"[OK] {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
