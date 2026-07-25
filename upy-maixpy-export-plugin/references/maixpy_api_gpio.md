# MaixPy GPIO Reference

Official URL: https://wiki.sipeed.com/maixpy/api/maix/peripheral/gpio.html

Status: seed_reference

GPIO is available through the MaixPy peripheral package. Stage A Sipeed vision export does not generate GPIO code by default; use it only when the user explicitly asks for GPIO interaction on the MaixCAM side.

Officially indexed shape:

```python
from maix import gpio

pin = gpio.GPIO("A19", gpio.Mode.OUT, gpio.Pull.PULL_NONE)
pin.value()
pin.value(1)
pin.high()
pin.low()
pin.toggle()
```

Codegen policy:

- Do not use `machine.Pin`; generated MaixPy code must use MaixPy APIs.
- Do not reuse A19/A18 as GPIO when they are reserved for the stage A UART1 JSONL bridge.
