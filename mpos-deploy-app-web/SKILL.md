---
name: mpos-deploy-app-web
description: Structured browser preview and deployment phase for MicroPythonOS Apps. Use when a backend runner needs desktop-preview, web-preview, device-copy, MPK install, firmware install guidance, permission prompts, device capability checks, deploy_result.json, and App-vs-device error classification. This does not replace classic mpos-deploy-app.
---

# MicroPythonOS Browser App Deploy

`mpos-deploy-app-web` records a deploy or preview result for one generated App. It must always expose the physical hardware path and ask permission before touching devices.

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
mpos-dev-web/reference/board_capabilities.md
mpos-dev-web/reference/board_capabilities.json
mpos-dev-web/reference/web_preview_limits.md
mpos-deploy-app/SKILL.md
```

## Modes

```text
desktop-preview
web-preview
device-copy
mpk-install
install-site
local-flash
```

## Permission Requirements

- `serial_scan`: before scanning ports.
- `device_write`: before `mpremote` copy or MPK upload.
- `firmware_flash`: before local flash or erase.
- `web_build` and `web_serve`: before building or serving Web preview when host policy requires it.

## Workflow

1. Confirm target mode from payload. Do not silently choose desktop or Web preview.
2. If physical mode is requested, request serial permission, connect to the device, detect `DeviceInfo.hardware_id` and runtime capabilities, and confirm whether MicroPythonOS is installed. Do not require the user to choose a board first.
3. If MicroPythonOS is missing or unknown, route to `install-site` guidance using `https://install.micropythonos.com/`.
4. Prefer `device-copy` for iteration when `mpremote` works.
5. Treat `deploy_mpk_install.py` or AIOREPL probe failure as `DEVICE_PROBE_FAILED`; if direct `mpremote` copy succeeds, record `device-copy` success/partial instead of App failure.
6. Use `desktop-preview` or `web-preview` as deploy records only when the user/session explicitly accepts no physical hardware validation.
7. Write `deploy_result.json` and route to `mpos-publish-app-web` when acceptable.

The connected device's runtime probe is authoritative. An unknown board ID is allowed, and a positive manager probe overrides stale or missing `board_capabilities.json` metadata.

Probe every `required_capabilities[]` entry through its portable MPOS API and record `runtime_capability_results`. Do not clear `MPOS_CAPABILITY_API_MISSING` with board metadata. Missing hardware on the connected device is `HARDWARE_CAPABILITY_UNAVAILABLE`, while destructive SD/device operations require a separate permission prompt.

## Output

`deploy_result.json` includes mode, hardware availability, board, serial port, MicroPythonOS installed status, permission decisions, commands, logs, result, warnings, structured errors, and handoff.
