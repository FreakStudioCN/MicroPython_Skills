#!/usr/bin/env python3
"""Regression tests for async package README capability checks."""

import ast
import contextlib
import importlib.util
import io
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
    def check_readme(self, code, readme_text, source_legacy_syntax=False):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            (package / "README.md").write_text(readme_text, encoding="utf-8")
            findings = []
            trees = {package / "code" / "driver.py": ast.parse(code)}
            CHECKER.readme_checks(package, trees, findings, False, source_legacy_syntax)
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

    def test_legacy_source_requires_readme_declaration(self):
        findings = self.check_readme(
            "from machine import I2C\n",
            "## API Async Matrix\n## Source Demo to Async Demo Mapping\n| Source sync step |\n## Hardware Acceptance\n",
            source_legacy_syntax=True,
        )
        self.assertIn("SOURCE_LEGACY_UNDECLARED", [item.code for item in findings])


class SourceCompatibilityChecksTest(unittest.TestCase):
    def test_legacy_source_requires_explicit_authorization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.py"
            path.write_text('print "legacy"\n', encoding="utf-8")
            findings = []
            context = {}
            tree = CHECKER.read_source_tree(path, findings, False, context)
            self.assertIsNone(tree)
            self.assertIn("SOURCE_LEGACY_SYNTAX", [item.code for item in findings])

    def test_authorized_legacy_source_is_parsed_in_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.py"
            path.write_text('print "legacy"\n', encoding="utf-8")
            findings = []
            context = {}
            tree = CHECKER.read_source_tree(path, findings, True, context)
            self.assertIsNotNone(tree)
            self.assertTrue(context["legacy_translated"])
            self.assertIn("SOURCE_LEGACY_SYNTAX", [item.code for item in findings])

    def test_async_delegate_to_blocking_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "import time\nclass Driver:\n    def configure(self):\n        time.sleep_ms(20)\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text(
                "class DriverAsync:\n    async def configure_async(self):\n        super().configure()\n",
                encoding="utf-8",
            )
            findings = []
            CHECKER.async_delegation_checks(
                source,
                code_dir,
                {facade: ast.parse(facade.read_text(encoding="utf-8"))},
                findings,
                False,
                {},
            )
            self.assertIn("ASYNC_DELEGATES_BLOCKING_SOURCE", [item.code for item in findings])

    def test_authorized_legacy_source_can_complete_with_partial_fidelity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source / "package.json").write_text('{"name": "source"}', encoding="utf-8")
            (source_code / "main.py").write_text(
                "import legacy\nfrom driver import Driver\ndevice = Driver()\n",
                encoding="utf-8",
            )
            (source_code / "driver.py").write_text("class Driver:\n    pass\n", encoding="utf-8")
            (source_code / "legacy.py").write_text('print "legacy"\n', encoding="utf-8")

            package = root / "outpkg"
            code = package / "code"
            examples = package / "examples"
            code.mkdir(parents=True)
            examples.mkdir()
            (package / "package.json").write_text(
                '{"name": "outpkg", "urls": [["driver_async.py", "code/driver_async.py"], ["legacy.py", "code/legacy.py"]]}',
                encoding="utf-8",
            )
            (package / "README.md").write_text(
                "## API Async Matrix\n## Source Demo to Async Demo Mapping\n| Source sync step |\n"
                "## Hardware Acceptance\n## Source Legacy Syntax Declaration\n"
                "Affected files: code/legacy.py\nStatus: package_fidelity_partial\n",
                encoding="utf-8",
            )
            (examples / "main_sync.py").write_bytes((source_code / "main.py").read_bytes())
            (code / "legacy.py").write_text("VALUE = 1\n", encoding="utf-8")
            (code / "driver_async.py").write_text(
                "class DriverAsync:\n    async def aclose(self):\n        pass\n",
                encoding="utf-8",
            )
            (code / "main.py").write_text(
                "import asyncio\nfrom driver_async import DriverAsync\n"
                "async def main():\n    device = DriverAsync()\n    try:\n        pass\n    finally:\n        await device.aclose()\n"
                "asyncio.run(main())\n",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                result = CHECKER.main([str(package), "--source", str(source), "--allow-source-legacy-syntax"])
            self.assertEqual(0, result)


if __name__ == "__main__":
    unittest.main()
