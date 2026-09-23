#!/usr/bin/env python3
"""Regression tests for async runtime-role and callback audit behavior."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DRIVER = load_module("async_driver_checker", ROOT / "scripts" / "check_async_driver.py")
SEMANTICS = load_module("async_semantics_checker", ROOT / "scripts" / "check_async_semantics.py")


class CallbackAuditTest(unittest.TestCase):
    def findings_for(self, source):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "driver.py"
            path.write_text(source, encoding="utf-8")
            return DRIVER.check_file(path)

    def test_interrupt_named_regular_method_is_not_treated_as_irq(self):
        findings = self.findings_for(
            "class Device:\n"
            "    def clear_interrupt(self):\n"
            "        self.i2c.writeto_mem(1, 2, b'')\n"
        )
        self.assertNotIn("IRQ_IO", [item.code for item in findings])

    def test_registered_irq_callback_is_checked(self):
        findings = self.findings_for(
            "class Device:\n"
            "    def start(self):\n"
            "        self.pin.irq(handler=self._irq_handler)\n"
            "    def _irq_handler(self, pin):\n"
            "        self.i2c.readfrom_mem(1, 2, 1)\n"
        )
        self.assertIn("IRQ_IO", [item.code for item in findings])


class RuntimeRolesTest(unittest.TestCase):
    def audit(self, files, roles):
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir)
            code = package / "code"
            code.mkdir()
            for relative, content in files.items():
                path = package / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            (package / "async_runtime_roles.json").write_text(roles, encoding="utf-8")
            findings = []
            audit_files = SEMANTICS.audit_files(package)
            runtime_roles = SEMANTICS.load_runtime_roles(package, [path for path in audit_files if path.is_relative_to(code)], findings)
            trees = {path: SEMANTICS.parse_tree(path, findings) for path in audit_files}
            SEMANTICS.compatibility_reachability(package, trees, runtime_roles, findings)
            for path, tree in trees.items():
                if tree is not None:
                    SEMANTICS.audit_tree(path, tree, findings, runtime_roles.get(path, "async_runtime"))
            return findings

    def test_unreachable_sync_compatibility_module_is_allowed(self):
        findings = self.audit(
            {
                "code/main.py": "import asyncio\nasync def main():\n    try:\n        pass\n    finally:\n        pass\nasyncio.run(main())\n",
                "code/compat_sync.py": "import time\ndef close():\n    time.sleep(1)\n",
            },
            '{"roles": {"compat_sync.py": "sync_compatibility"}}',
        )
        self.assertNotIn("LIFECYCLE_BLOCKING_CALL", [item.code for item in findings])
        self.assertNotIn("SYNC_COMPAT_REACHABLE", [item.code for item in findings])

    def test_async_runtime_cannot_import_sync_compatibility_module(self):
        findings = self.audit(
            {
                "code/main.py": "import asyncio\nimport compat_sync\nasync def main():\n    try:\n        pass\n    finally:\n        pass\nasyncio.run(main())\n",
                "code/compat_sync.py": "import time\ndef close():\n    time.sleep(1)\n",
            },
            '{"roles": {"compat_sync.py": "sync_compatibility"}}',
        )
        self.assertIn("SYNC_COMPAT_REACHABLE", [item.code for item in findings])

    def test_transitive_sync_compatibility_import_is_rejected(self):
        findings = self.audit(
            {
                "code/main.py": "import asyncio\nimport facade\nasync def main():\n    try:\n        pass\n    finally:\n        pass\nasyncio.run(main())\n",
                "code/facade.py": "import compat_sync\n",
                "code/compat_sync.py": "import time\ndef close():\n    time.sleep(1)\n",
            },
            '{"roles": {"compat_sync.py": "sync_compatibility"}}',
        )
        self.assertIn("SYNC_COMPAT_REACHABLE", [item.code for item in findings])


class AsyncApiSemanticsTest(unittest.TestCase):
    def findings_for(self, source):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "driver.py"
            path.write_text(source, encoding="utf-8")
            findings = []
            tree = SEMANTICS.parse_tree(path, findings)
            SEMANTICS.audit_tree(path, tree, findings, "async_runtime")
            return findings

    def test_dynamic_public_async_signature_and_duplicate_are_rejected(self):
        findings = self.findings_for(
            "class Driver:\n"
            "    async def read_async(self, *args, **kwargs):\n        pass\n"
            "    async def read_async(self, value):\n        return value\n"
        )
        codes = [item.code for item in findings]
        self.assertIn("PUBLIC_ASYNC_DYNAMIC_SIGNATURE", codes)
        self.assertIn("DUPLICATE_PUBLIC_DEFINITION", codes)

    def test_property_getter_and_setter_are_not_duplicate_definitions(self):
        findings = self.findings_for(
            "class Driver:\n"
            "    @property\n    def mode(self):\n        return 1\n"
            "    @mode.setter\n    def mode(self, value):\n        pass\n"
        )
        self.assertNotIn("DUPLICATE_PUBLIC_DEFINITION", [item.code for item in findings])

    def test_unbounded_async_poll_is_rejected_but_worker_is_allowed(self):
        findings = self.findings_for(
            "import asyncio\nclass Driver:\n"
            "    async def read_async(self):\n        while not self.ready:\n            await asyncio.sleep_ms(5)\n"
            "    async def worker(self):\n        while self.running:\n            await asyncio.sleep_ms(5)\n"
        )
        codes = [item.code for item in findings]
        self.assertIn("ASYNC_POLL_NO_TIMEOUT", codes)
        self.assertEqual(1, codes.count("ASYNC_POLL_NO_TIMEOUT"))

    def test_runtime_module_must_be_bound(self):
        findings = self.findings_for("async def read_async():\n    return time.ticks_ms()\n")
        self.assertIn("RUNTIME_MODULE_UNBOUND", [item.code for item in findings])

if __name__ == "__main__":
    unittest.main()
