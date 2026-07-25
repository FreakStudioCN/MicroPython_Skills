# maix.sys

Official URL: https://wiki.sipeed.com/maixpy/api/maix/sys.html

Status: seed_reference

Brief: system module.

Stage A policy: diagnostics-only unless explicitly requested. Do not generate reboot/poweroff/system mutation code in stage A.

Officially indexed callable surface:

```python
from maix import sys

sys.os_version()
sys.maixpy_version()
sys.runtime_version()
sys.device_configs(cache=True)
sys.device_id(cache=True)
sys.device_name(cache=True)
sys.host_name()
sys.host_domain()
sys.ip_address()
sys.mac_address()
sys.memory_info()
sys.bytes_to_human(bytes, precision=2, base=1024, units=[], sep=" ")
sys.cpu_freq()
sys.cpu_temp()
sys.cpu_usage()
sys.npu_freq()
sys.npu_usage()
sys.disk_usage(path="/")
sys.disk_partitions(only_disk=True)
sys.is_support(feature)
```

Codegen guidance:

- Generated README may mention `sys.maixpy_version()` as a manual diagnostic.
- Generated `main.py` should not depend on `sys.ip_address()` or network state unless a network task is explicitly enabled.
- Never generate `sys.poweroff()` or `sys.reboot()` in stage A.
