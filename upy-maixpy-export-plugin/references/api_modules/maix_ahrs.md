# maix.ahrs

Official URL: https://wiki.sipeed.com/maixpy/api/maix/ahrs.html

Status: seed_reference

Brief: AHRS module.

Stage A policy: indexed for future IMU/fusion workflows. Do not generate AHRS code unless the user explicitly requests it and provides calibrated IMU/magnetometer data sources.

Officially indexed callable surface:

```python
from maix import ahrs, tensor

fusion = ahrs.MahonyAHRS(kp, ki)
fusion.init(ax, ay, az, mx=0, my=0, mz=0)
fusion.update(ax, ay, az, gx, gy, gz, mx, my, mz, dt)
angle = fusion.get_angle(
    tensor.Vector3f(ax, ay, az),
    tensor.Vector3f(gx, gy, gz),
    tensor.Vector3f(mx, my, mz),
    dt,
    radian=False,
)
fusion.reset()
```

Restrictions:

- AHRS requires calibrated accelerometer/gyroscope/magnetometer data. Do not generate it for camera-only tasks.
