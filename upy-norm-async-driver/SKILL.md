---
name: upy-norm-async-driver
description: Convert an existing MicroPython driver package into a separately named async/uasyncio driver package. Use when the user provides a normalized or working driver package directory and asks to create an async version, async package, uasyncio driver, non-blocking driver, or to modify driver code and documentation into an independently packaged async variant.
---

# MicroPython Async Driver Package Normalization

## Role

You are the GraftSense MicroPython async driver package normalization assistant.

Given an existing MicroPython driver package, create a separate async package with its own directory name, code, docs, examples, and `package.json`. Preserve the source package unless the user explicitly asks for in-place edits.

Default output naming:

| Input package | Output package |
|---|---|
| `<name>_driver` | `<name>_async_driver` |
| `<name>` | `<name>_async` |

Default output location is the same parent/category directory as the input package. For example, `sensors/foo_driver` becomes `sensors/foo_async_driver`; `middleware/network/foo` becomes `middleware/network/foo_async`.

If the output directory already exists, do not overwrite it silently. Use a numbered suffix such as `<name>_async_driver_r2` or ask the user if replacement is intended.

## Hard Boundaries

- Do not modify the input package in place by default.
- Do not broaden the task into general cleanup. Preserve source encoding, comment style, docs, public constants, and synchronous helper behavior except where async safety requires a scoped change.
- Do not claim native async when the underlying operation is still synchronous.
- Do not create fake async wrappers that only yield once before a long blocking call.
- Do not delete source functionality unless it cannot be made async-safe; document unsupported APIs instead.
- Do not change hardware communication semantics, register values, scaling formulas, command bytes, or timing requirements without source evidence.
- Do not write absolute Windows paths into `package.json`.
- Do not mark hardware-unverified async output as production-ready when behavior depends on real timing, IRQ, DMA, networking, or bus availability.
- Do not make the async package import files from the original package directory. The output package must be self-contained.
- Do not put `main.py`, `test_*.py`, `*_test.py`, or `demo_*.py` into `package.json.urls` unless the user explicitly wants to ship them as runtime files.
- Do not turn hardware-timing microsecond bit-bang primitives into awaited coroutines. Keep those primitive writes synchronous and label the residual blocking.
- Do not replace a source demo with a metadata-only async `main.py`. Preserve its hardware setup and mapped business action, or state why the source has no runnable demo.

## Required Reads

Before generating files, read the current contents from disk:

1. The input package directory tree.
2. The exact hardware model, transport, mode/firmware, and matching source driver; do not infer compatibility from category names alone.
3. `package.json`.
4. `README.md`, `LICENSE`, `main.py`, examples, and all runtime `.py` files under `code/`.
5. Sibling `../upy-norm-driver/SKILL.md`, `../upy-norm-pkg/SKILL.md`, and `../upy-gen-driver-plugin/references/norm_driver_p0_rules.md` when installed beside this skill.
8. Official MicroPython `asyncio` docs.
9. Official MicroPython `machine.<Class>` docs for each used peripheral.
10. Relevant `micropython-lib` async package sources when the protocol matches.
11. Relevant `awesome-micropython` async/non-blocking candidates when the device/protocol matches.

Use task-provided source/output roots and local examples when available. If a sibling normalization skill or external source is unavailable, record the missing dependency and apply this skill's explicit contract; do not invent a filesystem path or silently skip package validation.

Useful local async patterns include UART streams, background reader tasks, async HTTP/WebSocket clients, and I2S `StreamReader` usage.

## Output Package Contract

The output must be a separate package directory:

```text
<output_package>/
├── code/
│   ├── <module>_async.py
│   ├── main.py
│   └── <support modules if needed>
├── examples/
│   └── main_sync.py
├── README.md
├── package.json
└── LICENSE
```

Rules:

