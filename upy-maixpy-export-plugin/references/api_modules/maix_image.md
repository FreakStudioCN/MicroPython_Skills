# maix.image

Official URL: https://wiki.sipeed.com/maixpy/api/maix/image.html

Status: seed_reference

Brief: image related definitions and functions.

Stage A policy: may be used with task-specific references for drawing rectangles/strings, QR code detection, color blob detection, OCR box handling, and AI result overlays. Do not invent advanced image-processing calls that are not listed in this reference or a task-specific reference.

Core enums/constants:

- `image.Format`
- `image.Fit`
- `image.ResizeMethod`
- `image.COLOR_RED`, `COLOR_GREEN`, `COLOR_BLUE`, `COLOR_WHITE`, `COLOR_BLACK`, `COLOR_YELLOW`

Officially indexed callable surface:

```python
from maix import image

image.format_name(fmt)
image.load(path)
image.from_bytes(width, height, format, data, copy=True)
image.load_font(name, path, size=16)
image.set_default_font(name)
image.string_size(text, scale=1, thickness=1, font="")
image.resize_map_pos(w_in, h_in, w_out, h_out, fit, x, y, w=-1, h=-1)
image.resize_map_pos_reverse(w_in, h_in, w_out, h_out, fit, x, y, w=-1, h=-1)

img.draw_rect(x, y, w, h, image.COLOR_RED)
img.draw_string(x, y, label, image.COLOR_RED)
qrcodes = img.find_qrcodes()
blobs = img.find_blobs([[0, 80, 40, 80, 10, 80]], pixels_threshold=500)
```

Result object helpers confirmed by API index:

- `QRCode`: `payload()`, `rect()`, `corners()`, `x()`, `y()`, `w()`, `h()`
- `Blob`: `rect()`, `corners()`, `x()`, `y()`, `w()`, `h()`, `pixels()`, `cx()`, `cy()`, `rotation()`
- `Rect`, `Line`, `Circle`, `AprilTag`, `DataMatrix` are indexed; generate them only when the task-specific reference exists.

Codegen-safe patterns:

```python
for code in img.find_qrcodes():
    x, y, w, h = code.rect()
    payload = code.payload()

for blob in img.find_blobs(THRESHOLDS, pixels_threshold=500):
    x, y, w, h = blob.rect()
```

Notes:

- Color thresholds are environment-dependent; generated code must mark them as placeholders.
- OCR and face recognition should use `maix.nn` task references for detection/recognition and only use `maix.image` for drawing/result geometry.
