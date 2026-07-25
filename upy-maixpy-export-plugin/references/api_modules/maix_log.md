# maix.log

Official URL: https://wiki.sipeed.com/maixpy/api/maix/log.html

Status: seed_reference

Brief: logging module.

Stage A policy: prefer simple `print(...)` in generated examples unless a task-specific reference requires `maix.log`.

Officially indexed callable surface:

```python
from maix import log

log.set_log_level(level, color=True)
log.get_log_level()
log.get_log_use_color()
```

Codegen guidance:

- Use `print(...)` for simple generated examples because it is easier to inspect from MaixVision/serial logs.
- Use `maix.log` only when a task-specific reference requires structured log levels.
