# Device MicroPython Unittest Subset

Read this before generating device-side tests under `device/tests/` or compatibility `test/device/`.

## Source Basis

- MicroPython official docs describe the library set as reduced for constrained devices, and ports/firmware may omit modules or functions.
- `micropython-lib/python-stdlib/unittest/unittest/__init__.py` is the reference implementation for the MicroPython `unittest` package used by generated device tests.

## Device Test Goal

Device tests are real MicroPython `unittest` tests, not CPython-only tests and not import-only smoke files. Treat generated device tests primarily as interface/contract tests: validate device-runnable protocol, state shape, driver adapter mock APIs, config constants, task signatures/return fields, session/state interfaces, and lightweight filesystem behavior without requiring PC-only modules.

Keep heavy behavioral coverage, state-machine matrix tests, cloud mocks, and edge-case logic in `test/pc/`. Keep device tests small enough to run with `mpremote run` or after copying to the board.

## Layout

Supported generated layouts:

```text
project/device/tests/test_*.py
project/test/device/test_*.py
```

Generate new real device-side tests under `project/device/tests/test_*.py` by default. Keep `project/test/device/test_*.py` only as a compatibility location for older sessions or projects that already use it. The checker scans both layouts, and file content should stay portable between both layouts.

## Allowed Imports

Prefer:

```python
import gc
import sys
import unittest

try:
    import ujson as json
except ImportError:
    import json
```

Allowed with care: `os` with `uos` fallback, `time`, `utime`, project local modules, and generated `firmware/lib` modules known to exist on the board.

Avoid in device tests:

```text
pathlib, tempfile, unittest.mock, mock, pytest, typing, dataclasses,
logging, argparse, subprocess, requests, asyncio
```

For path setup, use simple relative paths:

```python
import sys
sys.path.insert(0, "firmware")
sys.path.insert(0, "..")
sys.path.insert(0, "../firmware")
sys.path.insert(0, "../../firmware")
```

Do not use `Path(__file__)` in device tests.

## Supported Unittest API

The generated-device-test allowlist follows the methods present in the MicroPython `unittest` implementation:

```text
unittest.TestCase
unittest.main
unittest.skip
unittest.skipIf
unittest.skipUnless
unittest.expectedFailure
unittest.TestSuite
unittest.TextTestRunner
```

Allowed `TestCase` helpers:

```text
setUp, tearDown, setUpClass, tearDownClass, runTest,
addCleanup, doCleanups, subTest, skipTest, fail
```

Allowed assertions:

```text
assertEqual, assertNotEqual,
assertLessEqual, assertGreaterEqual,
assertAlmostEqual, assertNotAlmostEqual,
assertIs, assertIsNot, assertIsNone, assertIsNotNone,
assertTrue, assertFalse,
assertIn, assertIsInstance,
assertRaises, assertWarns
```

Do not generate CPython-only assertions:

```text
assertLess, assertGreater, assertNotIn,
assertRegex, assertNotRegex, assertRaisesRegex, assertWarnsRegex,
assertListEqual, assertDictEqual, assertTupleEqual, assertSetEqual,
assertCountEqual, assertMultiLineEqual, assertLogs, assertNoLogs
```

## Test Shape

Use a plain `unittest.TestCase` class and call `unittest.main()` at the end:

```python
import gc
gc.collect()

import sys
sys.path.insert(0, "..")
sys.path.insert(0, "../firmware")

import unittest

try:
    import ujson as json
except ImportError:
    import json

from protocol import parse_message


class TestProtocol(unittest.TestCase):
    def test_parse_normal_message(self):
        msg = parse_message('{"state":"ok","value":3}')
        self.assertIsInstance(msg, dict)
        self.assertEqual(msg["state"], "ok")
        self.assertIn("value", msg)
        self.assertFalse(bool(msg.get("error")))

    def test_parse_invalid_message(self):
        self.assertIsNone(parse_message("not json"))


unittest.main()
```

For generated driver adapter tests, avoid touching real hardware unless the user requested a hardware smoke test. Use mocks or pure adapter helpers:

```python
import gc
gc.collect()

import sys
sys.path.insert(0, "../firmware")
sys.path.insert(0, "../../firmware")

import unittest

from drivers.status_driver.mock import MockStatusOutput
from tasks.business_task import business_tick


class TestBusinessDevice(unittest.TestCase):
    def test_output_adapter_contract(self):
        output = MockStatusOutput()
        result = business_tick(output)
        self.assertTrue(result["ok"])
        self.assertIn("[task]", output.messages[0])

    def test_missing_output_contract(self):
        result = business_tick(None)
        self.assertIsNotNone(result)
        self.assertTrue(result["missing_output"])

    def test_driver_exception_contract(self):
        output = MockStatusOutput(fail=True)
        result = business_tick(output)
        self.assertFalse(result["ok"])
        self.assertIn("error", result)


unittest.main()
```

## Hardware Smoke Tests

Only generate hardware-touching device tests when the manifest already confirms the hardware and pins. Keep them opt-in and non-destructive:

- One sensor read, one bus scan, or one output toggle.
- No infinite loops.
- No Wi-Fi credential use.
- No paid cloud API call.
- Use `setUp`/`tearDown` to restore output state when possible.
- If the test needs a user-connected fixture, mark it as a deploy/manual test in `generate_plan.json`.

## Quality Gate Expectations

`check_device_unittest_subset.py` must pass before `phase_complete.result=success`.

The gate should check both `test/device/test*.py` and `device/tests/test*.py`, reject unsupported CPython-only assertion methods, reject unsupported `unittest.*` helpers, and warn when a device test file does not call `unittest.main()`.
