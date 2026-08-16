# MicroPythonOS Cross-Device Capabilities

The canonical machine-readable snapshot is `board_capabilities.json` in this directory. It is derived from MicroPythonOS runtime board detection, board modules, and manager registrations.

## Product rule

MicroPythonOS is the hardware abstraction layer. The browser must not require a board selector, and generated Apps must not target a named board. Analyze user intent as abstract requirements such as `camera`, `audio_output`, `touch_input`, or `physical_buttons`.

At runtime, use MPOS managers to determine whether a capability exists. For camera support, `CameraManager.has_camera()` is authoritative. The JSON file is advisory metadata for planning tests, explaining compatibility, and checking a connected device after permission is granted.

Unknown and future boards are allowed. Never reject one solely because its ID is absent from the snapshot.

## Capability contract states

- `portable_api: true`: skills may generate the feature through the listed MPOS API and must add a runtime fallback.
- `portable_api: false`: the current OS abstraction is incomplete. Emit `MPOS_CAPABILITY_API_MISSING`; do not generate a board import or low-level driver.
- `.board_private`: hardware or configuration exists in a board module but is not a portable App contract.
- `contract_status: partial`: a portable API exists but cannot yet distinguish every hardware state.

Portable contracts currently cover camera, input modes, audio input/output, IMU, RGB lights, battery, SD configuration, and network state. Environmental sensors, GPS, infrared, and LoRa are marked non-portable until MicroPythonOS provides complete service APIs.

Detailed generation, lifecycle, and test rules are in `mpos-dev/reference/docs-hardware-capabilities.md`.

## Camera facts in the current snapshot

MicroPythonOS currently registers cameras for these physical board modules:

- Makerfabs MaTouch ESP32-S3 SPI IPS 2.8: OV3660
- DFRobot UNIHIKER K10: GC2145
- Waveshare ESP32-S3-Touch-LCD-2: OV5640

The desktop `linux` target registers a Video4Linux2 camera. The browser `web` target does not currently emulate a camera.

`os_registrations[]` records only what current board source registers or configures. It is not a complete physical bill of materials. Absence from the array does not prove that every hardware revision lacks a component.

## Resolution order

1. Generate portable App code against MPOS APIs.
2. Let the running OS detect its board and register managers/devices.
3. Probe the required capability at runtime.
4. During physical test/deploy, record `DeviceInfo.hardware_id` and compare it with the JSON for diagnostics.
5. Prefer actual runtime results over stale metadata.

Do not expose low-level board details to generated App code and do not turn this file into a required board-selection list.
