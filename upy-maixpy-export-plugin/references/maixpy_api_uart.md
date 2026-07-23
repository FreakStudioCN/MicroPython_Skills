# MaixPy UART Reference

Official seed: https://wiki.sipeed.com/maixpy/

Status: seed_reference

Known safe shape:

```python
from maix import uart

serial = uart.UART("/dev/ttyS1", 115200)
serial.write(b"{\"type\":\"status\",\"label\":\"ready\",\"score\":1.0,\"x\":0,\"y\":0,\"w\":0,\"h\":0}\n")
```

Stage A must keep baudrate at `115200` and JSONL fields fixed as `type/label/score/x/y/w/h`.

