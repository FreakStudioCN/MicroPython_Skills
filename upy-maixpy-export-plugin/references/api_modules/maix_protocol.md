# maix.protocol

Official URL: https://wiki.sipeed.com/maixpy/api/maix/protocol.html

Status: not_codegen_ready

Brief: protocol module.

Stage A policy: do not confuse Maix protocol with the user's custom UART JSON Lines payload. Stage A uses plain JSONL over UART1.

Officially indexed callable surface:

```python
from maix import protocol

protocol.crc16_IBM(data)
msg = protocol.MSG()
parser = protocol.Parser(buff_size=1024, header=3148663466)
parser.push_data(data)
parser.decode(data)
parser.encode_resp_ok(cmd, body=None)
parser.encode_report(cmd, body=None)
parser.encode_resp_err(cmd, code, msg)
```

Restrictions:

- Do not use `maix.protocol` for the stage A UART JSON Lines bridge.
- The user-facing protocol remains one JSON object per line with `type/label/score/x/y/w/h`.
- If a later feature chooses Maix protocol framing, it must be a separate protocol contract and plugin UI mode.
