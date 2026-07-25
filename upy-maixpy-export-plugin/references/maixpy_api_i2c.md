# MaixPy I2C Reference

Official URL: https://wiki.sipeed.com/maixpy/api/maix/peripheral/i2c.html

Status: seed_reference

I2C is available through the MaixPy peripheral package. Stage A Sipeed vision export does not generate I2C code by default; use it only when the user explicitly selects an I2C external device and the device wiring/address are known.

Officially indexed shape:

```python
from maix import i2c

bus = i2c.I2C(id, i2c.Mode.MASTER, freq=100000)
devices = bus.scan()
bus.writeto(addr, data)
data = bus.readfrom(addr, length)
bus.writeto_mem(addr, mem_addr, data, mem_addr_size=8, mem_addr_le=False)
data = bus.readfrom_mem(addr, mem_addr, length, mem_addr_size=8, mem_addr_le=False)
```

Codegen policy:

- Do not guess I2C bus id, pins, address, or register map.
- External sensors should have a task-specific reference under `maix.ext_dev` or a board/device profile before code generation.
