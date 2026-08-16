# Camera Apps and Cross-Device Capability Rules

MicroPythonOS Apps are cross-device Apps. Do not require the user to choose a board before generation and do not generate board names, GPIO numbers, sensor models, camera drivers, or orientation workarounds in App code.

## Runtime capability check

Use the OS abstraction as the source of truth:

```python
from mpos import CameraManager

if CameraManager.has_camera():
    # Offer the camera action.
    pass
else:
    # Keep the rest of the App usable and explain that this device has no
    # camera registered by its current MicroPythonOS build.
    pass
```

An unknown or newly supported board must remain usable. A static board table may guide testing, but it must never override a successful runtime probe.

## Preferred implementation

- Use `CameraActivity` for preview, capture, settings, image orientation, buffer handling, and lifecycle cleanup.
- Use `CameraManager` when an App only needs to test availability or launch a camera flow.
- Do not import a board module or a low-level camera driver from an App.
- Do not copy GC2145, OV3660, OV5640, Video4Linux2, pin maps, byte swapping, mirroring, or rotation logic into an App. These belong to MicroPythonOS board support.
- Do not modify MicroPythonOS, LVGL, board support, or firmware to satisfy an App request.
- Release the camera when the Activity pauses or exits. A camera App must not leave input, I2C, or display resources unusable for the launcher or another App.

The native `webcam` module documented in `mpos-dev/SKILL.md` is for Linux/macOS desktop support. It is not the portable API for ESP32 Apps.

## Preview and validation

Browser preview currently has no real camera emulation. A camera-dependent path may show a clearly labeled placeholder, but the workflow must return `WEB_PREVIEW_UNSUPPORTED` or an equivalent partial result instead of rewriting valid App code.

Desktop preview proves layout and non-camera behavior. A successful camera claim requires physical-device validation: open the camera, capture an image, exit, return to the launcher, and verify that input and other Apps still work.

Known-board metadata is stored in `mpos-dev-web/reference/board_capabilities.json`. `CameraManager.has_camera()` on the running OS remains authoritative.
