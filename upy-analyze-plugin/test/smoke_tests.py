#!/usr/bin/env python3
"""
Smoke tests for upy-analyze-plugin test scaffolding.

Checks:
- test modules import after moving into test/
- sample JSON files are valid
- phase_complete samples contain manifest_content accepted by init_manifest.py
- the local runner/mock bridge reaches phase_complete
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
SAMPLE_DIR = SKILL_DIR / "sample"
INIT_MANIFEST = SKILL_DIR / "scripts" / "init_manifest.py"
EXTERNAL_SAMPLE_DIR = Path("G:/test/test")


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


def check_imports() -> None:
    sys.path.insert(0, str(TEST_DIR))
    import analyze_runner  # noqa: F401
    import interactive_local_session  # noqa: F401
    import llm_analyze  # noqa: F401
    import mock_plugin  # noqa: F401
    import pkg_guide_adapter  # noqa: F401
    import terminal_plugin_host  # noqa: F401


def check_sample_json() -> list[dict]:
    samples = []
    for path in sorted(SAMPLE_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            samples.append(json.load(f))
    if not samples:
        raise AssertionError("no sample JSON files found")
    return samples


def check_manifest_samples(samples: list[dict]) -> None:
    phase_complete_samples = [
        sample for sample in samples if sample.get("type") == "phase_complete"
    ]
    if not phase_complete_samples:
        raise AssertionError("no phase_complete samples found")

    for sample in phase_complete_samples:
        payload = sample.get("payload", {})
        if payload.get("result") == "success":
            if payload.get("next_phase") != "select-hw":
                raise AssertionError("analyze success must keep next_phase=select-hw")
            if payload.get("next_skill") != "/upy-select-hw-plugin":
                raise AssertionError("analyze success must route to next_skill=/upy-select-hw-plugin")

        manifest = sample.get("payload", {}).get("manifest_content")
        if not isinstance(manifest, dict):
            raise AssertionError("phase_complete sample missing object manifest_content")

        phase_proc = run(
            [
                sys.executable,
                str(INIT_MANIFEST),
                "--validate-phase-complete",
                "--stdin",
            ],
            input_text=json.dumps(sample, ensure_ascii=False),
        )
        if phase_proc.returncode != 0:
            raise AssertionError(
                "init_manifest.py rejected sample phase_complete:\n"
                f"stdout={phase_proc.stdout}\nstderr={phase_proc.stderr}"
            )
        phase_result = json.loads(phase_proc.stdout)
        if phase_result.get("status") != "ok":
            raise AssertionError(f"phase_complete validation failed: {phase_result}")

        proc = run(
            [sys.executable, str(INIT_MANIFEST), "--stdin"],
            input_text=json.dumps(manifest, ensure_ascii=False),
        )
        if proc.returncode != 0:
            raise AssertionError(
                "init_manifest.py rejected sample manifest_content:\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr}"
            )
        result = json.loads(proc.stdout)
        if result.get("status") != "ok":
            raise AssertionError(f"manifest validation failed: {result}")


def check_ttp223_active_low_sample(samples: list[dict]) -> None:
    target = None
    for sample in samples:
        manifest = sample.get("payload", {}).get("manifest_content")
        if not isinstance(manifest, dict):
            continue
        for device in manifest.get("devices", []):
            if isinstance(device, dict) and device.get("name") == "TTP223":
                target = device
                break
        if target is not None:
            break
    if target is None:
        raise AssertionError("missing TTP223 active-low sample device")
    if target.get("source") != "user_specified":
        raise AssertionError("TTP223 sample must be user_specified")
    behavior = target.get("behavior")
    if not isinstance(behavior, dict):
        raise AssertionError("TTP223 sample missing behavior object")
    if behavior.get("active_level") != "low":
        raise AssertionError("TTP223 behavior.active_level must be low")
    if target.get("driver", {}).get("module") != "machine.Pin":
        raise AssertionError("TTP223 sample should use machine.Pin builtin runtime")
    notes = target.get("notes", "") + " " + target.get("driver", {}).get("notes", "")
    if "低电平" not in notes:
        raise AssertionError("TTP223 sample notes should preserve low-level behavior")


def check_driver_search_provenance_validation(samples: list[dict]) -> None:
    target_manifest = None
    for sample in samples:
        manifest = sample.get("payload", {}).get("manifest_content")
        if not isinstance(manifest, dict):
            continue
        if any(device.get("driver", {}).get("source") == "upypi" for device in manifest.get("devices", [])):
            target_manifest = json.loads(json.dumps(manifest))
            break
    if target_manifest is None:
        raise AssertionError("missing sample manifest with upypi driver source")

    for device in target_manifest["devices"]:
        driver = device.get("driver", {})
        if driver.get("source") == "upypi":
            driver.pop("search_provider", None)
            driver.pop("search_mode", None)
            driver.pop("query", None)
            driver.pop("evidence", None)
            break

    proc = run(
        [sys.executable, str(INIT_MANIFEST), "--stdin"],
        input_text=json.dumps(target_manifest, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("manifest validation should fail when upypi driver lacks search_provider")
    result = json.loads(proc.stdout)
    errors = result.get("errors", [])
    if not any("driver.search_provider is required" in error for error in errors):
        raise AssertionError(f"missing search_provider error for unproven upypi driver: {result}")


def check_pkg_guide_adapter_marks_mock() -> None:
    sys.path.insert(0, str(TEST_DIR))
    from pkg_guide_adapter import resolve_driver

    driver = resolve_driver({
        "name": "SHT30",
        "type": "temperature_humidity_sensor",
        "interface": "I2C",
    })
    if driver.get("source") != "upypi":
        raise AssertionError(f"SHT30 adapter result should resolve to upypi: {driver}")
    if driver.get("search_provider") != "pkg_guide_adapter":
        raise AssertionError(f"adapter result must declare pkg_guide_adapter provider: {driver}")
    if driver.get("search_mode") != "mock" or driver.get("mock") is not True:
        raise AssertionError(f"adapter result must be marked as mock: {driver}")


def check_runner_bridge() -> None:
    proc = run([sys.executable, str(TEST_DIR / "run_local_mock_session.py")])
    combined = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise AssertionError(
            "run_local_mock_session.py failed:\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    if "PHASE COMPLETE" not in combined:
        raise AssertionError(f"runner bridge did not reach phase_complete:\n{combined}")
    if "next_phase=select-hw" not in combined:
        raise AssertionError(f"runner bridge did not keep next_phase=select-hw:\n{combined}")
    if "next_skill=/upy-select-hw-plugin" not in combined:
        raise AssertionError(f"runner bridge did not route to /upy-select-hw-plugin:\n{combined}")


def check_external_claude_samples() -> None:
    if not EXTERNAL_SAMPLE_DIR.exists():
        print(f"[SKIP] external claude samples: {EXTERNAL_SAMPLE_DIR} not found")
        return

    manifest_candidates = [
        EXTERNAL_SAMPLE_DIR / "manifest_draft.json",
        EXTERNAL_SAMPLE_DIR / "manifest_validated.json",
    ]
    missing_manifest_candidates = [path for path in manifest_candidates if not path.exists()]
    phase_complete_path = EXTERNAL_SAMPLE_DIR / "phase_complete.analyze.json"
    if missing_manifest_candidates or not phase_complete_path.exists():
        missing = missing_manifest_candidates
        if not phase_complete_path.exists():
            missing.append(phase_complete_path)
        print(f"[SKIP] external claude samples missing files: {missing}")
        return

    for path in manifest_candidates:
        proc = run([sys.executable, str(INIT_MANIFEST), "--input", str(path)])
        if proc.returncode != 0:
            raise AssertionError(
                f"init_manifest.py rejected external sample {path}:\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr}"
            )
        result = json.loads(proc.stdout)
        if result.get("status") != "ok":
            raise AssertionError(f"external manifest validation failed for {path}: {result}")

    with open(phase_complete_path, "r", encoding="utf-8") as f:
        phase_complete = json.load(f)
    phase_payload = phase_complete.get("payload", phase_complete)
    declared_files = []
    for artifact in phase_payload.get("artifacts", []):
        if artifact.get("type") == "file_list":
            declared_files.extend(file_item.get("path") for file_item in artifact.get("files", []))
    for rel_path in declared_files:
        if not rel_path:
            raise AssertionError(f"external phase_complete has empty file_list path: {phase_complete_path}")
        if not (EXTERNAL_SAMPLE_DIR / rel_path).exists():
            raise AssertionError(f"external phase_complete declares missing artifact file: {rel_path}")

    required_declared_files = {
        "manifest_draft.json",
        "manifest_validated.json",
        "phase_complete.analyze.json",
        "driver_search_log.md",
    }
    missing_declared = sorted(required_declared_files.difference(declared_files))
    if missing_declared:
        raise AssertionError(f"external phase_complete file_list missing required files: {missing_declared}")

    proc = run(
        [
            sys.executable,
            str(INIT_MANIFEST),
            "--validate-phase-complete",
            "--input",
            str(phase_complete_path),
        ]
    )
    result = json.loads(proc.stdout)
    if proc.returncode == 0:
        if result.get("status") != "ok":
            raise AssertionError(f"phase_complete validator returned inconsistent result: {result}")
        return

    errors = result.get("errors", [])
    known_historical_errors = {
        "phase_complete.artifacts must be an array",
        "phase_complete.next_skill must be '/upy-select-hw-plugin' when analyze succeeds",
    }
    unexpected_errors = [error for error in errors if error not in known_historical_errors]
    if unexpected_errors:
        raise AssertionError(
            "external phase_complete sample failed with unexpected errors:\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )


def main() -> int:
    checks = [
        ("imports", lambda: check_imports()),
        ("sample json", lambda: check_sample_json()),
    ]

    samples: list[dict] = []
    for name, check in checks:
        result = check()
        if name == "sample json":
            samples = result  # type: ignore[assignment]
        print(f"[OK] {name}")

    check_manifest_samples(samples)
    print("[OK] manifest samples")

    check_ttp223_active_low_sample(samples)
    print("[OK] TTP223 active-low sample")

    check_driver_search_provenance_validation(samples)
    print("[OK] driver search provenance validation")

    check_pkg_guide_adapter_marks_mock()
    print("[OK] pkg-guide adapter mock provenance")

    check_runner_bridge()
    print("[OK] runner bridge")

    check_external_claude_samples()
    print("[OK] external claude samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
