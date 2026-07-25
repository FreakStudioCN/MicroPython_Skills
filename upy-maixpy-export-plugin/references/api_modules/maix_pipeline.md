# maix.pipeline

Official URL: https://wiki.sipeed.com/maixpy/api/maix/pipeline.html

Status: seed_reference

Brief: video stream processing via pipeline.

Stage A policy: indexed for future streaming/pipeline work. Do not generate pipeline code in stage A.

Officially indexed callable surface:

```python
from maix import pipeline

stream.data_count()
stream.data_size(idx)
stream.has_sps_frame()
stream.has_pps_frame()
stream.has_i_frame()
stream.has_p_frame()
stream.pts()

frame = pipeline.Frame(frame_capsule, auto_delete=False, from="")
frame.width()
frame.height()
frame.format()
frame.to_image()
frame.stride(idx)
```

Restrictions:

- Pipeline frames often rely on lower-level media buffers/capsules. Do not generate this in stage A user scripts.