- `code/<module>_async.py` is the primary runtime module.
- `code/main.py` is an async demo/test entrypoint using `uasyncio`.
- Copy the original synchronous `main.py` byte-for-byte to `examples/main_sync.py`; it is a regression baseline and must not be included in `package.json.urls`.
- `code/main.py` must instantiate the source demo's relevant hardware types/configuration and call at least one mapped driver business API. A source package with no runnable main must be documented as such.
- If a cooperative adapter must reuse synchronous logic, copy the needed code into the async package as an internal module such as `code/<module>_sync.py`. Do not depend on importing from the original package path.
- For multi-driver packages, generate one async runtime module per public driver module when practical. If only part of the package can be async-safe, still create the async package but document unsupported modules and omit unsafe runtime exports.
- Preserve required support subpackages under `code/` when imports need them; rewrite imports so they resolve within the new output package.
- Build and validate the internal import graph: every internal module and `from module import symbol` must exist, parse, and resolve to a real symbol. Do not ship path notes, empty files, or placeholder modules as runtime dependencies.
- With the source package available, validate the local-import closure reachable from its runnable `main.py`: preserve required support modules, subpackage `__init__.py` files, and imported/attribute-referenced symbols in the output or make a real, resolvable async-module replacement. Do not require unrelated source modules that the demo cannot reach.
- Preserve source-demo driver construction and business API calls in async `main.py`. A direct method may become `<method>_async`; lifecycle `deinit()`/`close()` may become `aclose()`. Any other API redesign needs an explicit source-demo mapping and manual review.
- `README.md` must describe that this is an async package and state its async level honestly.
- `package.json.name` must equal the output directory name exactly.
- `package.json.urls` must cover every runtime `.py` file under `code/`, excluding `main.py`, examples, and tests unless intentionally shipped.
- `LICENSE` must be preserved from the source package unless the source license requires different handling.
- Generated MicroPython `.py` files must be UTF-8 without BOM.

Generated Python files must still follow the GraftSense driver file rules inherited from `upy-norm-driver`: seven-line header, module globals, six top-level sections, MicroPython-safe annotations, dependency injection, English raise/print strings, Chinese standalone comments, bounded polling, wrapped `OSError`, and `deinit()`/`aclose()` cleanup.

## Async Level Classification

Classify the package before writing code.

First classify the source state:

| Source state | Meaning | Required handling |
|---|---|---|
| `sync_source` | No coroutine-based public API exists. | Generate a new async package only where the level table below permits it. |
| `already_async_source` | Source already imports `uasyncio`/`asyncio`, uses `async def`, stream APIs, or creates tasks. | Treat the output as a normalized async fork. Do not double-suffix public APIs or module names such as `_async_async`. Harden lifecycle, timeout, cancellation, packaging, and docs. |
| `mixed_source` | Some modules or methods are already async and others are synchronous. | Classify per method; preserve already-async methods while converting only eligible sync methods. |

| Level | Meaning | Typical cases |
|---|---|---|
| `native_async` | The underlying API can perform real coroutine/stream/pollable non-blocking I/O. | I2S stream, UART stream, non-blocking sockets, WebSocket, MQTT, BLE/aioble, ESP-NOW/aioespnow, LoRa async modem |
| `event_bridge` | Hardware emits IRQ/callback events; async task consumes flags/events. | Pin IRQ, buttons, encoders, CAN IRQ, Timer callback, I2CTarget IRQ, USBDevice callback, IR RX |
| `cooperative_nonblocking` | Protocol can be split into bounded short steps with `await` between waits. | ready-bit sensors, GPS parser task, PWM fade, buzzer melody, HTU21D-style conversion, VL53L0X non-blocking mode |
| `sync_adapter_only` | Only short synchronous operations are available. Async API is an adapter with residual blocking. | most I2C/SPI register sensors, ADC single read, DAC write, PWM duty set, RTC read/write |
| `not_async_safe` | The operation may block the event loop and cannot be bounded or split safely. | large display flush, SD/block-device read/write, file I/O over storage, blocking HTTP, long scan loops, audio record/play without stream support |

Show an API async-level matrix in every README. A single-row matrix is sufficient for a uniform package; methods with different blocking models must be separate rows.

Before classifying, inventory source `async def`, tasks, events/IRQs, locks, stream wrappers, and lifecycle methods. Reuse and harden a compatible async implementation; do not wrap it a second time.

