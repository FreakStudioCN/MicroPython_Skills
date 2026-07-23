# MaixPy Code Generation Task Index

Status: task_index_seed

This file routes a user vision task to local references. Do not use it as the complete MaixPy API module index; use `maixpy_api_module_index.md` for full module coverage.

| task | required references | optional examples |
|---|---|---|
| camera preview | `maixpy_api_camera.md`, `maixpy_api_display.md`, `api_modules/maix_camera.md`, `api_modules/maix_display.md`, `api_modules/maix_app.md` | `examples/camera_display_preview.py` |
| UART JSONL output | `maixpy_api_uart.md`, `maixpy_api_pinmap.md`, `api_modules/maix_peripheral.md`, `api_modules/maix_err.md` | `examples/uart_jsonl_bridge.py` |
| YOLO detection | `maixpy_ai_yolo.md`, `maixpy_api_camera.md`, `maixpy_api_display.md`, `api_modules/maix_nn.md` | `examples/yolo_uart_jsonl.py` |
| QR code | `maixpy_vision_qrcode.md`, `api_modules/maix_image.md` | `examples/qrcode_jsonl.py` |
| color blob | `maixpy_vision_find_blobs.md`, `api_modules/maix_image.md` | `examples/find_blobs_jsonl.py` |
| face recognition | `maixpy_ai_face_recognition.md`, `api_modules/maix_nn.md`, `api_modules/maix_fs.md` | `examples/face_recognition_jsonl.py` |
| OCR | `maixpy_ai_ocr.md`, `api_modules/maix_nn.md`, `api_modules/maix_i18n.md`, `api_modules/maix_fs.md` | `examples/ocr_jsonl.py` |
| custom model placeholder | `maixhub_model_workflow.md`, `maixpy_ai_yolo.md`, `api_modules/maix_fs.md` | `examples/model_path_placeholder.py` |

If a required reference is missing or marked `Status: needs_full_crawl`, return `partial` instead of writing unverified API code.

