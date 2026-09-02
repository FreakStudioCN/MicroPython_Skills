"""check_generated_semantics negative cases, lifted out of smoke_tests.py.

Its own module for room: smoke_tests.py had grown past the point where another case could be added
to it, and these all interrogate one script, so they belong together. Registered from
smoke_tests.main() like every other suite.

The shared fixtures (ROOT, run_cmd, make_project, ...) are imported INSIDE the functions on purpose:
smoke_tests imports this module at the top, so importing it back at module level would be a cycle.
"""

import ast
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def assert_generated_semantics_negative_cases() -> None:
    from smoke_tests import ROOT, load_json, make_project, run_cmd, set_mcu_model  # noqa: F401 - see module docstring
    import json, tempfile  # noqa: E401 - kept beside the deferred import above
    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "dialog_task.py"
        task.write_text(
            "async def dialog_tick(pir, touch):\n"
            "    state = 'idle'\n"
            "    last_trigger = 0\n"
            "    return {'state': state, 'last_trigger': last_trigger}\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SEMANTIC_STATE_RESETS_EACH_TICK" not in stdout:
            raise AssertionError("semantic check must reject per-tick state reset")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "voice_task.py"
        task.write_text(
            "async def voice_interact(mic, wifi):\n"
            "    audio_data = mic.read_samples(16000)\n"
            "    _ = audio_data\n"
            "    return wifi.http_post('https://example.invalid', json_data={'audio': 'base64_placeholder'})\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        for expected in (
            "SEMANTIC_PLACEHOLDER_IN_RUNTIME",
            "SEMANTIC_ASYNC_BLOCKING_IO",
            "SEMANTIC_ASYNC_SYNC_IO",
            "SEMANTIC_DATA_READ_UNUSED",
        ):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"semantic check must reject {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "wifi_task.py"
        task.write_text(
            "async def wifi_tick(wifi):\n"
            "    wifi.connect('ssid', 'password')\n"
            "    return True\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SEMANTIC_ASYNC_BLOCKING_IO" not in stdout:
            raise AssertionError("semantic check must reject blocking connect() inside async tasks")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "hidden_blocking_task.py"
        task.write_text(
            "async def async_record(mic):\n"
            "    _record = getattr(mic, 'record')\n"
            "    return _record(5000)\n"
            "\n"
            "async def async_play(speaker, audio):\n"
            "    return speaker.__getattribute__('play')(audio)\n"
            "\n"
            "async def async_lambda_record(mic):\n"
            "    _record = lambda duration_ms: mic.record(duration_ms)\n"
            "    return _record(5000)\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        for expected in (
            "SEMANTIC_ASYNC_DYNAMIC_BLOCKING_LOOKUP",
            "SEMANTIC_ASYNC_DYNAMIC_BLOCKING_CALL",
            "SEMANTIC_ASYNC_BLOCKING_LAMBDA",
        ):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"semantic check must reject dynamically hidden blocking calls {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        task = project / "firmware" / "tasks" / "wrapper_blocking_task.py"
        task.write_text(
            "def record_adapter(mic):\n"
            "    return mic.record(5000)\n"
            "\n"
            "async def voice_tick(mic):\n"
            "    return record_adapter(mic)\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SEMANTIC_ASYNC_BLOCKING_WRAPPER" not in stdout:
            raise AssertionError(f"semantic check must reject async calls to blocking sync wrappers: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="async")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from drivers.inmp441_driver import create_inmp441\n"
            "from drivers.max98357_driver import create_max98357\n"
            "mic = create_inmp441()\n"
            "amp = create_max98357()\n",
            encoding="utf-8",
        )
        manifest = load_json(project / "project-manifest.json")
        manifest["phase"] = "generate"
        manifest["generate"] = {}
        (project / "project-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SEMANTIC_SHARED_I2S_WITHOUT_RESOURCE_PLAN" not in stdout:
            raise AssertionError("semantic check must require resource_plan for shared I2S")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        manifest = load_json(project / "project-manifest.json")
        manifest["devices"] = [
            {"name": "WS2812", "interface": "GPIO"},
            {"name": "MAX98357", "interface": "I2S"},
        ]
        manifest["pinout"] = [
            {"device": "MAX98357", "pin_name": "BCLK", "gpio": "8", "type": "i2s_bck", "bus": "i2s0"},
            {"device": "MAX98357", "pin_name": "LRC", "gpio": "9", "type": "i2s_ws", "bus": "i2s0"},
            {"device": "WS2812", "pin_name": "DIN", "gpio": "21", "type": "gpio_out"},
        ]
        (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from machine import I2C, Pin\n"
            "i2c0 = I2C(0, scl=Pin(9), sda=Pin(8), freq=400000)\n"
            "_ = i2c0.scan()\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        for expected in ("SEMANTIC_UNDECLARED_I2C_SCAN", "SEMANTIC_I2C_PIN_CONFLICT"):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"semantic check must reject generated I2C misuse {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from machine import Timer\n"
            "from lib.scheduler.timer_sched import Scheduler\n"
            "tim = Timer(-1)\n"
            "sc = Scheduler()\n"
            "sc.register(lambda: None)\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        for expected in ("SCHEDULER_TIMER_INVALID_FOR_PORT", "SCHEDULER_API_METHOD_MISSING"):
            if rc == 0 or expected not in stdout:
                raise AssertionError(f"semantic check must reject scheduler issue {expected}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "import sys\n"
            "import time\n"
            "from lib.scheduler.timer_sched import Scheduler\n"
            "from lib import logger\n"
            "def _on_scheduler_error(tid, exc):\n"
            "    sys.print_exception(exc)\n"
            "    logger.exception(exc, '[t=%dms] task failed' % time.ticks_ms())\n"
            "def tick(): pass\n"
            "sc = Scheduler(timer_id=0, error_cb=_on_scheduler_error)\n"
            "sc.schedule_every(tick, 100)\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_API_METHOD_MISSING" not in stdout:
            raise AssertionError(f"semantic check must reject any missing Scheduler method: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        (project / "firmware" / "lib" / "scheduler" / "timer_sched.py").write_text(
            "from machine import Timer\n\n"
            "class Scheduler:\n"
            "    def __init__(self, timer_id=-1, tick_ms=100):\n"
            "        self._timer = Timer(timer_id)\n"
            "    def add_task(self, callback, interval_ms, name=None): return name\n",
            encoding="utf-8",
        )
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from lib.scheduler.timer_sched import Scheduler\n"
            "def tick(): pass\n"
            "sc = Scheduler(timer_id=-1)\n"
            "sc.add_task(tick, 100, name='tick')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" not in stdout:
            raise AssertionError(f"semantic check must reject Scheduler(timer_id=-1): {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        (project / "firmware" / "lib" / "scheduler" / "timer_sched.py").write_text(
            "from machine import Timer\n\n"
            "class Scheduler:\n"
            "    def __init__(self, timer_id=-1, tick_ms=100):\n"
            "        self._timer = Timer(timer_id)\n"
            "    def add_task(self, callback, interval_ms, name=None): return name\n",
            encoding="utf-8",
        )
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from lib.scheduler.timer_sched import Scheduler\n"
            "def tick(): pass\n"
            "sc = Scheduler()\n"
            "sc.add_task(tick, 100, name='tick')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" not in stdout:
            raise AssertionError(f"semantic check must reject Scheduler() when default timer_id=-1: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        (project / "firmware" / "lib" / "scheduler" / "timer_sched.py").write_text(
            "from machine import Timer\n\n"
            "class Scheduler:\n"
            "    def __init__(self, timer_id=-1, tick_ms=100, idle_cb=None, error_cb=None):\n"
            "        self._timer = Timer(timer_id)\n"
            "        self._error_cb = error_cb\n"
            "    def add_task(self, callback, interval_ms, name=None): return name\n",
            encoding="utf-8",
        )
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "import sys\n"
            "import time\n"
            "from lib.scheduler.timer_sched import Scheduler\n"
            "from lib import logger\n"
            "def _on_scheduler_error(tid, exc):\n"
            "    sys.print_exception(exc)\n"
            "    logger.exception(exc, '[t=%dms] task failed' % time.ticks_ms())\n"
            "def tick(): pass\n"
            "sc = Scheduler(timer_id=0, error_cb=_on_scheduler_error)\n"
            "sc.add_task(tick, 100, name='tick')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc != 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" in stdout:
            raise AssertionError(f"semantic check must allow ESP32 main.py with explicit timer_id=0 while scheduler default is -1: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        set_mcu_model(project, "STM32")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from lib.scheduler.timer_sched import Scheduler\n"
            "def tick(): pass\n"
            "sc = Scheduler(timer_id=-1)\n"
            "sc.add_task(tick, 100, name='tick')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" not in stdout:
            raise AssertionError(f"semantic check must reject virtual Timer(-1) on general hardware-timer ports: {stdout}")

    for model in ("Raspberry Pi Pico W", "Zephyr"):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            make_project(project, mode="timer")
            set_mcu_model(project, model)
            main_py = project / "firmware" / "main.py"
            main_py.write_text(
                "import sys\n"
                "import time\n"
                "from lib.scheduler.timer_sched import Scheduler\n"
                "from lib import logger\n"
                "def _on_scheduler_error(tid, exc):\n"
                "    sys.print_exception(exc)\n"
                "    logger.exception(exc, '[t=%dms] task failed' % time.ticks_ms())\n"
                "def tick(): pass\n"
                "sc = Scheduler(timer_id=-1, error_cb=_on_scheduler_error)\n"
                "sc.add_task(tick, 100, name='tick')\n",
                encoding="utf-8",
            )
            rc, stdout, _stderr = run_cmd(
                [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
            )
            if rc != 0 or "SCHEDULER_TIMER_INVALID_FOR_PORT" in stdout:
                raise AssertionError(f"semantic check must allow virtual Timer(-1) on {model}: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        conf_py = project / "firmware" / "conf.py"
        conf_py.write_text(conf_py.read_text(encoding="utf-8") + "\nBOOT_DELAY_SECONDS = 3\n", encoding="utf-8")
        accepted_sources = {
            "time.sleep(3.0)": "import time\ntime.sleep(3.0)\n",
            "utime.sleep(3)": "import utime\nutime.sleep(3)\n",
            "time.sleep(conf.BOOT_DELAY_SECONDS)": "import time\nimport conf\ntime.sleep(conf.BOOT_DELAY_SECONDS)\n",
            "sleep_ms(3000)": "from time import sleep_ms\nsleep_ms(3000)\n",
        }
        for label, source in accepted_sources.items():
            main_py.write_text(source, encoding="utf-8")
            rc, stdout, _stderr = run_cmd(
                [sys.executable, str(ROOT / "scripts" / "check_skeleton_compliance.py"), "--project-dir", str(project)]
            )
            if rc != 0 or "BOOT_DELAY_MISSING" in stdout:
                raise AssertionError(f"skeleton check must accept semantic boot delay form {label}: {stdout}")
        main_py.write_text("import time\ntime.sleep(1)\n", encoding="utf-8")
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_skeleton_compliance.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "BOOT_DELAY_MISSING" not in stdout or "accepted_forms" not in stdout:
            raise AssertionError(f"skeleton check must reject short boot delay with actionable accepted_forms: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "from conf import LOG_DIR, LOG_FILES_MAX, LOG_LINES_PER_FILE\n"
            "from lib import logger\n"
            "logger.install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)\n"
            "logger.info('missing timestamp')\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "LOGGER_ROTATING_TIMESTAMP_MISSING" not in stdout:
            raise AssertionError(f"semantic check must require timestamped rotating logger calls: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "import time\n"
            "from conf import LOG_DIR, LOG_FILES_MAX, LOG_LINES_PER_FILE\n"
            "from lib import logger\n"
            "logger.install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)\n"
            "logger.info('[t=%dms] boot' % time.ticks_ms())\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "LOGGER_STARTUP_FATAL_GUARD_MISSING" not in stdout:
            raise AssertionError(f"semantic check must require startup fatal guard: {stdout}")

    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        make_project(project, mode="timer")
        main_py = project / "firmware" / "main.py"
        main_py.write_text(
            "import sys\n"
            "import time\n"
            "from conf import LOG_DIR, LOG_FILES_MAX, LOG_LINES_PER_FILE\n"
            "from lib import logger\n"
            "from lib.scheduler.timer_sched import Scheduler\n"
            "def _main():\n"
            "    logger.install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)\n"
            "    logger.info('[t=%dms] boot' % time.ticks_ms())\n"
            "    Scheduler().add_task(lambda: None, 100, name='tick')\n"
            "def _log_startup_fatal(exc):\n"
            "    sys.print_exception(exc)\n"
            "    logger.exception(exc, '[t=%dms] startup failed' % time.ticks_ms())\n"
            "try:\n"
            "    _main()\n"
            "except Exception as exc:\n"
            "    _log_startup_fatal(exc)\n"
            "    raise\n",
            encoding="utf-8",
        )
        rc, stdout, _stderr = run_cmd(
            [sys.executable, str(ROOT / "scripts" / "check_generated_semantics.py"), "--project-dir", str(project)]
        )
        if rc == 0 or "SCHEDULER_ERROR_CALLBACK_MISSING" not in stdout:
            raise AssertionError(f"semantic check must require Scheduler(error_cb=...): {stdout}")



# Every case below is a defect check_format_helper_convention actually had when it landed with no
# tests at all. Two were blind spots (it stayed silent); one failed CORRECT code, which is the
# expensive direction because it blocks a good deploy; one was structural -- str.format() ignores
# arguments it has no field for, so the brace half of the very mismatch this gate is named for
# raised nothing and could not be probed by catching exceptions.
_PERCENT_HELPER = "def _log_info(message, *args):\n    print(message % args)\n"
_BRACE_HELPER = "def _log_info(message, *args):\n    print(message.format(*args))\n"

FORMAT_HELPER_CASES = [
    # (name, helper, call, expect_finding)
    ("percent helper, percent template", _PERCENT_HELPER, '_log_info("temp=%d hum=%d", 1, 2)', False),
    ("brace helper, brace template", _BRACE_HELPER, '_log_info("temp={} hum={}", 1, 2)', False),
    ("percent helper handed a brace template", _PERCENT_HELPER, '_log_info("temp={} hum={}", 1, 2)', True),
    # str.format() drops what it has no field for, so this one raises NOTHING and is invisible to an
    # exception probe -- the reading is silently missing from the log and the line looks fine.
    ("brace helper handed a percent template", _BRACE_HELPER, '_log_info("temp=%d", 1)', True),
    # The call splats, so the runtime argument count is unknowable here. Counting the Starred node
    # as one argument failed this correct code with "not enough arguments for format string".
    ("percent call splats a tuple", _PERCENT_HELPER, 'vals = (1, 2)\n    _log_info("temp=%d hum=%d", *vals)', False),
    ("brace call splats a tuple", _BRACE_HELPER, 'vals = (1, 2)\n    _log_info("temp={} hum={}", *vals)', False),
    # ast.FunctionDef does not match ast.AsyncFunctionDef, so an async helper switched the gate off.
    ("async helper still has its convention read",
     "async def _log_info(message, *args):\n    print(message % args)\n", '_log_info("temp={}", 1)', True),
    # A helper that normalises its varargs before formatting means the same thing; requiring a bare
    # Name on the right of % (or inside the *splat) made the convention undetectable.
    ("percent helper normalising via tuple()",
     "def _log_info(message, *args):\n    print(message % tuple(args))\n", '_log_info("temp={}", 1)', True),
    ("brace helper normalising via tuple()",
     "def _log_info(message, *args):\n    print(message.format(*tuple(args)))\n", '_log_info("temp=%d", 1)', True),
    # The splat alone identifies the brace convention. Demanding that the splatted expression name
    # the varargs would stop recognising a helper that builds its argument list first, re-opening
    # the same silent hole the tuple() cases above exist to close, one step over.
    ("brace helper formatting a list it built first",
     "def _log_info(message, *args):\n    extra = list(args)\n    extra.append(0)\n"
     "    print(message.format(*extra))\n", '_log_info("temp=%d", 1)', True),
    ("repeated explicit index consumes one argument", _BRACE_HELPER, '_log_info("{0} then {0}", 1)', False),
    ("a format spec is not a missing placeholder", _BRACE_HELPER, '_log_info("temp={:>6.2f}", 1)', False),
    # Neither convention is applied, so there is nothing unambiguous to enforce and guessing would
    # produce findings on code that is fine.
    ("helper applying neither convention is not guessed at",
     "def _log_info(message, *args):\n    print(message, args)\n", '_log_info("temp={}", 1)', False),
]


def assert_format_helper_convention_cases() -> None:
    sys.path.insert(0, str(SCRIPTS))
    try:
        import check_generated_semantics as checker
    finally:
        sys.path.remove(str(SCRIPTS))

    for name, helper, call, expect_finding in FORMAT_HELPER_CASES:
        source = f"{helper}\n\ndef run():\n    {call}\n"
        errors = checker.check_format_helper_convention(Path("."), Path("main.py"), ast.parse(source))
        found = bool(errors)
        if found != expect_finding:
            raise AssertionError(
                f"format helper case {name!r}: expected "
                f"{'a finding' if expect_finding else 'no finding'}, got "
                f"{errors[0]['detail'] if errors else 'none'}"
            )
        if found and errors[0]["code"] != "FORMAT_HELPER_CONVENTION_MISMATCH":
            raise AssertionError(f"format helper case {name!r}: wrong code {errors[0]['code']}")
