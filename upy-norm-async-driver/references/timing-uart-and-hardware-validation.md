# Timing, UART, and Hardware Validation

Use this reference for strict-timing drivers, UART/transparent-radio drivers, or hardware verification plans.

## Strict Timing Devices

Classify microsecond pulse capture, bit-banged reset/read slots, and uninterrupted waveform sections as `cooperative_nonblocking`, not `native_async`.

- Keep the capture primitive fully synchronous. No `await`, allocation, logging, retry, or callback inside it.
- Put an `asyncio.Lock` around the complete transaction when concurrent callers can share the device or pin.
- Await before entering the critical section to enforce the documented power-on settle time and minimum measurement interval.
- On failure, schedule the next eligible slot using the same documented minimum interval. Do not retry faster just because the first read failed.
- Derive timing from source evidence or the datasheet. For DHT11-style devices, a 2 s initial wait and 1200 ms minimum interval are only valid when the specific source/device requires them.

```python
async def measure_async(self):
    async with self._lock:
        await self._wait_for_slot_async()
        try:
            # No await in this synchronous, timing-critical transaction.
            self._sync_sensor.measure()
            return self._sync_sensor.reading()
        finally:
            self._next_allowed_ms = time.ticks_add(
                time.ticks_ms(), self._min_interval_ms
            )
```

## Conservative UART Compatibility

Treat `asyncio.StreamReader`/`StreamWriter` as optional capabilities, not the baseline for RP2040 MicroPython ports. Prefer `uart.any()`, `uart.read()`, `await asyncio.sleep_ms()`, `time.ticks_ms()`, and `time.ticks_diff()` unless the target firmware has proved stream support.

Do not use `Loop.time()` or assume `asyncio.get_event_loop()` exists on the target. Use tick arithmetic for all driver timeouts.

```python
async def read_chunk_async(uart, timeout_ms=1000):
    started = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), started) < timeout_ms:
        if uart.any():
            chunk = uart.read()
            if chunk:
                return chunk
        await asyncio.sleep_ms(5)
    return None
```

For AT commands, serialize write/response transactions with a lock. Drain stale input only before a new transaction and only when the source protocol has no valid unsolicited frames. For stream framing, retain partial frames across polls; never clear a buffer merely to make a timeout disappear.

Use bounded retry with a documented policy: maximum attempts, initial delay, backoff cap, timeout, and recovery action. Preserve source framing, command bytes, transparent-mode behavior, silence-gap parsing, and ACK semantics. Do not add ACK/reply messages unless the source protocol defines them.

## Source and Behavior Evidence

Before conversion, record:

| Evidence | Required result |
|---|---|
| Hardware identity | Board/module label, transport, firmware/mode, and the matching source package path. Reject lookalike radio/modem drivers with incompatible chips or protocol modes. |
| Async inventory | Existing `async def`, tasks, events/IRQs, locks, stream wrappers, and lifecycle methods. Classify source as `sync_source`, `already_async_source`, or `mixed_source`. |
| Behavior mapping | Each public sync API mapped to its async API, with preserved command/frame bytes, timeout, split/merge and silence-gap rules, response/ACK behavior, and error semantics. |

Place the behavior mapping in the generated README for every protocol driver, not only mixed drivers.

## Hardware Acceptance

Report each level separately. A lower level does not imply a higher one.

| Level | Required evidence |
|---|---|
| Link | Bus/UART/radio transport responds or a known device identity/version is read. |
| Basic function | One documented operation completes with expected data or state. A first-frame `None` from a background receiver is a startup state, not success. |
| Complete business flow | The intended end-to-end workflow succeeds, including required peer/device/card/sensor interaction. |

For dual-endpoint protocols, provide separate transmitter and receiver demos or test roles. State both endpoint hardware, wiring/port configuration, module mode and parameters, message format, timeout, expected logs, and the return-path expectation. Run the source synchronous pair first when practical, then prove the async pair preserves the same behavior.

Generated MicroPython `.py` files must be UTF-8 without BOM. If hardware evidence is incomplete, mark exactly which acceptance level passed and what equipment or peer is missing.

## Demo Fidelity and Blocking Budgets

Copy the source package's runnable `main.py` byte-for-byte to `examples/main_sync.py`. The generated async `code/main.py` is not a replacement baseline: it must retain the source demo's relevant peripheral construction, initialization order, business action, visible output/error meaning, and cleanup.

When the source package is available, use its runnable `main.py` as the root of a recursive local-import check. Every reachable support module, package initializer, and imported or attribute-referenced symbol must remain resolvable in the output package. This is a dependency closure, not a demand to copy unrelated source modules. The async demo must also retain source driver construction and business calls; the static checker accepts the conventional `<method>_async` rename and `deinit()`/`close()` to `aclose()` lifecycle rename, but other API changes require manual review against the demo mapping table.

Every generated README must use these headings and tables:

```markdown
## API Async Matrix
| API | Level | Async strategy | Residual blocking | Timeout/cancellation |

## Source Demo to Async Demo Mapping
| Source sync step | Source API/protocol action | Async implementation | Preserved output/error meaning | Residual blocking |

## Hardware Acceptance
| Level | Evidence | Not covered |
```

For every `sync_adapter_only` row, include this additional section. A maximum duration needs source code, protocol, or datasheet evidence; an unbounded value is not acceptable.

```markdown
## Sync Adapter Blocking Budget
| API | Synchronous region | Blocking source | Maximum duration and evidence | Timeout | Allowed on main event loop |
```

## UART Concurrency Contract

For packages using UART, choose and document exactly one runtime model:

1. One background reader owns all `uart.read*` calls and dispatches frames/events.
2. One lock serializes command-response transactions; transparent data access cannot read concurrently.
3. The package exposes no concurrent read API and documents the caller ownership rule.

Use this README heading when UART is present:

```markdown
## UART Concurrency Contract
Model: <single reader | locked transaction | caller-owned>
Reader owner: <task/method>
Frame and unsolicited-data policy: <description>
```

The static checker can flag direct reads of one UART member from multiple async methods. A warning is not proof of a bug when a lock is intentionally used, but it requires the documented contract and manual review.
