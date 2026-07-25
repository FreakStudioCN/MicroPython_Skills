# maix.ext_dev

Official URL: https://wiki.sipeed.com/maixpy/api/maix/ext_dev.html

Status: seed_reference

Brief: external device module.

Stage A policy: indexed for future external device support. Do not generate concrete external-device code unless the user selects that device and the corresponding subpage/reference exists.

Officially indexed callable surface:

- The aggregate `maix.ext_dev` page does not expose a direct stage A callable surface in the API index.
- Code generation must use a concrete child module reference, for example `maix.ext_dev.qmi8658` or `maix.ext_dev.axp2101`, after that child reference has been added and checked.

Indexed submodules from official API navigation:

- `maix.ext_dev.imu`
- `maix.ext_dev.qmi8658`
- `maix.ext_dev.cmap`
- `maix.ext_dev.mlx90640`
- `maix.ext_dev.tof100`
- `maix.ext_dev.tmc2209`
- `maix.ext_dev.pmu`
- `maix.ext_dev.bm8563`
- `maix.ext_dev.fp5510`
- `maix.ext_dev.axp2101`

Codegen guidance:

- These are external device drivers, not generic MicroPython drivers.
- Stage A Sipeed vision export should not auto-add external sensors or PMU code.
- If a future board profile requires QMI8658/AXP2101/BM8563, add a task-specific reference and hardware mapping first.
