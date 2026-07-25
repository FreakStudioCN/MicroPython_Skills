# MaixPy Find Blobs Reference

Official URL: https://wiki.sipeed.com/maixpy/doc/en/vision/find_blobs.html

API URL: https://wiki.sipeed.com/maixpy/api/maix/image.html

Status: seed_reference

Color blob generation uses `maix.image.find_blobs`. Generate only a conservative skeleton with an explicit placeholder LAB threshold and README tuning instructions. Do not claim the threshold is calibrated for the user's real environment.

Officially indexed shape:

```python
thresholds = [[0, 80, 40, 80, 10, 80]]
blobs = img.find_blobs(thresholds, pixels_threshold=500)
for blob in blobs:
    x, y, w, h = blob.rect()
```

Blob object helpers:

```python
blob.rect()
blob.corners()
blob.x()
blob.y()
blob.w()
blob.h()
blob.pixels()
blob.cx()
blob.cy()
blob.rotation()
```

The user must tune thresholds in MaixVision or with live camera samples.

Codegen policy:

- Emit JSONL with `type="color"`, `label="color_blob"`, `score=1.0`, and bbox.
- README must call the LAB threshold a placeholder.
