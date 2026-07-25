# maix.app

Official URL: https://wiki.sipeed.com/maixpy/api/maix/app.html

Status: seed_reference

Brief: app lifecycle module.

Stage A policy: use `app.need_exit()` in generated loops. Other app-management APIs are indexed for completeness but should not be used unless the user explicitly asks for MaixPy app packaging/runtime behavior.

Officially indexed callable surface:

```python
from maix import app

app.app_id()
app.set_app_id(app_id)
app.get_app_data_path()
app.get_app_path(app_id="")
app.get_tmp_path()
app.get_share_path()
app.get_picture_path()
app.get_video_path()
app.get_font_path()
app.get_start_param()
app.need_exit()
app.running()
app.set_exit_flag(True)
```

Codegen-safe loop:

```python
from maix import app

while not app.need_exit():
    ...
```

Restrictions:

- Do not generate `switch_app(...)` or app config writes in stage A.
- Do not use app packaging paths as a substitute for `/root/models` unless the task reference says so.
