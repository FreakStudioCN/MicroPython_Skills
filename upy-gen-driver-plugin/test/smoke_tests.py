#!/usr/bin/env python3
"""Smoke tests for upy-gen-driver-plugin resources."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def assert_ok(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_samples_validate() -> None:
    validator = ROOT / "scripts" / "validate_phase_complete.py"
    for name in (
        "phase_complete.upy_gen_driver_plugin.partial.no_device.json",
        "phase_complete.upy_gen_driver_plugin.success.json",
    ):
        result = run([sys.executable, str(validator), "--input", str(ROOT / "sample" / name)])
        assert_ok(result.returncode == 0, f"{name} failed validation: {result.stdout} {result.stderr}")


def test_session_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "sessions" / "smoke"
        script = ROOT / "scripts" / "update_session_state.py"
        result = run([
            sys.executable,
            str(script),
            "--session-dir",
            str(session_dir),
            "--session-id",
            "smoke",
            "--checkpoint",
            "started",
            "--step",
            "start",
            "--status",
            "running",
            "--idempotency-key",
            "upy-gen-driver-plugin:smoke:start:v1",
        ])
        assert_ok(result.returncode == 0, result.stdout + result.stderr)
        result = run([sys.executable, str(script), "--session-dir", str(session_dir), "--check"])
        assert_ok(result.returncode == 0, result.stdout + result.stderr)


def test_convert_arduino() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "demo.ino"
        out = Path(tmp) / "mapping.json"
        src.write_text(
            "#include <Wire.h>\n"
            "const int ADDR = 0x44;\n"
            "void setup() { Wire.begin(); }\n"
            "void loop() { Wire.beginTransmission(ADDR); Wire.endTransmission(); delay(10); }\n",
            encoding="utf-8",
        )
        result = run([
            sys.executable,
            str(ROOT / "scripts" / "convert_arduino.py"),
            "--input",
            str(src),
            "--output",
            str(out),
            "--json-summary",
        ])
        assert_ok(result.returncode == 0, result.stdout + result.stderr)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert_ok(data["api_matches"], "expected API matches")


def test_mock_session() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run([
            sys.executable,
            str(ROOT / "test" / "run_local_mock_session.py"),
            "--output-root",
            tmp,
            "--session-id",
            "mock-smoke",
        ])
        assert_ok(result.returncode == 0, result.stdout + result.stderr)


def main() -> int:
    tests = [test_samples_validate, test_session_state, test_convert_arduino, test_mock_session]
    failures: list[str] = []
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
