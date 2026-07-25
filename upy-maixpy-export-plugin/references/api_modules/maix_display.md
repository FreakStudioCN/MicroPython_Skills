# maix.display

Official URL: https://wiki.sipeed.com/maixpy/api/maix/display.html

Status: seed_reference

Brief: control display device and show image on it.

Stage A policy: may be used for preview/debug display.

Officially indexed callable surface:

```python
from maix import display

display.send_to_maixvision(img)
display.set_trans_image_quality(80)

disp = display.Display()
disp.show(img)

disp = display.Display(width=-1, height=-1, format=..., device="", open=True)
disp.open(width=-1, height=-1, format=...)
disp.close()
disp.width()
disp.height()
disp.size()
disp.format()
disp.show(img, fit=...)
disp.set_backlight(value)
disp.get_backlight()
```

Codegen-safe usage:

- `disp.show(img)` is safe for camera preview and vision result overlays.
- `display.send_to_maixvision(img)` may be mentioned as an optional debugging route, but stage A should not depend on it.

Restrictions:

- Do not generate touch UI or display channel management unless `maix.touchscreen` and the task reference are explicitly selected.
- Do not silently change backlight/mirror/flip settings unless requested.
