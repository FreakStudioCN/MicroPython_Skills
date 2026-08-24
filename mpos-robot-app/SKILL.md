---
name: mpos-robot-app
description: Create, configure, test, package, and deploy a MicroPythonOS app for the camera-free Waveshare ESP32-S3-Touch-LCD-2 six-servo voice robot. Use for direct-PWM motion, user-editable pin profiles, I2S microphone/speaker audio, device-side Wi-Fi ASR/LLM/TTS conversations, uPyPI/MIP runtime dependencies, and resumable local or browser-hosted Skill sessions. This Skill supplies no website or backend implementation and does not depend on other MPOS Skills or micropythonos-ai-app-builder.
---

# MPOS Robot App

## Scope

Create only the Skill-driven MicroPythonOS robot App and its artifacts. Do not create a website, backend, frontend, browser UI, or AI App Builder integration. Accept calls from a local agent or an external website host through the same protocol without depending on that host's implementation.

Target `Waveshare ESP32-S3-Touch-LCD-2` with the MicroPythonOS board ID `waveshare_esp32_s3_touch_lcd_2`. Do not silently substitute the Waveshare 2.1, 2.8, or 2.8C boards.

## Read references

- Read [hardware.md](references/hardware.md) before selecting or validating pins.
- Read [protocol.md](references/protocol.md) for every session, checkpoint, retry, cancellation, permission, error, or artifact operation.
- Read [dependencies.md](references/dependencies.md) before resolving or installing ASR/TTS/WebSocket libraries.
- Read [runtime-contract.md](references/runtime-contract.md) before generating App code, poses, actions, or conversation behavior.

## Workflow

1. Normalize the request into `mpos-robot-skill/v1`. Validate a supplied envelope with `scripts/validate_protocol.py`; create a local envelope when none is supplied.
2. Create or resume the Session. Preserve completed stages, operation receipts, permissions, dependency resolution, and the latest valid checkpoint.
3. Negotiate capabilities. Never claim physical PWM, I2S, network, serial, or device tests that were not performed.
4. Request permission before file creation or overwrite, script execution, network access, dependency installation, serial access, device commands, packaging, or deployment.
5. Start from `assets/default_hardware_profile.json`. Apply user changes and run `scripts/validate_hardware_profile.py` before creating PWM or I2S objects.
6. Resolve third-party drivers with `scripts/resolve_upypi_dependencies.py`. Record package metadata and versioned URLs only. Never copy, snapshot, patch, vendor, or hash-lock driver source in this Skill.
7. Copy `assets/app-template/robot_runtime` into the generated App unchanged. Generate only the App Activity, settings UI, credentials UI, named poses, personality, prompts, provider configuration, and business behavior.
8. Keep LLM output behind the structured action validator. Never execute generated Python, pin numbers, PWM values, shell commands, device commands, or file operations returned by the LLM.
9. Test profile validation, safety limits, cancellation, idempotency, dependency failures, simulated motion/audio, and secret redaction. Run physical tests only when the caller grants device access.
10. Commit a checkpoint only after the stage result and artifact manifest are atomically persisted and validated.
11. Return a structured result for success, partial completion, permission wait, device wait, cancellation, timeout, or failure.

## Fixed constraints

- Use six direct `machine.PWM` outputs at 50 Hz; do not assume an external PWM controller.
- Use the default logical mapping: one arm and two leg joints per side.
- Treat the optional camera as absent. Reject the default robot profile if a camera is connected or requested because robot defaults reuse camera-interface GPIOs.
- Preserve display, touch, IMU, battery, USB, flash, PSRAM, boot, and serial pins defined in [hardware.md](references/hardware.md).
- Persist candidate, active, and last-known-good hardware profiles separately. Saving a profile must not activate hardware.
- Use half-duplex audio in the first version. Stop RX before TX and stop TX before RX.
- Let the robot connect directly over Wi-Fi to ASR, LLM, and TTS. Do not route runtime conversation through the Skill host.
- Keep Wi-Fi and provider secrets out of prompts, checkpoints, artifacts, logs, screenshots, and packages.
- Treat `fastb64` as a target-firmware capability already validated by the project. Probe it; do not modify `micropython-embedded` or rewrite uPyPI drivers.

## Protected template

Treat every file under `assets/app-template/robot_runtime` as project-owned protected code. Verify only these project-owned files when detecting template modification. Exclude all uPyPI packages and installed driver files from template hashes and artifacts.

## Completion

Do not report completion until the requested stages have finished, the output manifest is valid, secrets are absent, and every performed side effect has an operation receipt. Report unperformed physical tests explicitly.
