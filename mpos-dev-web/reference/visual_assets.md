# Visual Asset Pipeline

Browser workflows may generate App-local raster assets when a requested static visual cannot be expressed well with a small number of standard LVGL widgets. The default decision is automatic; users do not need to choose between LVGL and images.

## Strategy Selection

`mpos-analyze-app-web` assigns one of these strategies:

- `lvgl_native`: text, controls, focusable elements, live data, responsive layout, and simple geometry.
- `raster_asset`: non-interactive static illustrations, textures, logos, backgrounds, and sprites.
- `hybrid`: raster artwork plus native LVGL controls and live state. This is the normal choice for visually rich interactive Apps.

The analyzer must not rasterize buttons, user-visible dynamic text, changing sensor values, focus states, or accessibility-critical controls. A simple rectangle, circle, line, card, or progress indicator stays native LVGL. A complex static visual may use a raster asset when recreating it would require many widgets or produce visibly poor output.

Explicit user instructions such as “no images,” “use raster sprites,” or “find the recognizable original artwork online” override the automatic choice when they remain compatible with MPOS safety, source-rights, and resource limits. User-uploaded image conversion is outside this workflow.

## Semantic Plan

Analysis emits a semantic plan; it does not choose board-specific byte order or execute drawing code:

```json
{
  "visual_asset_plan": {
    "schema_version": "mpos-visual-asset-plan-v1",
    "decision_mode": "automatic",
    "render_strategy": "hybrid",
    "assets": [
      {
        "id": "player_ship",
        "purpose": "game_sprite",
        "reason": "A detailed static sprite is clearer than many LVGL primitives.",
        "required": true,
        "dynamic": false,
        "interactive": false,
        "contains_text": false,
        "width": 32,
        "height": 24,
        "transparent": true,
        "generation_mode": "web",
        "search_query": "official player ship game artwork transparent background",
        "fallback": "Show a colored LVGL polygon or rectangle."
      }
    ],
    "lvgl_elements": ["score_label", "left_button", "right_button", "fire_button"]
  }
}
```

Asset IDs use `^[a-z][a-z0-9_]{0,63}$`. Every asset records a purpose, reason, dimensions, whether it is required, transparency, and an LVGL fallback. `contains_text=true`, `dynamic=true`, or `interactive=true` normally forces `lvgl_native` unless the raster is only a decorative layer behind a native element.

Choose `generation_mode` automatically:

- `procedural`: generic geometry, gradients, textures, and original simple illustrations that do not require an exact known appearance.
- `web`: a named character, logo, meme, product, public figure, or other recognizable subject where a procedural approximation would not satisfy the request. Include a specific `search_query`.
- `external`: newly generated artwork from an external image-generation provider. This remains optional and separately authorized.

Do not emit `uploaded`. If exact Web artwork cannot be used, apply the declared procedural or native LVGL fallback rather than asking for an upload.

## Safe Host Rendering

Never execute arbitrary Python, shell, SVG script, or plugin code supplied by a model. The model emits a declarative `mpos-visual-asset-spec-v1` object. A fixed runner-whitelisted script renders and converts it:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  <skills-root>/mpos-gen-app-web/scripts/build_visual_asset.py \
  --spec <artifact-root>/visual-assets/<id>.spec.json \
  --preview-output <artifact-root>/visual-assets/<id>.png \
  --runtime-output <project-root>/internal_filesystem/apps/<fullname>/assets/images/<id>.bin \
  --metadata-output <artifact-root>/visual-assets/<id>.build.json \
  --format auto
