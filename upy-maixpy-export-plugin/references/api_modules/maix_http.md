# maix.http

Official URL: https://wiki.sipeed.com/maixpy/api/maix/http.html

Status: not_codegen_ready

Brief: HTTP module.

Stage A policy: indexed only. Do not generate HTTP clients/servers or MaixHub calls in stage A.

Officially indexed callable surface:

```python
from maix import http

server = http.JpegStreamer(host="", port=8000, client_number=16)
server.start()
server.write(img)
server.set_html(data)
server.stop()
server.host()
server.port()
```

Restrictions:

- HTTP streaming/server code implies networking and security surface; keep link-only in stage A.
