# MaixPy Camera Reference

Official URL: https://wiki.sipeed.com/maixpy/api/maix/camera.html

Task doc: https://wiki.sipeed.com/maixpy/doc/en/vision/camera.html

Status: seed_reference

Known safe shape from MaixPy examples:

```python
from maix import camera

cam = camera.Camera(640, 480)
img = cam.read()
```

Use with `maix.display` and `maix.app` for preview loops. Run `scripts/validate_reference_index.py` after a full crawl before expanding API usage.

For model-backed tasks, prefer camera size/format from the detector:

```python
cam = camera.Camera(detector.input_width(), detector.input_height(), detector.input_format())
```
