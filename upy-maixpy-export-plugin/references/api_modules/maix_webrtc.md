# maix.webrtc

Official URL: https://wiki.sipeed.com/maixpy/api/maix/webrtc.html

Status: not_codegen_ready

Brief: WebRTC module.

Stage A policy: indexed only. Do not generate WebRTC/network code.

Officially indexed callable surface:

```python
from maix import webrtc

rtc = webrtc.WebRTC(ip="", port=8000, stream_type=..., rc_type=..., bitrate=3000000, gop=60)
rtc.bind_camera(cam)
rtc.bind_audio_recorder(recorder)
rtc.start()
rtc.write(frame)
rtc.get_url()
rtc.get_urls()
rtc.stop()
```

Restrictions:

- WebRTC requires networking, signaling, STUN/server decisions, and security handling; keep link-only in stage A.
