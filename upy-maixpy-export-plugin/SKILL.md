---
name: upy-maixpy-export-plugin
description: Standalone tool-style Skill for generating MaixPy code for Sipeed vision modules such as MaixCAM Pro. Use when the plugin global Sipeed vision-module code-generation tool or a local test asks to create sipeed_vision/main.py and sipeed_vision/README.md for a MaixPy vision coprocessor over UART JSON Lines. This Skill is not part of the canonical MicroPython workflow, does not flash firmware, does not use mpremote, does not call MaixHub APIs, and does not modify firmware/.
---

# upy-maixpy-export-plugin

Generate standalone MaixPy code for a Sipeed vision module, normally MaixCAM Pro, used as an external vision coprocessor. The generated code runs on MaixPy/MaixVision, not on the user's ESP32/Pico/STM32 MicroPython master project.

Use this Skill only from the plugin global Sipeed vision-module code-generation entry, or from local direct tests that use the same `start_phase` envelope shape.

## Hard Boundaries

- Treat this as a standalone/global tool, not a MicroPython canonical phase.
- Always output `next_phase=null`.
- Do not output `next_phase=select-hw`, `upy-flash-mpy-firmware-plugin`, `upy-scaffold-plugin`, `upy-generate-plugin`, or `upy-deploy-plugin`.
- Do not write `firmware/`.
- Do not write `project-manifest.json`.
- Do not generate master MCU UART receiver source in stage A.
- Do not call `mpremote`, `esptool`, `mip.install`, MaixHub APIs, SFTP, firmware download, firmware flashing, or device deployment.
- Do not open links automatically. Return official links for the user to click.
- Do not fetch the network during code generation. Only Skill maintenance scripts may refresh `references/`.
- Do not invent MaixPy APIs from memory. If required references or examples are missing, return `partial`.

## Input Contract

Accept a `start_phase` envelope with `protocol_version="1.0"`, `phase="upy-maixpy-export-plugin"`, a stable `session_id`, and `idempotency_key="upy-maixpy-export-plugin:<session_id>:start:v1"`.

The payload must describe:

- `target_runtime="maixpy"`
- `target_device="maixcam_pro"`
- `output_root="sipeed_vision"`
- `vision_task.type`
- UART defaults: `UART1`, `A19`, `A18`, `115200`, `jsonl`
- capabilities matching the current plugin host: `file_operation=true`, `script_run=true`, `checkpoint_resume=false`, `device_command=false`, `network=false`

If `protocol_version` is not `"1.0"`, emit `phase_complete(result="failed")` with code `MAIXPY_EXPORT_INVALID_INPUT`.

## Reference Loading

Before generating code, read `references/maixpy_api_index.md` to choose task-specific references. Use `references/maixpy_api_module_index.md` and `references/maixpy_api_crawl_manifest.json` to verify API coverage.

Load only the references needed by the task:

- Camera preview: `maixpy_api_camera.md`, `maixpy_api_display.md`, `examples/camera_display_preview.py`
- UART JSONL bridge: `maixpy_api_uart.md`, `maixpy_api_pinmap.md`, `examples/uart_jsonl_bridge.py`
- YOLO: `maixpy_ai_yolo.md`, `examples/yolo_uart_jsonl.py`
- QR code: `maixpy_vision_qrcode.md`, `references/api_modules/maix_image.md`, `examples/qrcode_jsonl.py`
- Color blob: `maixpy_vision_find_blobs.md`, `references/api_modules/maix_image.md`, `examples/find_blobs_jsonl.py`
- Face recognition: `maixpy_ai_face_recognition.md`, `references/api_modules/maix_nn.md`, `examples/face_recognition_jsonl.py`
- OCR: `maixpy_ai_ocr.md`, `references/api_modules/maix_nn.md`, `references/api_modules/maix_i18n.md`, `examples/ocr_jsonl.py`

If any required reference is marked `Status: needs_full_crawl`, return `partial` instead of writing unverified API code. If a reference is marked `Status: not_codegen_ready`, return README/link-only guidance unless a later protocol explicitly enables that feature.

Do not describe missing local reference coverage as "MaixPy does not support this API" or "the official API is unavailable". Use "local Skill reference is not codegen-ready" and cite the official URL when available.

## Full API Index Requirement

Build the reference library from:

```text
https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html
https://wiki.sipeed.com/maixpy/
https://wiki.sipeed.com/maixpy/api/index.html
https://wiki.sipeed.com/maixvision
https://wiki.sipeed.com/maixpy/doc/zh/basic/maixvision.html
https://github.com/sipeed/maixpy
```

`api/index.html` is the authority for MaixPy module coverage. Its complete module list must be represented in:

```text
references/maixpy_api_module_index.md
references/maixpy_api_crawl_manifest.json
references/api_modules/*.md
```