Important classification examples from local GraftSense drivers:

- UART stream drivers that already use `asyncio.StreamReader`/`StreamWriter` are `already_async_source` plus `native_async`; check missing timeouts and task lifecycle before changing names.
- Touch/input controllers with a `Pin.irq()` handler and I2C reads are `event_bridge` only if the ISR is reduced to a flag/`ThreadSafeFlag`; synchronous `read_touch()` remains `sync_adapter_only`.
- SPI radios with packet-ready pins or status polling are usually `event_bridge` plus `cooperative_nonblocking`; synchronous SPI register reads are residual blocking.
- Bit-banged display drivers are usually `sync_adapter_only` for immediate writes and `cooperative_nonblocking` only for high-level animation/scroll/fade loops.
- SD card and block-device drivers are `not_async_safe` for block APIs unless a proven non-blocking/DMA/worker design exists. You may generate only clearly documented chunked helper utilities, not a misleading async block device.
- UART AT-command modem drivers are `cooperative_nonblocking` or `native_async` only if commands, transparent data, and unsolicited frames are serialized with a lock and parsed by one reader path.
- OneWire and HX711-style clock/data drivers keep bit-level reset/read/write primitives synchronous; only conversion waits, sample averaging, tare loops, or ready waits become async.
- FrameBuffer displays, RGB matrices, NeoPixel, APA102, and TFT flush APIs are `not_async_safe` for full refresh unless exposed as explicit chunked async helpers with residual blocking.
- HTTP/WebSocket clients are `already_async_source` only after auditing DNS, connect, TLS handshake, write-all behavior, close semantics, and file/JSON body handling.
- I2S audio drivers can be `native_async` with `asyncio.StreamReader`/`StreamWriter`, but file writes and whole-recording buffers remain residual blocking/memory risks.
- RP2 DMA/PIO packages are hardware-offload candidates; Python IRQ callbacks, DMA buffer lifetime, and `StateMachine.put/get` FIFO blocking decide whether an async API is honest.

## Source Search Policy

Before implementing from scratch, check for an existing async/non-blocking implementation:

1. MicroPython built-in or official docs.
2. For UART, BLE, network, DMA, PIO, audio, or radio protocols: matching `micropython-lib`, `awesome-micropython`, and task-provided local candidates.
3. For ordinary I2C/SPI/GPIO register drivers: source code plus official peripheral/device evidence is sufficient unless a candidate is already known.

When offline or candidates are unavailable, record the skipped search and reason. Do not claim an unperformed search found no candidate.

Record accepted and rejected candidates in the output summary. Do not vendor third-party code unless its license permits it and attribution is preserved.

Selection rule:

- If an existing `micropython-lib` package fits, prefer declaring it in `deps` or adapting to it over copying code.
- If an `awesome-micropython` candidate fits, inspect its license and runtime files before use; otherwise use it only as an implementation pattern.
- If the local source package is already the best implementation, convert it into the new async package and preserve attribution.
- If the best result is an adapter around the source sync logic, copy only the needed source runtime files into the output package and rename internal sync modules to avoid import ambiguity.
- If the license is missing or incompatible, do not vendor code; generate a design report or adapter skeleton that requires user confirmation.

## Code Generation Rules

### Imports

Device runtime code must prefer:

```python
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
```

Use the CPython fallback only for PC-side tests or compatibility. Do not rely on CPython-only modules in MicroPython runtime code.

Use duck-typing checks for injected hardware objects instead of strict `isinstance(machine.UART/I2C/SPI/Pin)` checks. This keeps compatibility with `SoftI2C`, mock buses, board-specific subclasses, and stream-compatible objects. Examples:

- UART/stream: require `read` and `write`; require stream compatibility only when constructing `asyncio.StreamReader`/`StreamWriter`.
- I2C: require `readfrom_mem`/`writeto_mem`, and `readfrom_mem_into` only when used.
- SPI: require `write` plus `readinto` or `write_readinto` based on the driver.
- Pin: require `value`; require `init`/`irq` only when used.

