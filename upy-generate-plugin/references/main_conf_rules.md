# main.py And conf.py Rules

Read this reference before updating `firmware/conf.py` or `firmware/main.py`.

## Framework Ownership

Scaffold-owned framework libraries are contracts, not generated business code.

- Do not edit `firmware/lib/scheduler/*`, `firmware/lib/logger/*`, `firmware/lib/time_helper.py`, or `firmware/tasks/maintenance.py` to fix generated app bugs unless the user explicitly requests a scaffold library contract change.
- Fix generator output, `firmware/main.py` assembly, generated tasks/drivers, validation scripts, or deploy tooling instead.
- For timer compatibility, keep the scaffold scheduler library default intact and pass the correct target-specific timer id from `main.py`.
- For logging behavior, do not modify scaffold logger source solely to add timestamps or formatting.

## conf.py Rules

All behavior constants must live in `conf.py`.

Required logging constants:

```python
LOG_DIR = "/log"
LOG_FILES_MAX = 4
LOG_LINES_PER_FILE = 150
LOG_LEVEL = "INFO"
```

Rules:

- Do not store secrets.
- Put thresholds, intervals, retry counts, display refresh periods, alarm durations, calibration offsets, and network timing in `conf.py`.
- Every generated business constant must be used by firmware or tests.
- Framework constants such as `LOG_DIR` may be reserved even when not directly used by a task, but `ALARM_*`, `DISPLAY_*`, `SENSOR_*`, `NETWORK_*`, and `BUSINESS_*` must be used or removed.

## main.py Boot Delay

After imports and before business initialization:

```python
time.sleep(3)  # Boot delay: allow mpremote to reconnect after reset
```

## Rotating Logger Setup

When scaffold logger exists, install device-side rotating logs:

```python
from lib.logger import install_rotating, getLogger, info, warning, error, setLevel, DEBUG, INFO
from conf import LOG_DIR, LOG_FILES_MAX, LOG_LINES_PER_FILE, LOG_LEVEL

install_rotating(LOG_DIR, max_files=LOG_FILES_MAX, lines_per_file=LOG_LINES_PER_FILE)
if LOG_LEVEL == "DEBUG":
    setLevel(DEBUG)
else:
    setLevel(INFO)
_log = getLogger("main")
```

Then double-write startup:

```python
msg = "[main] firmware start"
print(msg)
info(msg)
```

Generated logger messages should include enough timing context at the call site. Use `time.ticks_ms()`, `time.ticks_diff()`, `time.localtime()`, or an explicit helper to mix uptime/timestamp into message text before calling scaffold logger APIs. This keeps `/log/run_*.log` useful after deploy without changing scaffold logger ownership.

## DI Assembly

`main.py` must connect the full dependency chain:

```text
machine.I2C/Pin/SPI/UART -> create_<device>() -> driver object -> task function
```

Do not let task functions instantiate hardware.

## I2C Startup Scan

Only generate I2C startup scan code when manifest hardware facts include at least one I2C device or an I2C pinout/bus entry. Do not add a generic I2C scan just because the scaffold has I2C constants.

Before creating `I2C(...)`, verify SCL/SDA pins do not overlap with non-I2C assignments in `pinout[]` such as I2S BCLK/LRC/DIN, WS2812 DIN, UART, SPI, PWM, or GPIO-only control pins. If they overlap, emit a structured generate error instead of reusing the pins.

For each I2C device with `scan_<name>_i2c`, call it during startup:

```python
found = scan_aht20_i2c(i2c0)
if found:
    msg = "[driver] AHT20 found on I2C"
    info(msg)
else:
    msg = "[driver] AHT20 missing on I2C"
    warning(msg)
print(msg)
```

## I2C Address Conflicts

If manifest shows multiple I2C devices with the same address and the board has another available I2C bus, create a second I2C object. If not possible, emit a structured error instead of silently changing pins.

## Shared Peripheral Resources

Build a `generate.resource_plan` before writing `main.py` when devices share I2S, SPI, UART, ADC, PWM, or timer resources.

Rules:

- Do not let multiple generated drivers silently instantiate the same hardware peripheral independently.
- For INMP441 + MAX98357 or similar I2S microphone/amplifier pairs, either generate a proven shared/half-duplex ownership strategy or emit `partial` with a structured resource conflict.
- Record the selected strategy in `project-manifest.json.generate.resource_plan`.
- If hardware feasibility is uncertain, do not emit deploy-ready success.

## main.py Logging Points

| Position | Level | Required content |
|---|---|---|
| Firmware startup | `info` | Project name, version, board. |
| Rotating logger installed | `info` or `debug` | `LOG_DIR` path. |
| I2C/SPI/UART init | `info` | Bus id and pins. |
| Driver create success | `info` | Device and address/pin. |
| Driver create failure | `warning` | Device and exception. |
| I2C scan result | `info`/`warning` | Device and found/missing. |
| Scheduler start | `info` | Mode and tick/loop details. |
| Scheduler fatal exception | `error` | Exception summary. |

## Scheduler Entrypoints

Timer mode should wire a scheduler/tick loop from scaffold when available.

Async mode should use:

```python
import uasyncio as asyncio
asyncio.run(main())
```

Thread mode should use `_thread.start_new_thread` and keep a main heartbeat loop.
