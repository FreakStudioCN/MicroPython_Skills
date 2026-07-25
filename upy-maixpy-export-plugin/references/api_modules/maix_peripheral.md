# maix.peripheral

Official URL: https://wiki.sipeed.com/maixpy/api/maix/peripheral.html

Status: seed_reference

Brief: chip peripheral driver aggregate.

Stage A policy: may support UART, pinmap, GPIO, and I2C only through the task-specific references in `references/maixpy_api_uart.md`, `maixpy_api_pinmap.md`, `maixpy_api_gpio.md`, and `maixpy_api_i2c.md`.

Officially indexed callable surface:

- The aggregate `maix.peripheral` page does not expose a direct stage A callable surface in the API index.
- Stage A generation must use concrete child modules such as `maix.uart`, `maix.pinmap`, `maix.gpio`, or `maix.i2c` through the task-specific reference files listed above.

Indexed subpages:

- https://wiki.sipeed.com/maixpy/api/maix/peripheral/wdt.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/timer.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/pwm.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/key.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/uart.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/adc.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/i2c.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/hid.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/spi.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/pinmap.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/gpio.html
- https://wiki.sipeed.com/maixpy/doc/en/peripheral/pinmap.html
- https://wiki.sipeed.com/maixpy/doc/en/peripheral/uart.html
- https://wiki.sipeed.com/maixpy/doc/en/peripheral/gpio.html
- https://wiki.sipeed.com/maixpy/doc/en/peripheral/i2c.html

Known stage A mapping:

```python
from maix import uart, pinmap, err
err.check_raise(pinmap.set_pin_function("A19", "UART1_TX"), "Failed to set TX")
err.check_raise(pinmap.set_pin_function("A18", "UART1_RX"), "Failed to set RX")
serial = uart.UART("/dev/ttyS1", 115200)
```

Stage A restrictions:

- UART/pinmap are supported only for the fixed MaixCAM Pro JSONL bridge.
- GPIO/I2C/SPI/ADC/PWM/key/HID/timer/WDT require task-specific references before code generation.
- Do not use ESP32 MicroPython `machine.*` APIs in MaixPy output.
