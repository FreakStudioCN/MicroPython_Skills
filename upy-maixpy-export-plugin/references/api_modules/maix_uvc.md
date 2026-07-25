# maix.uvc

Official URL: https://wiki.sipeed.com/maixpy/api/maix/uvc.html

Status: not_codegen_ready

Brief: UVC module.

Stage A policy: indexed only. Do not generate UVC camera/device-mode code in stage A.

Officially indexed callable surface:

```python
from maix import uvc

uvc.helper_fill_mjpg_image(buf, size, img)

server = uvc.UvcServer(cb=None)
server.set_cb(cb)
server.run()
server.stop()

streamer = uvc.UvcStreamer()
streamer.show(img)
streamer.use_mjpg(1)
```

Restrictions:

- UVC changes the device-mode/USB behavior; keep it out of stage A MaixPy export.