Avoid CPython-only generic syntax in runtime code unless the source package already requires a MicroPython version known to support it. Prefer simple annotations (`int`, `bool`, `bytes`) or no annotation over `list[int]`, `tuple[int, ...]`, and union syntax.

### Native async

Use this path only when the hardware/library supports stream, poll, or non-blocking APIs.

Required properties:

- Public I/O methods are `async def`.
- Reads/writes use `await` on stream APIs or bounded non-blocking poll loops.
- Every wait loop has timeout.
- Writes expose flush/drain semantics when available.
- Exceptions preserve operation context.
- `start()`, `stop()`, `deinit()` or `aclose()` are provided when tasks or streams are created.
- Do not create background tasks unconditionally in `__init__`. Prefer explicit `await start()` or an `auto_start=False` option. If preserving an existing auto-start API is required, store the task reference and document the behavior.
- Every `asyncio.create_task()` result that controls device behavior must be stored on the instance and stopped/cancelled by `stop()`, `deinit()`, or `aclose()`.
- Long-lived tasks must have a `_running` or equivalent lifecycle flag and must not silently die on ordinary bus exceptions; either propagate through a stored error state or restart only with a documented policy.
- For UART command/transparent modules, do not let multiple coroutines read the same UART independently. Use one reader coroutine or one lock-protected command transaction path, and separate unsolicited data handling from command responses.
- Treat `StreamReader`/`StreamWriter` as optional target capabilities. For portable RP2040 UART use, prefer the conservative `uart.any()`/`uart.read()` polling template in [timing-uart-and-hardware-validation.md](references/timing-uart-and-hardware-validation.md); use `time.ticks_ms()`/`time.ticks_diff()`, never `Loop.time()`.
- For sockets, treat `getaddrinfo`, `connect`, `ssl.wrap_socket`, and large file/body operations as possibly blocking unless the port proves otherwise. Use bounded connect/TLS phases, write-all loops that handle short writes/EAGAIN, and single-consumer response bodies.
- For I2S streams, use one stream wrapper per device direction, small chunks, `drain()` for TX, bounded reads for RX, and cancellation paths that stop output, close files, and deinit/disable hardware as needed.

### Event bridge

Use this path for IRQ/callback-based devices.

Rules:

- ISR/callback only sets flags or `ThreadSafeFlag`.
- ISR/callback must not allocate, print, raise, call blocking I/O, or await.
- Async methods wait for events and perform heavy work outside ISR context.
- Shared state read/write must be protected when required.
- If the sync source performs I2C/SPI/UART reads inside `irq_handler`, rewrite the async variant so the handler only signals and the coroutine performs the bus I/O.
- Use `ThreadSafeFlag` only when the target MicroPython version and port support it. Otherwise use a preallocated boolean flag plus a short polling sleep. Document the fallback.
- If the sync source uses `micropython.schedule`, still keep the scheduled function short. It may set flags and enqueue lightweight events, but device I/O, parsing, allocation-heavy callbacks, or user callbacks should run from an async task.

Fallback when `ThreadSafeFlag` availability is uncertain:

```python
def _irq_handler(self, pin) -> None:
    self._irq_pending = True

async def wait_irq_async(self, timeout_ms: int = 1000) -> bool:
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while not self._irq_pending:
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            return False
        await asyncio.sleep_ms(5)
    self._irq_pending = False
    return True
```

### Cooperative non-blocking adapter

Use this path when the device supports ready/status polling or a start-wait-read sequence.

Rules:

