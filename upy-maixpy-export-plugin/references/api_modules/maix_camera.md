# maix.camera

Official URL: https://wiki.sipeed.com/maixpy/api/maix/camera.html

Status: seed_reference

Brief: access camera device and get image from it.

Stage A policy: may be used for camera preview and vision loops.

Known safe surface:

```python
from maix import camera
cam = camera.Camera(640, 480)
img = cam.read()
```

For AI models, prefer `camera.Camera(detector.input_width(), detector.input_height(), detector.input_format())` when the detector reference confirms those methods.
