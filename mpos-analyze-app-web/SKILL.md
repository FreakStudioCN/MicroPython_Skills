---
name: mpos-analyze-app-web
description: Structured browser requirements analysis for MicroPythonOS Apps. Use when a backend runner receives a natural-language App request and needs analysis_result.json, manifest draft, App identity, dependency/test/deploy plans, missing-field errors, and next_phase routing for mpos-ai-app/v1. This does not replace classic mpos-analyze-app.
---

# MicroPythonOS Browser App Analysis

`mpos-analyze-app-web` converts a browser user's natural-language request into structured App requirements. It does not write App source files.

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
mpos-dev/reference/docs-packaging.md
mpos-dev-web/reference/board_capabilities.md
mpos-dev-web/reference/web_preview_limits.md
```

## Required Input

`payload.input.prompt` is required. Prefer explicit `fullname`, `name`, `publisher`, and `version`. If missing, derive safe defaults and record them. If `fullname` cannot be derived, emit `MISSING_FIELD`.

Do not ask for a board as a generation prerequisite. Extract abstract `required_capabilities` and `runtime_fallbacks`. For a camera request, record `camera`, keep non-camera behavior usable, and require physical validation without binding the App to a camera model.

Automatically classify requested visuals as `lvgl_native`, `raster_asset`, or `hybrid`. Users do not need to select a rendering path. Keep text, controls, focus state, live data, and responsive layout native; propose App-local raster assets only for complex static artwork. For a named recognizable subject whose original appearance matters, select `generation_mode=web` and emit a specific `search_query` when Web search/fetch and network-read capabilities are available. Do not select or request uploaded artwork. Explicit user preferences may override the automatic choice.

Resolve every hardware requirement against `board_capabilities.json`. A `portable_api=false` contract produces `MPOS_CAPABILITY_API_MISSING` and blocks automatic hardware implementation. Only explicit external modules become `required_accessories`; onboard hardware never becomes a dependency-search request.

## Workflow

1. Validate request and capabilities.
2. Derive App identity:
   - `fullname`: reverse-DNS package name.
   - `publisher`: default to the organization prefix, for example `com.example`.
   - `version`: default `1.0.0` for new Apps.
3. Produce manifest draft using the flat MPOS layout.
4. Identify LVGL widgets, MPOS APIs, system managers, images, networking, storage, and abstract hardware capabilities. Resolve built-in camera support through `CameraManager`/`CameraActivity`, not an App-local driver.
5. Emit a semantic `visual_asset_plan`: explain every automatic raster decision, dimensions, transparency, generation mode, Web search query when applicable, required/optional state, and native LVGL fallback. Do not emit executable drawing code, source URLs, request headers, or board-specific image formats. Run or request `scripts/validate_visual_asset_plan.py` with `--allow-web` only when the host has Web search/fetch plus `network_read`; invalid plans emit `VISUAL_ASSET_SPEC_INVALID` and remain in analysis repair.
6. Decide whether `mpos-prepare-deps-web` is required. Host-only visual rendering is not an App dependency and does not route through dependency preparation.
7. Produce test, package, deploy, and publish plans, including runtime image load and screenshot evidence when assets are planned.
8. Warn when physical hardware validation is needed.
9. Emit `analysis_result.json` and update artifact manifest.

## Output

Write `analysis_result.json` with:

```json
{
  "schema_version": "mpos-analyze-app-web-v1",
  "phase": "mpos-analyze-app-web",
  "result": "success",
  "app": {},
  "manifest_draft": {},
  "requirements": {
    "required_capabilities": [],
    "required_accessories": [],
    "runtime_fallbacks": {},
    "physical_validation_required": false
  },
  "visual_asset_plan": {
    "schema_version": "mpos-visual-asset-plan-v1",
    "decision_mode": "automatic",
    "render_strategy": "lvgl_native",
    "assets": [],
    "lvgl_elements": []
  },
  "api_plan": {},
  "dependency_plan": {},
  "test_plan": {},
  "deploy_plan": {},
  "warnings": [],
  "structured_errors": [],
  "handoff": {"next_phase": "mpos-gen-app-web"}
}
```

If dependencies are needed, set `handoff.next_phase` to `mpos-prepare-deps-web`.