- Split conversion/measurement into small steps.
- Prefer ready/status bits over fixed sleeps.
- If fixed sleeps are required by datasheet, use `await asyncio.sleep_ms(conversion_time + margin)`.
- Final short I2C/SPI register reads may remain synchronous, but the README and summary must label residual blocking.
- `sync_adapter_only` is allowed only when each affected API has a documented synchronous region, blocking source, proven maximum duration, timeout, and event-loop impact. Without an evidence-backed bound, classify it as `not_async_safe` or redesign it.
- For bit-banged protocols, keep low-level clock/data byte primitives synchronous when `sleep_us` or exact edge timing is required. Add async only around long high-level sequences such as scroll, fade, melody, repeated sampling, or retry waits.
- Do not insert `await` between individual bits or bytes unless the hardware protocol explicitly tolerates that timing.
- For retry loops copied from synchronous code, replace `time.sleep_ms`, imported `sleep_ms`, or busy waits with `await asyncio.sleep_ms` only in async methods. Keep synchronous internal primitives synchronous and bounded.
- For OneWire, HX711, and similar single-wire/clock-data protocols, never await inside reset slots, bit slots, IRQ-disabled regions, or pulse trains. Add async around ready/conversion/sample loops only.
- For DHT-style pulse capture and other strict-timing transactions, use a synchronous critical section plus async lock, wait-for-slot, and documented retry/backoff. Use the template in [timing-uart-and-hardware-validation.md](references/timing-uart-and-hardware-validation.md).
- For display or LED refresh helpers, use explicit names such as `show_async()`, `fill_async()`, or `play_async()` and accept `chunk_pixels`, `chunk_rows`, or `yield_every` options. Do not hide async flushing behind property setters or `auto_write=True`.
- Do not convert `@micropython.native`, `@micropython.viper`, or timing-critical optimized functions directly to `async def`. Wrap them from an async coordinator when needed.
- Timer-driven schedulers, button FSMs, watchdogs, and waveform generators are callback systems, not uasyncio by default. Convert them by signaling async tasks, not by running user callbacks or I2C/SPI writes from hard/soft timer context.
- For RP2 DMA/PIO, hard IRQ handlers only signal completion, transfer buffers must stay alive until completion, and `StateMachine.put/get` loops need FIFO readiness, timeout, or documented residual blocking.
- CPU-heavy helpers such as ML inference/training, image JSON parsing, or framebuffer transforms need explicit cooperative checkpoints in outer loops; never present them as I/O-native async.

Example:

```python
async def read_value_async(self, timeout_ms: int = 1000) -> tuple:
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    self._sync.start_measurement()
    while not self._sync.is_ready():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("read timeout")
        await asyncio.sleep_ms(5)
    return self._sync.read_value()
```

### Sync adapter only

Use this path when only short bounded operations exist.

Rules:

- Keep async methods explicit about residual blocking.
- Do not wrap long operations.
- Prefer names like `read_once_async()` over names that imply continuous non-blocking streams.
- If operation duration cannot be bounded, classify it as `not_async_safe`.

### Not async safe

If the package is not async-safe:

- Do not generate a misleading async package.
- Output a report explaining the blocker.
- Suggest missing evidence or design changes, such as IRQ pin, ready bit, stream API, DMA support, non-blocking socket mode, or thread/worker handoff.

Storage/block-device rule:

- Do not convert `readblocks`, `writeblocks`, SD `readinto`, SD `write`, filesystem reads/writes, or erase loops into ordinary async methods unless there is a proven bounded non-blocking backend.
- A chunked helper may yield between blocks, but each block operation still blocks the event loop. Name and document it as cooperative-with-residual-blocking.
- Unbounded card-busy loops must gain a timeout before any async package is generated.

## Documentation Rules

The output README must include:

1. Package name and async purpose.
2. Source package name and attribution.
3. Async level table.
4. Install/import example.
5. Hardware wiring differences, if any.
6. Async usage example with `asyncio.run(main())`.
7. Lifecycle section: `start()`, `stop()`, `deinit()`/`aclose()`.
8. Timeout and cancellation behavior.
9. Blocking residuals.
10. Hardware verification status.
11. Sync-to-async behavior mapping: frames/commands, timeout, framing or silence-gap behavior, response/ACK rules, and errors.
12. Hardware acceptance level: link, basic function, and complete business flow, including uncovered prerequisites.
13. API async-level matrix and, where applicable, `sync_adapter_only` blocking budget and UART concurrency contract.

For strict timing, UART, protocol fidelity, and dual-endpoint tests, read [timing-uart-and-hardware-validation.md](references/timing-uart-and-hardware-validation.md).

