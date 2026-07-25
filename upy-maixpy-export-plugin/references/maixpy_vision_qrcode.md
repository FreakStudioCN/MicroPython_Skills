# MaixPy QR Code Reference

Official URL: https://wiki.sipeed.com/maixpy/doc/zh/vision/qrcode.html

API URL: https://wiki.sipeed.com/maixpy/api/maix/image.html

Status: seed_reference

QR code generation uses `maix.image` on frames read from `maix.camera`. Generate only a conservative skeleton and keep UART JSONL fields fixed.

Officially indexed shape:

```python
codes = img.find_qrcodes()
for code in codes:
    payload = code.payload()
    x, y, w, h = code.rect()
```

QRCode object helpers:

```python
code.payload()
code.rect()
code.corners()
code.x()
code.y()
code.w()
code.h()
```

Codegen policy:

- Emit JSONL with `type="qrcode"`, `label=payload`, `score=1.0`, and bbox.
- Prefer `code.rect()` for bbox.
- If bbox helper methods are unavailable in the target MaixPy version, compute `x/y/w/h` from `corners()` when available, or emit zero bbox fields.
