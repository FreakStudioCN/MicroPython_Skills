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
