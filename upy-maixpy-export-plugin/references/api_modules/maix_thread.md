# maix.thread

Official URL: https://wiki.sipeed.com/maixpy/api/maix/thread.html

Status: seed_reference

Brief: thread module.

Stage A policy: do not generate multi-threaded vision/UART code. Keep stage A single-loop and event-loop friendly.

Officially indexed callable surface:

```python
from maix import thread

t = thread.Thread(func, args=None)
t.join()
t.detach()
t.joinable()
```

Restrictions:

- Do not generate multithreaded camera/display/UART code in stage A.
- Use `app.need_exit()` in one main loop. Threaded pipelines require explicit user intent, resource ownership rules, and hardware testing.
