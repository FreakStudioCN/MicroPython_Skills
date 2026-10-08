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
    def test_inherited_surface_and_signature_changes_have_actionable_findings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "driver.py").write_text(
                "from time import sleep as pause\nclass Driver:\n"
                "    def read(self):\n        pause(1)\n"
                "    def attach(self, channel, *, neutral_us=1500):\n        pass\n",
                encoding="utf-8",
            )
            output = root / "code" / "driver_async.py"
            tree = ast.parse("class DriverAsync(Driver):\n    async def attach_async(self, channel, neutral_us=1500):\n        return super().attach(channel, neutral_us)\n")
            findings = []
            CHECKER.async_delegation_checks(source, output.parent, {output: tree}, findings, False, {})
            codes = {item.code for item in findings}
            self.assertTrue({"ASYNC_EXPOSES_BLOCKING_SOURCE_API", "ASYNC_SOURCE_SIGNATURE_CHANGED", "ASYNC_SOURCE_ARGUMENT_BINDING"}.issubset(codes))

    def test_clean_up_can_map_to_declared_aclose(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            baseline = source / "main.py"
            baseline.write_text("from driver import Driver\ndevice = Driver()\ndevice.clean_up()\n", encoding="utf-8")
            (source / "driver.py").write_text("class Driver:\n    def clean_up(self): pass\n", encoding="utf-8")
            code = root / "code"
            code.mkdir()
            example = code / "main.py"
            example.touch()
            main_tree = ast.parse("from driver_async import DriverAsync\nasync def main():\n    device = DriverAsync()\n    await device.aclose()\n")
            for method, expected_missing in (("aclose", False), ("unrelated", True)):
                findings = []
                trees = {example: main_tree, code / "driver_async.py": ast.parse("class DriverAsync:\n    async def " + method + "(self): pass\n")}
                CHECKER.source_dependency_checks(source, code, trees, findings, baseline, example, main_tree, False, {})
                self.assertEqual(expected_missing, "EXAMPLE_DRIVER_API_FIDELITY" in {item.code for item in findings})

    def test_bounded_sync_helper_gets_review_not_forced_conversion(self):
        findings = self.async_example_findings(
            "from helper import Helper\nasync def main():\n    helper = Helper()\n    helper.sample()\n",
            {"helper.py": "class Helper:\n    def sample(self):\n        return self.bus.readfrom(1, 2)\n"},
        )
        matching = [item for item in findings if item.code == "ASYNC_EXAMPLE_SYNC_DRIVER"]
        self.assertEqual(["WARN"], [item.severity for item in matching])

    def test_sleep_import_aliases_and_unrelated_method(self):
        for statement, call in (("from time import sleep", "sleep"), ("from utime import sleep as pause", "pause"), ("import time as clock", "clock.sleep")):
            with self.subTest(statement=statement):
                tree = ast.parse(statement + "\nclass Driver:\n    def reset(self):\n        " + call + "(1)\n")
                self.assertIn("reset", CHECKER.source_methods_with_blocking_waits({Path("driver.py"): tree}))
                self.assertIn("reset", CHECKER.source_class_details({Path("driver.py"): tree})["Driver"]["blocked_methods"])
        tree = ast.parse("from asyncio import sleep\nasync def wait():\n    await sleep(1)\n")
        self.assertNotIn("wait", CHECKER.source_methods_with_blocking_waits({Path("driver.py"): tree}))

    def test_keyword_only_forwarding(self):
        method = ast.parse("def attach(self, channel, *, neutral_us=1500, reversed=False): pass").body[0]
        for call, expected in (("super().attach(1, 1500, False)", True), ("super().attach(1, neutral_us=1500, reversed=False)", False), ("super().attach(1, reverse=False)", True)):
            with self.subTest(call=call):
                findings = []
                CHECKER.source_forwarding_check(Path("driver.py"), ast.parse(call).body[0].value, method, True, findings)
                self.assertEqual(expected, bool(findings))

    def test_value_object_is_not_a_sync_driver(self):
        findings = self.async_example_findings(
            "from values import Effect\nasync def main():\n    effect = Effect(7)\n",
            {"values.py": "class Effect:\n    def __init__(self, value):\n        self.value = value\n"},
        )
        self.assertNotIn("ASYNC_EXAMPLE_SYNC_DRIVER", [item.code for item in findings])

    def test_async_suffix_and_lowercase_alias_do_not_hide_sync_driver(self):
        findings = self.async_example_findings(
            "from driver_async import DriverAsync as device\nasync def main():\n    driver = device()\n    driver.read()\n",
            {"driver_async.py": "from time import sleep\nclass DriverAsync:\n    def read(self):\n        sleep(1)\n"},
        )
        self.assertIn("ASYNC_EXAMPLE_SYNC_DRIVER", [item.code for item in findings])

    def async_example_findings(self, main_source, runtime_sources):
        with tempfile.TemporaryDirectory() as temp_dir:
            code_dir = Path(temp_dir) / "code"
            code_dir.mkdir()
            main = code_dir / "main.py"
            main.write_text(main_source, encoding="utf-8")
            trees = {main: ast.parse(main_source)}
            for name, source in runtime_sources.items():
                path = code_dir / name
                path.write_text(source, encoding="utf-8")
                trees[path] = ast.parse(source)
            findings = []
            CHECKER.async_example_checks(main, code_dir, trees, findings)
            return findings

    def test_async_example_constructing_sync_driver_is_rejected(self):
        findings = self.async_example_findings(
            "from sync_driver import Driver\nasync def main():\n    device = Driver()\n    return device.read()\n",
            {
                "sync_driver.py": "from time import sleep\nclass Driver:\n    def read(self):\n        sleep(1)\n",
                "driver_async.py": "class DriverAsync:\n    async def read_async(self):\n        return 1\n",
            },
        )
        self.assertIn("ASYNC_EXAMPLE_SYNC_DRIVER", [item.code for item in findings])

    def test_async_example_constructing_async_driver_is_allowed(self):
        findings = self.async_example_findings(
            "from driver_async import DriverAsync\nasync def main():\n    device = DriverAsync()\n    return await device.read_async()\n",
            {"driver_async.py": "class DriverAsync:\n    async def read_async(self):\n        return 1\n"},
        )
        self.assertNotIn("ASYNC_EXAMPLE_SYNC_DRIVER", [item.code for item in findings])

    def main_fidelity_findings(self, main_source, driver_source):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            code_dir = package / "code"
            code_dir.mkdir()
            main = code_dir / "main.py"
            driver = code_dir / "driver_async.py"
            main.write_text(main_source, encoding="utf-8")
            driver.write_text(driver_source, encoding="utf-8")
            findings = []
            CHECKER.main_fidelity(
                package,
                None,
                code_dir,
                {main: ast.parse(main_source), driver: ast.parse(driver_source)},
                findings,
            )
            return findings

    def test_main_constructor_and_cleanup_are_not_a_business_call(self):
        findings = self.main_fidelity_findings(
            "import asyncio\nfrom driver_async import DriverAsync\n"
            "async def main():\n    device = DriverAsync()\n    try:\n        pass\n    finally:\n        await device.aclose()\nasyncio.run(main())\n",
            "class DriverAsync:\n    async def aclose(self):\n        pass\n",
        )
        self.assertIn("MAIN_NO_DRIVER_BUSINESS_CALL", [item.code for item in findings])

    def test_main_mapped_driver_business_call_is_accepted(self):
        findings = self.main_fidelity_findings(
            "import asyncio\nfrom driver_async import DriverAsync\n"
            "async def main():\n    device = DriverAsync()\n    try:\n        await device.read_async()\n    finally:\n        await device.aclose()\nasyncio.run(main())\n",
            "class DriverAsync:\n    async def read_async(self):\n        return 1\n    async def aclose(self):\n        pass\n",
        )
        self.assertNotIn("MAIN_NO_DRIVER_BUSINESS_CALL", [item.code for item in findings])

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

    def test_facade_inheriting_blocking_source_init_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "import time\nclass Driver:\n    def __init__(self):\n        time.sleep_ms(20)\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class DriverAsync(Driver):\n    def __init__(self):\n        super().__init__()\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(source, code_dir, {facade: ast.parse(facade.read_text(encoding="utf-8"))}, findings, False, {})
            self.assertIn("ASYNC_INHERITS_BLOCKING_INIT", [item.code for item in findings])

    def test_async_facade_implicitly_inheriting_blocking_init_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "import time\nclass Driver:\n    def __init__(self):\n        time.sleep_ms(20)\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class DriverAsync(Driver):\n    async def read_async(self):\n        return 1\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(source, code_dir, {facade: ast.parse(facade.read_text(encoding="utf-8"))}, findings, False, {})
            self.assertIn("ASYNC_IMPLICITLY_INHERITS_BLOCKING_INIT", [item.code for item in findings])

    def test_async_facade_calling_inherited_blocking_method_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "import time\nclass Driver:\n    def read(self):\n        time.sleep_ms(20)\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class DriverAsync(Driver):\n    async def read_async(self):\n        return self.read()\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(source, code_dir, {facade: ast.parse(facade.read_text(encoding="utf-8"))}, findings, False, {})
            self.assertIn("ASYNC_CALLS_INHERITED_BLOCKING_METHOD", [item.code for item in findings])

    def test_async_facade_directly_calling_source_class_blocking_method_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "import time\nclass Driver:\n    def read(self):\n        time.sleep_ms(20)\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class DriverAsync(Driver):\n    async def read_async(self):\n        return Driver.read(self)\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(source, code_dir, {facade: ast.parse(facade.read_text(encoding="utf-8"))}, findings, False, {})
            self.assertIn("ASYNC_CALLS_SOURCE_CLASS_BLOCKING_METHOD", [item.code for item in findings])

    def test_async_facade_inheriting_unsafe_source_irq_callback_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "class Driver:\n    def __init__(self, pin, i2c):\n        self.i2c = i2c\n        pin.irq(handler=self._irq)\n    def _irq(self, pin):\n        self._process()\n    def _process(self):\n        return self.i2c.readfrom(1, 1)\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class DriverAsync(Driver):\n    async def read_async(self):\n        return 1\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(source, code_dir, {facade: ast.parse(facade.read_text(encoding="utf-8"))}, findings, False, {})
            self.assertIn("ASYNC_INHERITS_UNSAFE_CALLBACK", [item.code for item in findings])

    def test_facade_calling_source_property_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text("class Driver:\n    @property\n    def mode(self):\n        return 1\n", encoding="utf-8")
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class DriverAsync(Driver):\n    async def read_mode_async(self):\n        return super().mode()\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(source, code_dir, {facade: ast.parse(facade.read_text(encoding="utf-8"))}, findings, False, {})
            self.assertIn("ASYNC_CALLS_SOURCE_PROPERTY", [item.code for item in findings])

    def test_super_delegate_uses_the_actual_source_base_class(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "import time\nclass Blocking:\n    def configure(self):\n        time.sleep_ms(20)\nclass Safe:\n    def configure(self):\n        return 1\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class SafeAsync(Safe):\n    async def configure_async(self):\n        return super().configure()\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(source, code_dir, {facade: ast.parse(facade.read_text(encoding="utf-8"))}, findings, False, {})
            self.assertNotIn("ASYNC_DELEGATES_BLOCKING_SOURCE", [item.code for item in findings])

    def test_async_example_directly_reading_blocking_source_property_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "import time\nclass Driver:\n    @property\n    def serial(self):\n        time.sleep_ms(25)\n        return 1\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class DriverAsync(Driver):\n    async def serial_async(self):\n        return 1\n", encoding="utf-8")
            main = code_dir / "main.py"
            main.write_text("async def main():\n    sensor = DriverAsync()\n    return sensor.serial\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(
                source,
                code_dir,
                {facade: ast.parse(facade.read_text(encoding="utf-8")), main: ast.parse(main.read_text(encoding="utf-8"))},
                findings,
                False,
                {},
            )
            self.assertIn("ASYNC_ACCESSES_BLOCKING_SOURCE_PROPERTY", [item.code for item in findings])

    def test_explicit_async_property_mapping_is_allowed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source_code = source / "code"
            source_code.mkdir(parents=True)
            (source_code / "driver.py").write_text(
                "import time\nclass Driver:\n    @property\n    def serial(self):\n        time.sleep_ms(25)\n        return 1\n",
                encoding="utf-8",
            )
            package = Path(temp_dir) / "package"
            code_dir = package / "code"
            code_dir.mkdir(parents=True)
            facade = code_dir / "driver_async.py"
            facade.write_text("class DriverAsync(Driver):\n    async def serial_async(self):\n        return 1\n", encoding="utf-8")
            main = code_dir / "main.py"
            main.write_text("async def main():\n    sensor = DriverAsync()\n    return await sensor.serial_async()\n", encoding="utf-8")
            findings = []
            CHECKER.async_delegation_checks(
                source,
                code_dir,
                {facade: ast.parse(facade.read_text(encoding="utf-8")), main: ast.parse(main.read_text(encoding="utf-8"))},
                findings,
                False,
                {},
            )
            self.assertNotIn("ASYNC_ACCESSES_BLOCKING_SOURCE_PROPERTY", [item.code for item in findings])

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
                "class DriverAsync:\n    async def read_async(self):\n        return 1\n    async def aclose(self):\n        pass\n",
                encoding="utf-8",
            )
            (code / "main.py").write_text(
                "import asyncio\nfrom driver_async import DriverAsync\n"
                "async def main():\n    device = DriverAsync()\n    try:\n        await device.read_async()\n    finally:\n        await device.aclose()\n"
                "asyncio.run(main())\n",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                result = CHECKER.main([str(package), "--source", str(source), "--allow-source-legacy-syntax"])
            self.assertEqual(0, result)


if __name__ == "__main__":
    unittest.main()
