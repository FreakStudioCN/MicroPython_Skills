# maix.app

Official URL: https://wiki.sipeed.com/maixpy/api/maix/app.html

Status: seed_reference

Brief: app lifecycle module.

Stage A policy: use `app.need_exit()` in generated loops.

Known safe surface:

```python
from maix import app
while not app.need_exit():
    ...
```
