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
```

Also read `mpos-dev/reference/mpos_api_summary.json` and `mpos-dev/reference/lvgl_api_summary.json` completely. Do not skip them because this phase appears simple.

Never modify classic `mpos-*` skills, MicroPythonOS OS/framework/build/lvgl files, or App directories outside the current workflow target.

## Read First

Also read:

```text
mpos-dev/reference/docs-deploy-targets.md
mpos-dev/reference/docs-web-port.md
mpos-dev-web/reference/web_preview_limits.md
mpos-test-app/SKILL.md
```

## Default Tests

- Run desktop smoke when `capabilities.desktop_preview=true` and `script_run` permission is available.
- Use classic `mpos-test-app` scripts or equivalent host actions.
- Web preview is optional. Run it only when requested and `capabilities.web_preview=true`.
- Always provide manual reproduction commands in `app_test_result.json`.

## Failure Classification

- App traceback or invalid API: route to `mpos-gen-app-web` repair.
- Missing desktop binary, missing `_webrepl`, `lvgl_micropy_unix` segfault, missing `emcc`, or Web port linker errors: external/toolchain warning or blocked result.
- `machine_timer_type` Web link/build errors belong to Web port/toolchain unless logs show App code caused them.

## Screenshots

Publish-ready screenshots must be PNG, JPEG, or WebP. BMP is raw evidence only.

## Output

Write `app_test_result.json` with desktop launch result, controller smoke result, optional Web preview result, screenshots, visible text/widget tree when available, manual commands, warnings, structured errors, and `handoff.next_phase`.

Route:

- `success` or acceptable `partial`: `mpos-package-app-web`.
- App failure: `mpos-gen-app-web`.
- external/tooling blocked: `null` unless the user requests retry after fixing environment.
