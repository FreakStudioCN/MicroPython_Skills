# maix.rtsp

Official URL: https://wiki.sipeed.com/maixpy/api/maix/rtsp.html

Status: not_codegen_ready

Brief: RTSP module.

Stage A policy: indexed only. Do not generate streaming services or network listeners.

Officially indexed callable surface:

```python
from maix import rtsp

server = rtsp.Rtsp(ip="", port=8554, fps=30, stream_type=..., bitrate=3000000)
server.bind_camera(cam)
server.bind_audio_recorder(recorder)
server.start()
server.write(frame)
server.get_url()
server.get_urls()
server.stop()
```

Restrictions:

- RTSP requires network setup, stream lifecycle, and security decisions; keep link-only in stage A.
