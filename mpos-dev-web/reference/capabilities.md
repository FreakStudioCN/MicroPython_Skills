# Host Capability Negotiation

The backend host must pass workflow/tool capabilities. These fields describe what the browser and runner can do; they are different from the hardware features required by an App.

Example:

```json
{
  "capabilities": {
    "file_operation": true,
    "script_run": true,
    "approval_request": true,
    "permission_request": true,
    "checkpoint_resume": true,
    "cancellation": true,
    "retry": true,
    "timeout": true,
    "desktop_preview": true,
    "web_preview": true,
    "visual_asset_render": true,
    "lvgl_image_convert": true,
    "web_image_search": true,
    "remote_image_fetch": true,
    "external_image_generation": false,
    "physical_device": false,
    "serial_port_scan": false,
    "mpremote": true,
    "firmware_flash": false,
    "network_read": true,
    "network_upload": false
  }
}
```

Rules:

- If `file_operation=false`, emit planned writes as artifacts or file operations for the host; do not write directly.
- If `script_run=false`, emit command plans and block required script phases with structured errors.
- If `physical_device=false`, do not claim hardware validation.
- If `web_preview=false`, skip Web preview with a warning.
- If `visual_asset_render=false` or `lvgl_image_convert=false`, use native LVGL fallbacks for optional artwork and block required raster artwork with `VISUAL_ASSET_TOOLCHAIN_MISSING`.
- If `web_image_search=false`, do not select `generation_mode=web`; use procedural artwork, external generation when separately allowed, or native LVGL.
- If `remote_image_fetch=false` or `network_read=false`, do not download a search result. Preserve the source candidate record and use the declared fallback.
- If `external_image_generation=false`, use the fixed procedural renderer or native LVGL. Do not silently call an external image provider.
- If `network_read=false`, skip upystore version comparison and mark it `unknown_unverified`.
- If `network_upload=false`, never upload; current publish skill is manual guidance only.

App requirements use a separate field:

```json
{
  "required_capabilities": ["camera"],
  "runtime_fallbacks": {
    "camera": "Show a camera-unavailable state while keeping the rest of the App usable."
  }
}
```

Do not add `target_board` to generation requests. Resolve device capabilities after connection through MPOS runtime managers; use `board_capabilities.json` only as advisory diagnostics.

Before generation, look up every required hardware capability in `board_capabilities.json`:

- `portable_api=true`: generate with the listed MPOS API and fallback.
- `portable_api=false`: return `MPOS_CAPABILITY_API_MISSING` rather than inventing a driver.
- Unknown capability: block automatic hardware generation and request backend/OS capability review.
