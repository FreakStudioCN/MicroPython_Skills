# MaixPy Camera Reference

Official seed: https://wiki.sipeed.com/maixpy/

Status: seed_reference

Known safe shape from MaixPy examples:

```python
from maix import camera

cam = camera.Camera(640, 480)
img = cam.read()
```

Use with `maix.display` and `maix.app` for preview loops. Run `scripts/validate_reference_index.py` after a full crawl before expanding API usage.

