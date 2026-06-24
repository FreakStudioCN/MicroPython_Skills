# Driver Factory And Mock Templates

Read this reference before generating `firmware/drivers/*_driver/` files.

## Driver API Analysis

For every device, read these files when present:

```text
firmware/lib/<driver>.py
firmware/lib/<name>_README.md
firmware/lib/<name>_example.py
```

Rules:

- Treat the downloaded driver source as the authority for mock method names and signatures.
- Use README/example to infer default address, bus speed, reset sequence, and real call pattern.
- If multiple classes exist, prefer the concrete I2C/SPI subclass. If none is obvious, choose the first public non-Exception class.
- Extract `__init__` arguments, defaults, public methods, and return expectations.
- All public methods used by tasks must exist in the mock.
- If driver constructs its own I2C internally, patch it only when necessary to allow injected `i2c=None`.

## I2C Factory Template

```python
# -*- coding: utf-8 -*-
# @Generated : upy-generate-plugin

try:
    from lib.<module> import <DriverClass>
except ImportError:
    <DriverClass> = None

_<NAME>_DEFAULT_ADDR = <default_addr>


def create_<name>(i2c, address=None):
    """Create <DriverClass>. Return driver object or None."""
    if i2c is None or <DriverClass> is None:
        return None
    addr = _<NAME>_DEFAULT_ADDR if address is None else address
    try:
        return <DriverClass>(i2c=i2c, address=addr)
    except Exception as exc:
        from lib.logger import warning
        msg = "[driver] <NAME> init failed: {}".format(exc)
        warning(msg)
        print(msg)
        return None


def scan_<name>_i2c(i2c, address=None):
    """Return True when expected I2C address responds on the bus."""
    if i2c is None:
        return False
    addr = _<NAME>_DEFAULT_ADDR if address is None else address
    try:
        return addr in i2c.scan()
    except Exception:
        return False
```

If the real driver constructor does not use `i2c=` or `address=`, adapt the call to the real source signature. Do not guess.

## GPIO Factory Template

Use this for LED, relay, buzzer, and other GPIO-only devices with no external driver:

```python
try:
    from machine import Pin
except ImportError:
    Pin = None


class <Name>Output:
    def __init__(self, pin_num, active_high=True):
        self.pin_num = pin_num
        self.active_high = active_high
        self.pin = Pin(pin_num, Pin.OUT) if Pin is not None else None
        self.off()

    def _level(self, enabled):
        return 1 if enabled == self.active_high else 0

    def on(self):
        if self.pin is not None:
            self.pin.value(self._level(True))

    def off(self):
        if self.pin is not None:
            self.pin.value(self._level(False))

    def toggle(self):
        if self.pin is not None:
            self.pin.value(0 if self.pin.value() else 1)

    def value(self, level=None):
        if self.pin is None:
            return None
        if level is None:
            return self.pin.value()
        self.pin.value(level)
        return self.pin.value()


def create_<name>(pin_num, active_high=True):
    try:
        return <Name>Output(pin_num, active_high=active_high)
    except Exception as exc:
        from lib.logger import warning
        msg = "[driver] <NAME> GPIO init failed: {}".format(exc)
        warning(msg)
        print(msg)
        return None
```

GPIO devices normally do not have scan functions.

## SPI Factory Rule

SPI adapters should accept `spi` and `cs_pin`. Instantiate chip-select inside the factory unless the real driver expects a `Pin` object provided by caller.

```python
def create_<name>(spi, cs_pin, **kwargs):
    if spi is None:
        return None
    try:
        from machine import Pin
        cs = Pin(cs_pin, Pin.OUT)
        return <DriverClass>(spi, cs, **kwargs)
    except Exception as exc:
        ...
```

## Mock Template

```python
class Mock<Name>:
    """Mock <NAME> with the same public API used by generated tasks."""

    def __init__(self, **kwargs):
        self._temperature = kwargs.get("temperature", 25.0)
        self._humidity = kwargs.get("humidity", 60.0)
        self.fail = kwargs.get("fail", False)

    def read(self):
        if self.fail:
            raise OSError("mock <NAME> failure")
        return self._temperature, self._humidity
```

Default value rules:

| Real return | Mock default |
|---|---|
| number | `0` or realistic sensor value |
| bool | `True` |
| tuple | realistic tuple, for example `(25.0, 60.0)` |
| `None` | method body can return `None` |
| display/output mutation | store call in `self.calls` or `self.last_*` |

## Async Driver Rules

- Default: keep real driver synchronous and call it from async task only when the operation is quick.
- If driver contains `time.sleep`, `time.sleep_ms`, busy wait, or blocking I2S operations, decide whether to wrap or patch.
- If patching to `async def`, update factory, mock, and task call sites together.
- Use `uasyncio`, not CPython `asyncio`, in firmware.
