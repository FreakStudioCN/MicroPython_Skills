# maix.image

Official URL: https://wiki.sipeed.com/maixpy/api/maix/image.html

Status: seed_reference

Brief: image related definitions and functions.

Stage A policy: may be used with task-specific references for drawing rectangles, strings, QR code detection, and color blob detection.

Known safe surfaces:

```python
from maix import image
img.draw_rect(x, y, w, h, image.COLOR_RED)
img.draw_string(x, y, label, image.COLOR_RED)
qrcodes = img.find_qrcodes()
blobs = img.find_blobs([[0, 80, 40, 80, 10, 80]], pixels_threshold=500)
```

For OCR, face recognition, and advanced image APIs, require full crawl before generating concrete code.
