# maix.video

Official URL: https://wiki.sipeed.com/maixpy/api/maix/video.html

Status: seed_reference

Brief: video module.

Stage A policy: indexed for future recording/playback workflows. Do not generate video file workflows in stage A.

Indexed classes:

- `Context`
- `Frame`
- `Packet`
- `Encoder`
- `Decoder`
- `Video`
- `VideoRecorder`

Officially indexed callable surface:

```python
from maix import video

video.timebase_to_us(timebase, value)
video.timebase_to_ms(timebase, value)

enc = video.Encoder(path="", width=2560, height=1440, format=..., type=..., framerate=30)
enc.bind_camera(cam)
frame = enc.encode(img)
enc.push(frame)
enc.pop(block_ms=1000)

dec = video.Decoder(path, format=...)
ctx = dec.decode(block=True)

v = video.Video(path="", width=2560, height=1440, format=..., framerate=30)
v.open(path="", fps=30.0)
packet = v.encode(img)
img = v.decode(frame)
v.finish()
```

Restrictions:

- Do not record, encode, decode, or write video files from the default Sipeed vision export.
- Video workflows need storage, audio, frame timing, and cleanup policies.
