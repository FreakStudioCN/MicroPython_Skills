# maix.rtmp

Official URL: https://wiki.sipeed.com/maixpy/api/maix/rtmp.html

Status: not_codegen_ready

Brief: RTMP module.

Stage A policy: indexed only. Do not generate streaming services or network publishing code.

Officially indexed callable surface:

```python
from maix import rtmp

stream = rtmp.Rtmp(host="localhost", port=1935, app="", stream="", bitrate=1000000)
stream.bind_camera(cam)
stream.bind_audio_recorder(recorder)
stream.bind_display(display)
stream.start(path="")
stream.stop()
stream.get_path()
stream.is_started()
```

Restrictions:

- Requires network and streaming product decisions; do not generate in stage A.
