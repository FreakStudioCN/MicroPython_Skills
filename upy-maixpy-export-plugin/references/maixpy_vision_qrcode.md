# MaixPy QR Code Reference

Official URL: https://wiki.sipeed.com/maixpy/doc/zh/vision/qrcode.html

Status: seed_reference

QR code generation uses `maix.image` on frames read from `maix.camera`. Generate only a conservative skeleton and keep UART JSONL fields fixed.

Known safe shape:

```python
codes = img.find_qrcodes()
for code in codes:
    payload = code.payload()
```

If bounding box helper methods are unavailable in the target MaixPy version, compute `x/y/w/h` from `corners()` when available, or emit zero bounding box fields.
