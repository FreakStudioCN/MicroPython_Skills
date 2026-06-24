# Task Generation Rules

Read this reference before generating `firmware/tasks/*.py` and `test/pc/*`.

## Task Shape

Tasks must be plain Python functions or coroutines with dependency injection:

```python
def sensor_tick(sensor, display=None, alarm=None):
    ...
```

Rules:

- Do not import `machine`.
- Do not instantiate `Pin`, `I2C`, `SPI`, `UART`, or network hardware.
- Accept driver objects as parameters.
- Handle `None` driver objects gracefully.
- Catch exceptions per device operation; one failed sensor must not stop all outputs.
- Return a small result dict when useful so PC tests can assert behavior.

## Scheduler Modes

| Mode | Task style |
|---|---|
| `timer` | Sync function, use `@timed_function` when available. |
| `async` | `async def`, use `@timed_coro` when available, await non-trivial waits. |
| `thread` | Sync worker-safe function, avoid shared mutable globals unless protected. |

## State And Async Semantics

- State-machine tasks must persist state across calls with a class, context object, state dict, or explicit state parameter. Do not reset `state`, `last_trigger`, or similar state variables inside every `*_tick()` call.
- Async tasks must be cooperative. Do not call synchronous HTTP/network methods such as `urequests.post()` or driver `http_post()` directly inside `async def`; generate a non-blocking adapter/state machine or emit `partial` with a structured error.
- In `async def`, do not call blocking driver/time operations directly: `time.sleep`, `time.sleep_ms`, `read_samples`, `readinto`, `record`, `play_samples`, `write_samples`, `connect`, or long scan loops. Use `await asyncio.sleep_ms(...)`, break the operation into short state-machine steps, move it to a thread-mode worker, or emit `partial`.
- Do not hide blocking calls from static gates with `getattr(obj, "record")`, `obj.__getattribute__("play")`, `lambda`, alias variables, reflection helpers, or thin synchronous wrappers that are then called from `async def`. This is a blocking quality failure, not an async adapter.
- A valid async strategy must be explicit and testable: a cooperative state machine that advances in short non-blocking steps, a thread/worker handoff when the scaffold mode and board support it, a genuinely non-blocking driver API, or `partial` with `next_phase=null`. Yielding once before a blocking `record()`, `play()`, `connect()`, or synchronous HTTP call is not sufficient.
- Runtime firmware must not contain placeholder payloads such as `base64_placeholder`, fake cloud responses, or TODO implementations. If an API payload shape is unknown, request user details or stop with `partial`.
- Data read from hardware must flow into outputs, payloads, logs, or returned result objects. Do not read a microphone/sensor buffer and discard it.
- When producer and consumer are in different ticks/states, store the data in an explicit state field, queue, or buffer and declare it in `generate_plan.json` `data_flow_contract[]`.
- For voice/audio flows, recorded bytes from microphone mocks must reach the cloud/ASR call in PC contract tests. Do not pass `b""`, fixed fake audio, or a placeholder to the cloud pipeline after a real record step unless the plan explicitly declares mock-only behavior.

## Data Flow Contract Tests

Do not rely on static semantic checks to infer all business intent. For every critical `data_flow_contract` in `generate_plan.json`, generate a PC `unittest` contract test that uses sentinel values or spy objects.

Example pattern:

```python
class SpyCloudClient:
    def __init__(self):
        self.received_audio = None

    async def process_voice(self, audio_data):
        self.received_audio = audio_data
        return bytearray(b"tts")


class SentinelMic:
    def start_recording(self):
        pass

    def record(self, duration_ms):
        return b"SENTINEL_AUDIO"

    def stop_recording(self):
        pass
```

The test should drive the producer state, then the consumer state, and assert the spy received exactly the sentinel bytes.

## Required Logging Matrix

| Position | Level | Double-write | Content |
|---|---|---|---|
| Sensor read success | `debug` | yes | Sensor name and actual values. |
| Sensor read failure | `warning` | yes | Sensor name and exception. |
| Alarm trigger | `warning` | yes | Parameter, current value, threshold. |
| Alarm recovery | `info` | yes | Parameter and current value. |
| Display update | `debug` | yes | Display content summary. |
| Display update failure | `warning` | yes | Exception. |
| Network publish success | `info` or `debug` | yes | Endpoint/topic and payload summary. |
| Network publish failure | `warning` | yes | Exception and retry intent. |
| Unexpected exception | `error` | yes | Task name and context. |
| Internal counters/GC | `debug` | optional | Logger-only is acceptable. |

Use this helper pattern:

```python
def _log_debug(message):
    try:
        from lib.logger import debug
        debug(message)
    except Exception:
        pass
    print(message)
```

Direct imports at module top are fine when scaffold logger exists:

```python
from lib.logger import debug, info, warning, error
```

## Temperature Key Collision

When both humidity and pressure sensors provide temperature, keep the main temperature under `temperature` and pressure sensor temperature under `pressure_temp`.

## PC Unit Tests

Use CPython `unittest`, not pytest-only style.

Required scenarios:

1. Normal data.
2. Missing device object (`None`).
3. Driver method raises an exception.
4. For state machines, multiple ticks covering state persistence and timeout.
5. For network/voice payloads, assert the real captured data reaches the outgoing payload.
6. For async mode, assert no synchronous network call is required for scheduler progress, or mark the implementation partial.

Template:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "firmware"))

from drivers.<name>_driver.mock import Mock<Name>  # noqa: E402
from tasks.<task> import <task_fn>  # noqa: E402


class Test<Task>(unittest.TestCase):
    def test_normal_data(self):
        sensor = Mock<Name>(temperature=25.0, humidity=60.0)
        result = <task_fn>(sensor)
        self.assertIsNotNone(result)

    def test_missing_device(self):
        result = <task_fn>(None)
        self.assertIsNotNone(result)

    def test_driver_exception(self):
        sensor = Mock<Name>(fail=True)
        result = <task_fn>(sensor)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
```