Every module entry must include official URL, brief, local reference path, crawl status, and codegen policy. Aggregate pages such as `maix.ext_dev`, `maix.comm`, `maix.peripheral`, `maix.nn`, and `maix.network` must not hide their subpages. UART, GPIO, I2C, SPI, and pinmap references are required for stage A UART generation.

## Generation Rules

Write only:

```text
sipeed_vision/main.py
sipeed_vision/README.md
```

Use MaixPy APIs, not MicroPython `machine.*`.

Required UART defaults:

```text
MaixCAM Pro A19 UART1_TX -> master MCU RX
MaixCAM Pro A18 UART1_RX -> master MCU TX
MaixCAM Pro GND          -> master MCU GND
baudrate                 -> 115200
protocol                 -> JSON Lines
```

Ignore user-supplied baudrate changes in stage A. If the user asks for a different baudrate, keep `115200` and add a warning in README and `phase_complete.payload.warnings`.

JSONL output fields are fixed: `type`, `label`, `score`, `x`, `y`, `w`, `h`.

For a task without a bounding box, keep the fixed fields and use `x=0`, `y=0`, `w=0`, `h=0`. Additional fields are not part of stage A unless the user explicitly asks and the receiving side is still documented as optional.

Always use `app.need_exit()` in loops when examples show an event loop.

## README Rules

`sipeed_vision/README.md` must state:

- `main.py` runs on MaixCAM Pro/MaixPy/MaixVision, not the MicroPython master board.
- Firmware flashing, OS upgrade, model training, MaixHub, MaixVision connection, and deployment are manual external flows.
- UART wiring uses A19/A18/GND, UART1, 115200, JSON Lines.
- MaixCAM Pro IO is 3.3 V and not 5 V tolerant.
- UART0 is not preferred because it may be related to system logs, maix protocol, or boot behavior.
- Official links:
  - https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html
  - https://wiki.sipeed.com/maixpy/
  - https://wiki.sipeed.com/maixvision
  - https://wiki.sipeed.com/maixpy/doc/zh/basic/maixvision.html
  - https://github.com/sipeed/maixpy
- If AI models are involved, the model path is a prerequisite, normally under `/root/models`.

## Task Support

Default stage A support:

- camera preview
- YOLO detection skeleton
- UART JSONL output
- custom model path placeholder
- QR code skeleton if references/examples are present
- color blob skeleton if references/examples are present

Conditional stage A support:

- Face recognition can be a conservative skeleton only when references/examples are present. README must explain model files, face database, and enrollment prerequisites.
- OCR can be a conservative skeleton only when references/examples are present. README must explain model files, font files, and MaixPy version prerequisites.

For `maix.nn` features, local references now cover YOLOv5, YOLOv8, YOLO11, YOLOWorld, FaceRecognizer, and PP_OCR at seed level. YOLOv5 remains the default detection skeleton. Face recognition and OCR may be generated only as conservative runtime skeletons with explicit model/database/asset prerequisites. Classifier, tracker, custom tensor, audio, touch UI, video, pipeline, network, streaming, and WebRTC tasks remain partial or link-only unless the task-specific reference/example is added.

Unsupported in stage A:

- MaixHub API automation
- automatic model training or download
- RTSP/RTMP/WebRTC/network service generation
- firmware flashing or device upload
- master MCU receiver code generation

## Protocol Output

Finish with `phase_complete`. The current plugin protocol accepts only `success`, `failed`, and `partial`; do not invent `result="cancelled"`.

Cancellation uses `result="partial"`, `checkpoint="cancelled"`, and error code `MAIXPY_CANCELLED_BY_USER`.

## Error Codes

Use stable local error codes:

- `MAIXPY_EXPORT_INVALID_INPUT`
- `MAIXPY_REFERENCE_INDEX_MISSING`
- `MAIXPY_REFERENCE_INSUFFICIENT`
- `MAIXPY_UNSUPPORTED_TASK`
- `MAIXPY_FILE_WRITE_DENIED`
- `MAIXPY_FILE_CONFLICT`
- `MAIXPY_VALIDATION_FAILED`
- `MAIXPY_CANCELLED_BY_USER`
- `MAIXPY_TIMEOUT`
- `MAIXPY_INTERNAL_ERROR`

Every structured error must include `code`, `severity`, `phase_step`, `retryable`, `message`, `details`, and `next_action`.

## Validation

Use bundled scripts when available:

```text
python scripts/validate_reference_index.py --skill-root <skill-root>
python scripts/validate_maixpy_export.py --project-root <project-root>
```

If `script_run=false`, do not claim validation passed. Do LLM self-check and return a warning.

## Local Test Mode

Local direct tests may write under a temporary project root and session root. They must produce the same `phase_complete` payload shape as plugin mode. Local tests must not be treated as hardware proof.
