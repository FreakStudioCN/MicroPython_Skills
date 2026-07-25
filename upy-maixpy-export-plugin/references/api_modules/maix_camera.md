# maix.camera

Official URL: https://wiki.sipeed.com/maixpy/api/maix/camera.html

Status: seed_reference

Brief: access camera device and get image from it.

Stage A policy: may be used for camera preview and vision loops.

Officially indexed callable surface:

```python
from maix import camera

camera.list_devices()
camera.get_device_name()
camera.get_sensor_size()

cam = camera.Camera(640, 480)
img = cam.read()

cam = camera.Camera(width, height, format, device=None, fps=-1, buff_num=3, open=True, raw=False)
cam.open(width=-1, height=-1, format=..., fps=-1, buff_num=-1)
cam.close()
cam.is_opened()
cam.is_closed()
cam.width()
cam.height()
cam.fps()
cam.format()
cam.skip_frames(num)
```

Codegen-safe patterns:

```python
from maix import app, camera, display

cam = camera.Camera(640, 480)
disp = display.Display()

while not app.need_exit():
    img = cam.read()
    disp.show(img)
```

For AI models, prefer:

```python
cam = camera.Camera(detector.input_width(), detector.input_height(), detector.input_format())
```

Restrictions:

- Do not generate sensor-register writes (`write_reg`/`read_reg`) unless a board/task reference explicitly requires them.
- Do not change exposure/gain/AWB/windowing without user intent and a task-specific reference.
