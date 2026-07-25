# maix.comm

Official URL: https://wiki.sipeed.com/maixpy/api/maix/comm.html

Status: seed_reference

Brief: communication module.

Stage A policy: do not use this for the custom UART JSONL protocol unless a task-specific reference proves the exact API. Stage A UART uses `maix.uart` plus `maix.pinmap`.

Officially indexed callable surface:

```python
from maix import comm

proto = comm.CommProtocol(buff_size=1024, header=3148663466, method_none_raise=False)
msg = proto.get_msg(timeout=0)
proto.resp_ok(cmd, body=None)
proto.report(cmd, body=None)
proto.resp_err(cmd, code, msg)
proto.valid()

comm.CommProtocol.set_method(method)
comm.CommProtocol.get_uart_port()
comm.CommProtocol.get_uart_ports()
```

Restrictions:

- Do not replace the stage A JSON Lines protocol with `maix.comm`.
- If `maix.comm` is selected later, define a new payload schema and plugin UI mode.
