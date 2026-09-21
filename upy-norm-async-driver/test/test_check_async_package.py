#!/usr/bin/env python3
"""Regression tests for async package README capability checks."""

import ast
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_async_package.py"
SPEC = importlib.util.spec_from_file_location("check_async_package", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


class ReadmeCapabilityChecksTest(unittest.TestCase):
    def check_readme(self, code, readme_text):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            (package / "README.md").write_text(readme_text, encoding="utf-8")
            findings = []
            trees = {package / "code" / "driver.py": ast.parse(code)}
            CHECKER.readme_checks(package, trees, findings, False)
            return findings

    def test_readme_uart_word_does_not_require_contract_without_runtime_uart(self):
        findings = self.check_readme(
            "from machine import I2C\n",
            "## API Async Matrix\n## Source Demo to Async Demo Mapping\n| Source sync step |\n## Hardware Acceptance\nUART is not used by this I2C driver.\n",
        )
        self.assertNotIn("UART_CONCURRENCY_DOC", [item.code for item in findings])

    def test_runtime_uart_requires_contract(self):
        findings = self.check_readme(
            "from machine import UART\n",
            "## API Async Matrix\n## Source Demo to Async Demo Mapping\n| Source sync step |\n## Hardware Acceptance\n",
        )
        self.assertIn("UART_CONCURRENCY_DOC", [item.code for item in findings])

    def test_unrelated_uart_attribute_does_not_require_contract(self):
        findings = self.check_readme(
            "class Metadata:\n    UART = 'not hardware'\n",
            "## API Async Matrix\n## Source Demo to Async Demo Mapping\n| Source sync step |\n## Hardware Acceptance\n",
        )
        self.assertNotIn("UART_CONCURRENCY_DOC", [item.code for item in findings])


if __name__ == "__main__":
    unittest.main()
