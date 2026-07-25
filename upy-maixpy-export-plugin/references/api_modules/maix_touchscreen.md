# maix.touchscreen

Official URL: https://wiki.sipeed.com/maixpy/api/maix/touchscreen.html

Status: seed_reference

Brief: touchscreen module.

Stage A policy: indexed for future UI workflows. Do not generate touch UI unless explicitly requested and full reference is present.

Officially indexed callable surface:

```python
from maix import touchscreen

ts = touchscreen.TouchScreen(device="", open=True)
ts.open()
ts.close()
ts.read()
ts.read0()
ts.available(timeout=0)
ts.is_opened()
ts.clear()
```

Restrictions:

- Do not add touch UI to normal camera/AI UART exports.
- Touch coordinates and screen orientation require hardware-specific validation.
