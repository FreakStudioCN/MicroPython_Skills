---
name: mpos-test-app-web
description: Structured browser testing phase for generated MicroPythonOS Apps. Use when a backend runner needs desktop smoke, optional Web preview, screenshots, runner logs, classification of App vs OS/toolchain failures, app_test_result.json, artifact manifest entries, and retryable structured errors. This does not replace classic mpos-test-app.
---

# MicroPythonOS Browser App Testing

`mpos-test-app-web` tests a generated App in the browser workflow. It records evidence for the frontend and does not repair code directly.

## Shared Requirements

Before acting, read `mpos-dev-web/SKILL.md`, then read these references as needed:

```text
mpos-dev-web/reference/protocol.md
mpos-dev-web/reference/state_machine.md
mpos-dev-web/reference/error_codes.md
mpos-dev-web/reference/artifact_manifest.md
mpos-dev-web/reference/permission_prompts.md
mpos-dev-web/reference/capabilities.md
mpos-dev-web/reference/visual_assets.md
```

Also read `mpos-dev/reference/mpos_api_summary.json` and `mpos-dev/reference/lvgl_api_summary.json` completely. Do not skip them because this phase appears simple.

Never modify classic `mpos-*` skills, MicroPythonOS OS/framework/build/lvgl files, or App directories outside the current workflow target.

## Read First

Also read:

```text
mpos-dev/reference/docs-deploy-targets.md
mpos-dev/reference/docs-web-port.md
mpos-dev-web/reference/web_preview_limits.md
mpos-dev/reference/docs-hardware-capabilities.md
mpos-dev/reference/docs-camera-apps.md
mpos-test-app/SKILL.md
```

## Default Tests

- Run desktop smoke when `capabilities.desktop_preview=true` and `script_run` permission is available.
- Use classic `mpos-test-app` scripts or equivalent host actions.
- Web preview is optional. Run it only when requested and `capabilities.web_preview=true`.
- Always provide manual reproduction commands in `app_test_result.json`.
- For every `app_runtime_image`, validate the LVGL v9 header, declared dimensions/stride/format, file hash, App reference, and packaged path before launch.
- For every Web-sourced runtime image, validate that its `visual_asset_source_record` matches the downloaded source hash and contains sufficient source-page, license, and attribution evidence for packaging.
- Launch the App and capture screenshot evidence that planned required artwork rendered. When feasible, temporarily make a required asset unavailable and verify the declared native LVGL fallback without modifying the final App tree.

## Failure Classification

- App traceback or invalid API: route to `mpos-gen-app-web` repair.
- Missing desktop binary, missing `_webrepl`, `lvgl_micropy_unix` segfault, missing `emcc`, or Web port linker errors: external/toolchain warning or blocked result.
- `machine_timer_type` Web link/build errors belong to Web port/toolchain unless logs show App code caused them.
- A browser target without camera emulation must return `WEB_PREVIEW_UNSUPPORTED` (or equivalent partial result) for the camera path. Do not route valid portable App code to repair merely because Web preview has no camera.
- For camera claims, require physical evidence that preview/capture works and that exiting restores launcher input and other Apps. Desktop layout smoke alone is insufficient.
- Record a result for every required hardware capability. Missing Web/desktop emulation is `unsupported_in_preview`/partial; missing capability on a connected device is `HARDWARE_CAPABILITY_UNAVAILABLE`; neither is an App repair request.
- Reject forbidden direct hardware access statically. Test pointer and focus/keypad navigation separately, and verify audio/light/camera cleanup after leaving the Activity.
- A missing or corrupt App runtime image, invalid `M:` path, blank render, or missing fallback is `VISUAL_ASSET_LOAD_FAILED` and routes to generation repair. A missing fixed renderer/converter is `VISUAL_ASSET_TOOLCHAIN_MISSING`; do not ask the code model to repair tooling.
- A failed search or fetch is an external acquisition failure, not an App-code repair. Missing redistribution evidence is `VISUAL_ASSET_RIGHTS_UNVERIFIED` and must select another source or use the fallback before packaging.

## Screenshots

Publish-ready screenshots must be PNG, JPEG, or WebP. BMP is raw evidence only.

For final-artifact-only or batch sessions, screenshots are required even when per-App `app_test_result.json` is not exposed to the frontend. Use the classic helper or host-equivalent action:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-test-app/scripts/capture_batch_screenshots.py \
  --repo <repo-root> \
  --app-prefix <fullname-prefix> \
  --output-dir <artifact-root>/screenshots
```

Write `screenshot_manifest.json` and add each PNG/JPEG/WebP file to `artifact_manifest.json` with role `store_screenshot`. Missing screenshots are structured errors and block `publish_ready`.

## Output

Write `app_test_result.json` with desktop launch result, controller smoke result, optional Web preview result, visual asset validation results, screenshots, visible text/widget tree when available, manual commands, warnings, structured errors, and `handoff.next_phase`.

Route:

- `success` or acceptable `partial`: `mpos-package-app-web`.
- App failure: `mpos-gen-app-web`.
- external/tooling blocked: `null` unless the user requests retry after fixing environment.
