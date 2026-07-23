# Web Preview Limits

Web preview is optional. It is not equivalent to physical hardware validation.

Known boundaries:

- Browser WebAssembly has no real GPIO, ADC, IMU, camera, Bluetooth, serial bus, SD card, or physical buttons unless explicitly emulated.
- HTTP uses browser `fetch()` and is subject to CORS.
- `/data` and `/apps` may persist in IndexedDB; stale browser state can affect tests.
- Web build depends on Web port patches, Emscripten, generated `web/micropython.{js,wasm,data}`, and local tooling.
- `machine_timer_type` and related Web port linker/build errors are toolchain or OS Web port problems unless logs prove App code caused them.

Required user-facing wording:

```text
Web preview is a quick browser compatibility preview. It does not replace real hardware deployment. Apps that use camera, IMU, GPIO, serial, Bluetooth, audio devices, SD card, or physical buttons must be validated on a real MicroPythonOS device.
```

If Web preview fails:

- Preserve browser console output when available.
- Preserve build/server logs.
- Emit structured error code `WEB_PREVIEW_BUILD_FAILED`, `WEB_PREVIEW_UNSUPPORTED`, or `WEB_PREVIEW_TIMEOUT`.
- Do not ask `mpos-gen-app-web` to change App code unless the log points to an App traceback or invalid API call.
