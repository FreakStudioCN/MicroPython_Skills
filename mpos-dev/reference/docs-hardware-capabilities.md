# Cross-Device Hardware Capability Rules

MicroPythonOS owns board detection, drivers, GPIO/pin maps, bus sharing, orientation, units, and hardware lifecycle. Skills own requirement classification, portable API selection, fallback behavior, static policy checks, and test planning.

## Generation boundary

Normal generated Apps must not:

- import `mpos.board.*`;
- import or instantiate `machine.Pin`, `machine.I2C`, `machine.SPI`, `machine.UART`, `machine.I2S`, `machine.ADC`, or `neopixel.NeoPixel`;
- import board-specific camera, sensor, radio, touch, display, audio, or power drivers;
- embed GPIO numbers, I2C addresses, bus IDs, camera orientation fixes, or board names.

Use an MPOS root-exported manager when `board_capabilities.json` marks the feature contract `portable_api: true`. If a requested onboard feature has no portable API, emit `MPOS_CAPABILITY_API_MISSING`; do not search for a driver or generate board-private code.

External accessories are a separate advanced workflow. They require an explicit `required_accessories` entry, wiring/bus confirmation, dependency handoff, permission for device operations, and conflict validation. They must never be inferred silently from a request for an onboard feature.

## Portable capability probes

| Capability | Runtime probe/API | Required fallback |
|---|---|---|
| Camera | `CameraManager.has_camera()` | Keep non-camera UI usable |
| Audio output | `bool(AudioManager.get_outputs())` | Disable playback or use visual feedback |
| Audio input | `bool(AudioManager.get_inputs())` | Disable recording and explain why |
| IMU | `SensorManager.get_default_sensor(type) is not None` | Show unavailable state; never fake physical data |
| RGB lights | `LightsManager.is_available()` and `get_led_count()` | Keep UI usable without LEDs |
| Battery | `BatteryManager.has_battery()` | Hide battery-only UI; do not display false 0% |
| SD configuration | `SDCardManager.get_mode() is not None` | Use App/internal storage when possible |
| Pointer/touch | `InputManager.has_pointer()` | Provide keypad/encoder focus navigation |
| Keypad | `InputManager.has_indev_type(lv.INDEV_TYPE.KEYPAD)` | Preserve pointer navigation |
| Encoder | `InputManager.has_indev_type(lv.INDEV_TYPE.ENCODER)` | Preserve pointer/keypad navigation |
| Network | `ConnectivityManager.is_online()` | Offline state, retry, or cached data |

GPS, infrared, LoRa, and board-private environmental sensors currently lack a complete portable MPOS service contract. A manager class containing pins or a raw driver object is not sufficient.

## Input requirements

Interactive Apps must not assume touch. Every primary action must be reachable with an LVGL focus group, focused state must be visible, and dialogs/lists/keyboards must have a non-pointer path. Test pointer and keypad/encoder modes separately when the host supports them.

## Lifecycle and destructive operations

- Stop audio playback and recording when the Activity pauses or exits.
- Release camera sessions and verify that launcher input still works.
- Clear or restore App-owned light state on exit.
- Do not mount, format, erase, flash, or write a device without the corresponding permission.
- `SDCardManager.format()` always requires an explicit destructive-operation prompt.
- A Web/desktop target missing real hardware produces a preview limitation or partial result, not automatic App repair.

## Validation

Generation must scan imports and constructor calls for forbidden direct hardware access. Testing must record each required capability as `available`, `unavailable`, `emulated`, `unsupported_in_preview`, or `not_tested`, together with the probe and evidence. Physical success requires capability-specific operation plus post-exit resource recovery.