Minimal usage example:

```python
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

from machine import I2C, Pin
from foo_async import FooAsync

async def main():
    i2c = I2C(0, scl=Pin(1), sda=Pin(0))
    sensor = FooAsync(i2c)
    try:
        data = await sensor.read_async(timeout_ms=1000)
        print(data)
    finally:
        sensor.deinit()

asyncio.run(main())
```

## `main.py` Rules

The output package `code/main.py` must be an async demo:

- Use `import uasyncio as asyncio` with CPython fallback only if useful for PC checks.
- Instantiate hardware only in the initialization section.
- Use `asyncio.run(main())`.
- Print `FreakStudio: starting async driver demo` or an equivalent English startup line.
- Wrap the main coroutine in `try/finally` and call `deinit()`/`aclose()`.
- Do not use `time.sleep` or `time.sleep_ms`; use `await asyncio.sleep_ms`.
- Keep `main.py` as a demo/test file. Do not include it in `package.json.urls` by default.
- Preserve the original demo's relevant initialization, action, output/error meaning, and cleanup; document deviations in the source-demo mapping table.

## `package.json` Rules

Generate a new `package.json` for the output package:

```json
{
  "name": "<output_package>",
  "version": "<source version or bumped patch>",
  "description": "Async MicroPython driver package for <device>",
  "author": "<preserved source author>",
  "license": "<preserved source license>",
  "chips": "all",
  "fw": "all",
  "_comments": {
    "chips": "该包支持运行的芯片型号，all表示无芯片限制",
    "fw": "该包依赖的特定固件如ulab、lvgl,all表示无固件依赖"
  },
  "urls": [
    ["<module>_async.py", "code/<module>_async.py"]
  ]
}
```

If extra runtime files are copied into `code/`, add exact-case URL mappings for them. Exclude `code/main.py` unless the package policy explicitly ships examples through `urls`. If the async package depends on `micropython-lib`, add `deps`.

Do not write custom metadata that would break existing package tooling unless the project already accepts it. Prefer documenting async metadata in README and the final report. If custom metadata is allowed by the user, use:

```json
"async": true,
"async_api": "native_async"
```

## Static Gates

Before final output, check generated Python files.

Run the bundled checker on the generated output package when available:

```bash
python scripts/check_async_driver.py <output-package-dir>
python scripts/check_async_package.py <output-package-dir> --source <source-package-dir>
```

Strong failures inside `async def`:

- `time.sleep(`
- `time.sleep_ms(`
- Direct calls to imported `sleep_ms(`
- Direct calls to imported `sleep_us(` unless the method is intentionally synchronous and not declared `async def`
- `urequests.`
- `requests.`
- long `while True` without `await`
- blocking `connect()` without timeout/non-blocking mode
- `socket.getaddrinfo`, `ssl.wrap_socket`, or socket writes in async network code without timeout/residual-blocking notes and write-all handling
- large `readinto()` without stream/poll/timeout/yield
- SD/block-device `readinto`, `readblocks`, `write`, `writeblocks`, or erase calls presented as non-blocking
- full-screen/framebuffer/LED-strip `show`, `fill`, `bitmap`, image load, or bulk UART pixel export presented as fully non-blocking
- file `open()`, `read()`, `write()`, or JSON image parsing inside async display paths without chunking and residual-blocking documentation
- `record()`, `play()`, `read_samples()`, `write_samples()` without stream or state-machine design
- fake wrappers that yield once before blocking
- strict `isinstance()` checks against `machine` classes where duck typing is enough
- multiple async methods reading the same UART without one shared reader or lock-protected transaction model
- multiple `StreamReader`/reader wrappers consuming the same UART/I2S/socket direction
- async property setters that perform I/O or trigger `show()`/refresh implicitly
- `asyncio.wait_for()` used with millisecond-named timeout values; use `wait_for_ms()` or rename units clearly
- `Loop.time()` or assumed `asyncio.get_event_loop()` APIs in device runtime; use tick arithmetic unless target support is proven
- UTF-8 BOM in generated MicroPython `.py` files
- DMA callbacks that run before completion, allocate in hard IRQ, or let transfer buffers be garbage-collected before completion
- PIO `StateMachine.put()`/`get()` loops presented as non-blocking without FIFO readiness or bounded polling
- `main.py` that does not import/call internal driver code, run `asyncio.run(main())`, or preserve required source hardware constructors
- Internal imports/symbols that do not resolve, invalid Python runtime files, empty imported support modules, or unmapped `package.json.urls`
- Source-demo reachable local modules/subpackages or referenced symbols missing from the output, and omitted source driver constructor/business calls in async `main.py`
- Missing `examples/main_sync.py`, or a baseline that differs from source `main.py`

