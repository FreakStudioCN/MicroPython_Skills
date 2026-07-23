# maix.err

Official URL: https://wiki.sipeed.com/maixpy/api/maix/err.html

Status: seed_reference

Brief: error handling module.

Stage A policy: may be used for `err.check_raise(...)` around pinmap calls when task-specific UART/pinmap references are present.

Known safe surface:

```python
from maix import err, pinmap
err.check_raise(pinmap.set_pin_function("A19", "UART1_TX"), "Failed to set TX")
```

Full class/function extraction still belongs to the maintenance crawler.
