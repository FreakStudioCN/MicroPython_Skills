# maix.time

Official URL: https://wiki.sipeed.com/maixpy/api/maix/time.html

Status: seed_reference

Brief: time module.

Stage A policy: may be used for lightweight loop throttling.

Officially indexed callable surface:

```python
from maix import time

time.time()
time.time_ms()
time.time_s()
time.time_us()
time.time_diff(last, now=-1)
time.ticks_s()
time.ticks_ms()
time.ticks_us()
time.ticks_diff(last, now=-1)
time.fps()
time.fps_start()
time.fps_set_buff_len(len)
time.sleep_ms(100)
```

Codegen guidance:

- Use `time.sleep_ms(...)` for simple throttling.
- Use `time.fps_start()` / `time.fps()` only for optional debug logging.
- Do not call NTP/timezone APIs in stage A because they imply network or system configuration.