```

The bundled renderer supports constrained rectangles, circles, lines, polygons, and linear gradients with optional 2x/4x supersampling. It has no network access, imports, text rendering, arbitrary file reads, or model-provided executable code.

## Web Source Acquisition

When `generation_mode=web`, require `capabilities.web_image_search=true`, `capabilities.remote_image_fetch=true`, `capabilities.lvgl_image_convert=true`, and `capabilities.network_read=true`. Request `network_read` before search or download.

Use a host-owned image search provider. The model supplies only the query and selection criteria. Prefer an official/primary source page or a source with explicit reusable licensing. Select an image only when the source page, direct image URL, creator/attribution when applicable, license evidence, MIME type, size, and dimensions can be recorded. An “official” image is not automatically redistributable; do not put it into an MPK when redistribution rights are unknown.

The fixed fetcher and decoder must:

- Accept only HTTPS and configured image MIME types; never forward cookies, credentials, or arbitrary model-provided headers.
- Resolve DNS and reject loopback, private, link-local, multicast, and metadata-service addresses before the request and after every redirect.
- Limit redirects, download bytes, decoded dimensions/pixels, duration, and decompression ratio.
- Verify content from decoded bytes rather than URL suffix or `Content-Type` alone.
- Normalize orientation/color, resize with aspect-ratio policy, strip metadata, and write a clean PNG preview.
- Convert the normalized pixels to `RGB565`, `RGB565A8`, or `A8`, then validate the LVGL v9 header, dimensions, stride, byte length, and SHA-256.

Write a `visual_asset_source_record` before conversion. It contains `asset_id`, `search_query`, `source_page_url`, requested and resolved image URLs, source domain, license/license URL, attribution, retrieval time, MIME, source byte size, dimensions, and source SHA-256. The code model never receives authority to fetch a different URL.

An external image-generation provider is optional and separate from Web search. Use it only when `capabilities.external_image_generation=true` and the user grants `external_asset_generation`. Its bitmap output must still pass the same conversion, size, hash, and runtime validation gates.

## Runtime Formats and Paths

Keep source previews outside the App under the session artifact root. Put only runtime assets under:

```text
internal_filesystem/apps/<fullname>/assets/images/<id>.bin
```

Use:

- `RGB565` for opaque color images.
- `RGB565A8` for color images with transparency.
- `A8` for a recolorable single-color mask.

The converter emits the LVGL v9 binary header. Generated App code loads the file through the MPOS `M:` drive:

```python
image.set_src("M:apps/<fullname>/assets/images/<id>.bin")
```

Do not embed large image byte arrays in Python source. Do not write board IDs, display byte swaps, or board-specific color fixes into generated Apps.

PNG files can be used directly when current MPOS source and preview evidence prove the decoder and memory cost are acceptable. Prefer LVGL binary assets for predictable device decoding and record the selected format.

## Resource Rules

- Default output pixel budget per asset: 262,144 pixels.
- Default shape budget per procedural asset: 512.
- Default remote download limit per source: 8 MiB; the host may set a lower limit.
- Supported supersampling factors: 1, 2, and 4.
- Prefer small sprites, masks, tiles, and local decoration over multiple full-screen transparent images.
- `320x240 RGB565` is about 150 KiB; `RGB565A8` is about 225 KiB before MPK compression.
- Record each runtime byte size and the total App visual-asset size. A host may apply a stricter session or device budget.
- Use `DisplayMetrics` and native LVGL layout around images. Do not infer a board or assume every display is 320x240.

If a required asset exceeds budget, emit `VISUAL_ASSET_BUDGET_EXCEEDED`. For an optional decorative asset, use its LVGL fallback and continue with `partial` plus a warning.

## Artifacts and Staleness

For each asset, register:

- `visual_asset_spec`: declarative input JSON.
- `visual_asset_source_record`: Web search, provenance, license, retrieval, and source hash metadata.
- `visual_asset_source`: PNG/JPEG/WebP preview for browser review.
- `app_runtime_image`: App-local LVGL `.bin` file.
- `visual_asset_build_log`: format, dimensions, sizes, hashes, renderer version, and conversion result.

`generation_result.json` records the same metadata and the App runtime path. Hash the semantic plan, every spec, source record, and downloaded source. A changed prompt, search selection, resolved URL, source hash, asset spec, dimensions, transparency, renderer version, or converter version makes the runtime image, screenshots, MPK, and publish results stale. Unchanged hashes are idempotently reusable across resume and retry.

## Required Validation

Generation validates the spec, safe paths, pixel/shape budgets, LVGL v9 header, dimensions, stride, byte length, and hashes. Testing launches the App and captures a screenshot that proves the image rendered. It separately tests the fallback for required asset-load failures when feasible.

Classify failures as follows:

- Invalid model asset plan or spec: `VISUAL_ASSET_SPEC_INVALID`, owner `app`, retryable.
- Missing fixed renderer/converter: `VISUAL_ASSET_TOOLCHAIN_MISSING`, owner `toolchain`, retryable.
- Renderer or conversion failure: `VISUAL_ASSET_BUILD_FAILED`, owner `skill`, retryable.
- Resource budget exceeded: `VISUAL_ASSET_BUDGET_EXCEEDED`, owner `app`, retryable.
- App cannot load a valid packaged asset: `VISUAL_ASSET_LOAD_FAILED`, owner `app`, retryable.
- Web search has no usable result: `VISUAL_ASSET_SEARCH_FAILED`, owner `external`, retryable.
- Remote URL, redirect, response, or decoded image validation fails: `VISUAL_ASSET_FETCH_FAILED`, owner `external`, retryable.
- Packaging rights cannot be verified: `VISUAL_ASSET_RIGHTS_UNVERIFIED`, owner `external`, not retryable without another source.
