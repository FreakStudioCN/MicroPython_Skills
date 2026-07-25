# maix.network

Official URL: https://wiki.sipeed.com/maixpy/api/maix/network.html

Status: not_codegen_ready

Brief: network module.

Stage A policy: indexed only. Do not generate network, RTSP, RTMP, WebRTC, HTTP, or MaixHub client code in this Skill stage.

Officially indexed callable surface:

```python
from maix import network

network.have_network()
```

Indexed submodule:

- `maix.network.wifi`

Restrictions:

- Stage A generated scripts must not depend on Wi-Fi/network setup.
- Use network APIs only in a future explicit network/streaming tool mode.
