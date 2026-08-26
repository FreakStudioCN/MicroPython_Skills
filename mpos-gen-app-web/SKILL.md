---
name: mpos-gen-app-web
description: Structured browser code generation and repair for MicroPythonOS Apps. Use when a backend runner needs to create or repair App files from analysis_result.json, dependency_handoff.json, API summaries, and session checkpoints, then emit generation_result.json, file operations, artifact manifest entries, and structured errors. This does not replace classic mpos-gen-app.
---

# MicroPythonOS Browser App Generation

`mpos-gen-app-web` generates or repairs App files for the browser workflow. It is protocol-first and may emit `file_operation` events instead of direct writes when the host owns file application.

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
mpos-dev/reference/docs-app-model.md
mpos-dev/reference/docs-frameworks.md
mpos-dev/reference/docs-hardware-capabilities.md
mpos-dev/reference/docs-camera-apps.md
mpos-dev-web/reference/board_capabilities.json
mpos-dev/reference/docs-packaging.md
mpos-gen-app/SKILL.md
```

## Mandatory Gates

Before broad code writes:

- Read `analysis_result.json`.
- Read `dependency_handoff.json` when present.
- Read both API summary JSON files completely.
- Read and validate `visual_asset_plan`; if absent, treat the strategy as `lvgl_native` rather than inventing unplanned assets.
- List every planned `lv.*`, widget method, and `mpos.*` call.
- Check each planned API against the summaries or current source evidence.
- For zero-reference LVGL widgets, emit `WIDGET_ZERO_REFERENCE` warning and suggest simpler alternatives.

## App Rules

- Use flat layout: `internal_filesystem/apps/<fullname>/MANIFEST.JSON`, `icon_64x64.png`, `assets/main.py`.
- `publisher` is required. Do not wait for upload to fail with `MISSING_FIELD`.
- Do not modify App-external MPOS files.
- `buttonmatrix.set_map()` must use `"\n"` row separators and `""` terminator.
- Avoid unsupported CPython runtime modules.
- Prefer proven `lv.button` + flex/grid for simple controls.
- Generate capability-based, cross-device code. Do not write board IDs, GPIO maps, camera models, byte swaps, mirroring, rotation, or board imports into an App.
- Camera Apps use `CameraManager.has_camera()` and preferably `CameraActivity`. Keep a usable non-camera state when no camera is registered. The desktop `webcam` module is not a portable ESP32 API.
- Reject normal generated Apps that import `mpos.board.*`, instantiate direct GPIO/I2C/SPI/UART/I2S/ADC/NeoPixel hardware, or use board-specific drivers. Emit `DIRECT_HARDWARE_ACCESS_FORBIDDEN`; only a confirmed external-accessory handoff may allow a narrow exception.
- Generate runtime probes and fallbacks for audio, IMU, lights, battery, SD configuration, input modes, and network. Do not fabricate sensor values when hardware is unavailable.
- Every interactive App needs a visible LVGL focus path in addition to pointer interaction. Hardware sessions must stop or restore resources on pause/exit.
- Follow the analyzer's automatic `lvgl_native`, `raster_asset`, or `hybrid` strategy. Raster assets are App-local static artwork; never rasterize controls, dynamic text, focus state, or live values.
- For `generation_mode=web`, request `network_read`, use only the host-owned image search/fetch action, record provenance and redistribution rights, and pass only the registered downloaded artifact to the fixed decoder/converter. Do not accept user uploads or let the model fetch arbitrary URLs.
- Never execute Python, shell, SVG script, or plugin code emitted by a model. Convert a procedural `mpos-visual-asset-spec-v1` only through the fixed runner-whitelisted `scripts/build_visual_asset.py` pipeline; convert registered Web source artifacts only through the host-owned fixed image decoder/converter.
- Keep source PNG/JPEG/WebP previews under the session artifact root and runtime LVGL images under `assets/images/*.bin`. Use `M:apps/<fullname>/assets/images/<id>.bin` and provide a native LVGL fallback for every runtime load.
- Use `RGB565` for opaque color artwork, `RGB565A8` for transparent color artwork, and `A8` for recolorable masks. Do not embed large image byte arrays in Python source or add board-specific byte swaps.

Run or request `mpos-gen-app/scripts/check_app_hardware_policy.py` as a required gate. Use `--allow-direct-hardware` only for a confirmed external accessory and preserve all findings for review.

## Workflow

1. Validate protocol and input artifacts.
2. Build a generation plan and emit it as a status/artifact. Include the semantic visual plan, runtime byte budget, and reuse/stale decisions.
3. Request `file_write` permission if the host requires it.
4. For each procedural asset, emit a declarative spec and request the fixed builder with a host-supplied session root and per-file byte budget. For each Web asset, search, select, rights-check, fetch, normalize, and record the source through host-owned actions before fixed conversion. Validate the LVGL v9 header, dimensions, stride, size, source hash, and runtime hash before code generation.
5. Generate or repair only target App files. Give the code generator the actual validated runtime paths, dimensions, and formats; do not let it guess them.
6. Build a runtime bundle manifest and run `scripts/validate_visual_asset_bundle.py` against actual files, hashes, and `runtime_byte_budget`. Then run or request static gates: manifest, syntax, API usage, app-only changes, asset references, lint when available.
7. Run hardware policy gates: capability contract, forbidden direct access, runtime fallbacks, input modality, and lifecycle cleanup.
8. Classify missing search results, rejected downloads, unverified rights, and a missing fixed visual pipeline with their specific `VISUAL_ASSET_*` codes; use `TOOLCHAIN_MISSING` for unrelated tools such as `uv`, `ruff`, or `mpy-cross`.
9. Write `generation_result.json` and artifact manifest with `visual_assets[]` metadata.
10. Route to `mpos-test-app-web` on success or partial with usable files.

## Output

`generation_result.json` must include:

```json
{
  "schema_version": "mpos-gen-app-web-v1",
  "phase": "mpos-gen-app-web",
  "result": "success",
  "mode": "create",
  "app": {},
  "files_written": [],
  "api_usage": {"checked": true, "missing": []},
  "visual_assets": [],
  "validation": {"gates": []},
  "warnings": [],
  "structured_errors": [],
  "handoff": {"next_phase": "mpos-test-app-web"}
}
```
