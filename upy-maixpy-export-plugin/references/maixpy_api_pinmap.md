# MaixPy Pinmap Reference

Official URL: https://wiki.sipeed.com/maixpy/api/maix/peripheral/pinmap.html

Status: seed_reference

Known safe shape:

```python
from maix import pinmap, err

pinmap.get_pin_functions("A19")
err.check_raise(pinmap.set_pin_function("A19", "UART1_TX"), "Failed to set UART1 TX")
err.check_raise(pinmap.set_pin_function("A18", "UART1_RX"), "Failed to set UART1 RX")
```

Stage A uses fixed MaixCAM Pro UART1 pins: A19 TX and A18 RX.

Codegen policy:

- Do not remap A19/A18 unless the user leaves stage A defaults and accepts a new wiring contract.
- Pair pinmap changes with `err.check_raise(...)`.
