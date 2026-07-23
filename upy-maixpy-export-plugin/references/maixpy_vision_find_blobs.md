# MaixPy Find Blobs Reference

Official URL: https://wiki.sipeed.com/maixpy/doc/en/vision/find_blobs.html

Status: seed_reference

Color blob generation uses `maix.image.find_blobs`. Generate only a conservative skeleton with an explicit placeholder LAB threshold and README tuning instructions. Do not claim the threshold is calibrated for the user's real environment.

Known safe shape:

```python
thresholds = [[0, 80, 40, 80, 10, 80]]
blobs = img.find_blobs(thresholds, pixels_threshold=500)
```

The user must tune thresholds in MaixVision or with live camera samples.
