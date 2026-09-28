#!/usr/bin/env python3
"""Regression tests for the no_async_variant blocker report checker."""

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_async_blocker.py"
SPEC = importlib.util.spec_from_file_location("check_async_blocker", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


class AsyncBlockerChecksTest(unittest.TestCase):
    def write_report(self, path):
        path.write_text(
            "# Async Blocker Report\n\n## Source\n`driver`\n\n"
            "## Blocking Evidence\nStrict pulse timing has no yield boundary.\n\n"
            "## Re-evaluation Conditions\nA completion IRQ or FIFO-ready event is available.\n\n"
            "Status: `no_async_variant`\n",
            encoding="utf-8",
        )

    def run_checker(self, withdrawn_dir, report):
        with contextlib.redirect_stdout(io.StringIO()):
            return CHECKER.main([str(withdrawn_dir), "--report", str(report)])

    def test_withdrawn_directory_and_complete_report_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            withdrawn_dir = root / "driver_async"
            withdrawn_dir.mkdir()
            report = root / "driver_async_blocker.md"
            self.write_report(report)
            self.assertEqual(0, self.run_checker(withdrawn_dir, report))

    def test_runtime_file_in_withdrawn_directory_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            withdrawn_dir = root / "driver_async"
            withdrawn_dir.mkdir()
            (withdrawn_dir / "driver_async.py").write_text("pass\n", encoding="utf-8")
            report = root / "driver_async_blocker.md"
            self.write_report(report)
            self.assertEqual(1, self.run_checker(withdrawn_dir, report))