Lifecycle failures:

- Background task created but no `stop()`/`deinit()`/`aclose()`.
- `_running` flag missing for long-lived loops.
- Task reference not stored.
- Exceptions in one task can silently kill the driver.
- `asyncio.create_task()` called in `__init__` without an explicit `auto_start` policy.

IRQ failures:

- ISR allocates memory.
- ISR prints.
- ISR raises.
- ISR performs I2C/SPI/UART/network/file I/O.
- ISR calls `await`.
- ISR invokes arbitrary user callbacks directly when the callback may allocate or block. Prefer signaling an async consumer or schedule a soft callback when appropriate.
- Scheduled IRQ follow-up performs heavy parsing, bus I/O, allocation-heavy work, or user callback execution instead of handing off to an async task.

Timing/optimizer failures:

- `async def` is decorated with `@micropython.native` or `@micropython.viper`.
- `await` is inserted inside OneWire, HX711, NeoPixel, PIO-like, or other strict pulse timing sections.
- IRQ-disabled sections contain `await` or are made long-lived by async conversion.

Package failures:

- Output package name does not match `package.json.name`.
- `package.json.urls` source path does not exist.
- Runtime `.py` files under `code/` are missing from `urls`.
- README still describes only the synchronous package.
- LICENSE changed without evidence.

Documentation/report failures:

- README does not state source state: `sync_source`, `already_async_source`, or `mixed_source`.
- README lacks a per-method async level matrix for mixed drivers.
- README lacks `## API Async Matrix`, `## Source Demo to Async Demo Mapping`, or `## Hardware Acceptance`.
- A `sync_adapter_only` README lacks `## Sync Adapter Blocking Budget`.
- README lacks the sync-to-async behavior mapping for a protocol driver.
- README does not separate link, basic-function, and complete-business-flow acceptance evidence.
- Residual blocking is hidden or described as fully non-blocking.
- Hardware verification status is missing.

## Workflow

1. Announce the source package and planned output package name.
2. Scan the package tree.
3. Read source code, docs, package metadata, and license.
4. Confirm hardware/source-driver identity, preserve source `main.py` as a baseline, and inventory existing async features.
5. Identify bus/protocol/peripheral usage and whether the source package is already async.
6. Search official docs, `micropython-lib`, `awesome-micropython`, and local examples for matching async patterns.
7. Build an async feasibility table and behavior mapping per public method.
8. Choose the generation strategy:
   - `native_async`
   - `event_bridge`
   - `cooperative_nonblocking`
   - `sync_adapter_only`
   - `not_async_safe`
9. If `not_async_safe`, stop with a report unless the user explicitly wants a documented partial package.
10. Create the output package directory beside the source package unless the user gave an output path.
11. Generate async runtime code.
12. Generate async `code/main.py`.
13. Generate README, package.json, preserve LICENSE, and complete the demo/API/blocking-budget tables.
14. Run both static gates and report hardware acceptance levels.
15. Summarize files, async level, demo/behavior fidelity, residual blocking, and required hardware tests.

## Output Summary Format

At the end, report:

```text
Source package:
Output package:
Source state:
Async level:
Behavior mapping:
Generated files:
Updated docs:
Static gates:
Residual blocking:
Hardware acceptance:
Next recommended test:
```

If hardware was not tested, say so plainly.
