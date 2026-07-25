# MaixPy Code Generation Task Index

Status: task_index_seed

This file routes a user vision task to local references. Do not use it as the complete MaixPy API module index; use `maixpy_api_module_index.md` for full module coverage.

| task | required references | optional examples |
|---|---|---|
| camera preview | `maixpy_api_camera.md`, `maixpy_api_display.md`, `api_modules/maix_camera.md`, `api_modules/maix_display.md`, `api_modules/maix_app.md` | `examples/camera_display_preview.py` |
| UART JSONL output | `maixpy_api_uart.md`, `maixpy_api_pinmap.md`, `api_modules/maix_peripheral.md`, `api_modules/maix_err.md` | `examples/uart_jsonl_bridge.py` |
| YOLOv5 detection | `maixpy_ai_yolo.md`, `maixpy_api_camera.md`, `maixpy_api_display.md`, `api_modules/maix_nn.md`, `api_modules/maix_image.md` | `examples/yolo_uart_jsonl.py` |
| YOLOv8/YOLO11/YOLOWorld detection | `maixpy_ai_yolo.md`, `api_modules/maix_nn.md` | conservative only; require explicit model family and model path |
| QR code | `maixpy_vision_qrcode.md`, `api_modules/maix_image.md` | `examples/qrcode_jsonl.py` |
| color blob | `maixpy_vision_find_blobs.md`, `api_modules/maix_image.md` | `examples/find_blobs_jsonl.py` |
| face recognition | `maixpy_ai_face_recognition.md`, `api_modules/maix_nn.md`, `api_modules/maix_fs.md` | `examples/face_recognition_jsonl.py` |
| OCR | `maixpy_ai_ocr.md`, `api_modules/maix_nn.md`, `api_modules/maix_i18n.md`, `api_modules/maix_fs.md` | `examples/ocr_jsonl.py` |
| classifier | `api_modules/maix_nn.md`, task-specific classifier reference | partial until classifier example is added |
| tracker | `api_modules/maix_tracker.md`, object-detection task reference | partial unless receiver JSONL supports track ids |
| audio | `api_modules/maix_audio.md` | partial/link-only unless explicit audio task and hardware route are supplied |
| touch UI | `api_modules/maix_touchscreen.md`, `api_modules/maix_display.md` | partial unless explicit touch UI task and screen orientation are supplied |
| video record/playback | `api_modules/maix_video.md` | link-only by default |
| RTSP/RTMP/WebRTC/HTTP/UVC/network | `api_modules/maix_network.md`, `api_modules/maix_rtsp.md`, `api_modules/maix_rtmp.md`, `api_modules/maix_webrtc.md`, `api_modules/maix_http.md`, `api_modules/maix_uvc.md` | link-only; do not generate in stage A |
| custom model placeholder | `maixhub_model_workflow.md`, `maixpy_ai_yolo.md`, `api_modules/maix_fs.md` | `examples/model_path_placeholder.py` |

If a required reference is missing or marked `Status: needs_full_crawl`, return `partial` instead of writing unverified API code. If a reference is marked `Status: not_codegen_ready`, return README/link-only guidance unless a later protocol explicitly enables that feature.

Do not describe missing local reference coverage as "MaixPy does not support this API". Use "local reference is not codegen-ready" and cite the official URL when available.
