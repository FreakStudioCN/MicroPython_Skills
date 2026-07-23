# MaixPy Pinmap Reference

Official seed: https://wiki.sipeed.com/maixpy/

Status: seed_reference

Known safe shape:

```python
from maix import pinmap, err

err.check_raise(pinmap.set_pin_function("A19", "UART1_TX"), "Failed to set UART1 TX")
err.check_raise(pinmap.set_pin_function("A18", "UART1_RX"), "Failed to set UART1 RX")
```

Stage A uses fixed MaixCAM Pro UART1 pins: A19 TX and A18 RX.

