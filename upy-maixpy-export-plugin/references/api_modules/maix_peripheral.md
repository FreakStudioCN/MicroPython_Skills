# maix.peripheral

Official URL: https://wiki.sipeed.com/maixpy/api/maix/peripheral.html

Status: seed_reference

Brief: chip peripheral driver aggregate.

Stage A policy: may support UART, pinmap, GPIO, and I2C only through the task-specific references in `references/maixpy_api_uart.md`, `maixpy_api_pinmap.md`, `maixpy_api_gpio.md`, and `maixpy_api_i2c.md`.

Required subpages:

- https://wiki.sipeed.com/maixpy/doc/en/peripheral/pinmap.html
- https://wiki.sipeed.com/maixpy/doc/en/peripheral/uart.html
- https://wiki.sipeed.com/maixpy/doc/en/peripheral/gpio.html
- https://wiki.sipeed.com/maixpy/doc/en/peripheral/i2c.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/uart.html
- https://wiki.sipeed.com/maixpy/api/maix/peripheral/pinmap.html

Known stage A mapping:

```python
from maix import uart, pinmap, err
err.check_raise(pinmap.set_pin_function("A19", "UART1_TX"), "Failed to set TX")
err.check_raise(pinmap.set_pin_function("A18", "UART1_RX"), "Failed to set RX")
serial = uart.UART("/dev/ttyS1", 115200)
```
