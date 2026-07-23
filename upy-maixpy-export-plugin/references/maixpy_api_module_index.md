# MaixPy API Module Index

Source URL: https://wiki.sipeed.com/maixpy/api/index.html

Status: index_seed

This file is the complete module coverage checklist. Each module must also have a local file under `references/api_modules/`.

| module | brief | local reference | stage A policy |
|---|---|---|---|
| `maix.err` | maix.err module | `references/api_modules/maix_err.md` | A0 direct support |
| `maix.tensor` | maix.tensor module | `references/api_modules/maix_tensor.md` | A1 skeleton only |
| `maix.image` | maix.image module, image related definition and functions | `references/api_modules/maix_image.md` | A0 direct support |
| `maix.camera` | maix.camera module, access camera device and get image from it | `references/api_modules/maix_camera.md` | A0 direct support |
| `maix.display` | maix.display module, control display device and show image on it | `references/api_modules/maix_display.md` | A0 direct support |
| `maix.ext_dev` | maix.ext_dev module | `references/api_modules/maix_ext_dev.md` | A1 skeleton only |
| `maix.comm` | maix.comm module | `references/api_modules/maix_comm.md` | A1 skeleton only |
| `maix.peripheral` | Chip's peripheral driver | `references/api_modules/maix_peripheral.md` | A0 direct support |
| `maix.nn` | maix.nn module | `references/api_modules/maix_nn.md` | A0 direct support |
| `maix.network` | maix.network module | `references/api_modules/maix_network.md` | A2 link only |
| `maix.audio` | maix.audio module | `references/api_modules/maix_audio.md` | A1 skeleton only |
| `maix.example` | example module | `references/api_modules/maix_example.md` | A3 example index |
| `maix.fs` | maix.fs module | `references/api_modules/maix_fs.md` | A0 direct support |
| `maix.i18n` | maix.i18n module | `references/api_modules/maix_i18n.md` | A1 skeleton only |
| `maix.thread` | maix.thread module | `references/api_modules/maix_thread.md` | A1 skeleton only |
| `maix.util` | maix.util module | `references/api_modules/maix_util.md` | A1 skeleton only |
| `maix.protocol` | maix.protocol module | `references/api_modules/maix_protocol.md` | A1 skeleton only |
| `maix.app` | maix.app module | `references/api_modules/maix_app.md` | A0 direct support |
| `maix.log` | maix.log module | `references/api_modules/maix_log.md` | A0 direct support |
| `maix.time` | maix.time module | `references/api_modules/maix_time.md` | A0 direct support |
| `maix.sys` | maix.sys module | `references/api_modules/maix_sys.md` | A1 skeleton only |
| `maix.uvc` | maix.uvc module | `references/api_modules/maix_uvc.md` | A2 link only |
| `maix.tracker` | maix.tracker module | `references/api_modules/maix_tracker.md` | A1 skeleton only |
| `maix.rtsp` | maix.rtsp module | `references/api_modules/maix_rtsp.md` | A2 link only |
| `maix.pipeline` | maix.pipeline module, video stream processing via pipeline | `references/api_modules/maix_pipeline.md` | A1 skeleton only |
| `maix.touchscreen` | maix.touchscreen module | `references/api_modules/maix_touchscreen.md` | A1 skeleton only |
| `maix.rtmp` | maix.rtmp module | `references/api_modules/maix_rtmp.md` | A2 link only |
| `maix.webrtc` | maix.webrtc module | `references/api_modules/maix_webrtc.md` | A2 link only |
| `maix.video` | maix.video module | `references/api_modules/maix_video.md` | A1 skeleton only |
| `maix.http` | maix.http module | `references/api_modules/maix_http.md` | A2 link only |
| `maix.ahrs` | maix.ahrs module | `references/api_modules/maix_ahrs.md` | A1 skeleton only |

Policy:

- A0 modules may be used in generated `main.py` only when their detailed reference and task example are present.
- A1 modules require explicit user intent and must remain conservative skeletons with README prerequisites.
- A2 modules are indexed but not auto-generated in stage A because they imply networking, streaming, services, or device-mode complexity.
- A3 modules are examples/source index only.

