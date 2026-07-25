# MaixPy UART Reference

Official URL: https://wiki.sipeed.com/maixpy/api/maix/peripheral/uart.html

Status: seed_reference

Known safe shape:

```python
from maix import uart

serial = uart.UART("/dev/ttyS1", 115200)
serial.write(b"{\"type\":\"status\",\"label\":\"ready\",\"score\":1.0,\"x\":0,\"y\":0,\"w\":0,\"h\":0}\n")
serial.write_str("{\"type\":\"status\",\"label\":\"ready\",\"score\":1.0,\"x\":0,\"y\":0,\"w\":0,\"h\":0}\n")
```

Stage A must keep baudrate at `115200` and JSONL fields fixed as `type/label/score/x/y/w/h`.

Codegen policy:

- Use `/dev/ttyS1` for MaixCAM Pro UART1.
- Set pin functions with `maix.pinmap` before opening UART.
- Do not use UART0 by default; it may be shared with system logs, Maix protocol, or boot behavior.
