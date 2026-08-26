# Artifact Manifest

The browser frontend must display artifacts from a manifest, not guessed paths.

Use this shape:

```json
{
  "schema_version": "mpos-artifact-manifest-v1",
  "session_id": "sess_20260723_001",
  "app_fullname": "com.example.calculator",
  "artifacts": [
    {
      "id": "art_manifest",
      "phase": "mpos-gen-app-web",
      "kind": "source",
      "role": "app_manifest",
      "path": "project/internal_filesystem/apps/com.example.calculator/MANIFEST.JSON",
      "mime": "application/json",
      "size": 512,
      "sha256": "...",
      "display_name": "MANIFEST.JSON"
    }
  ]
}
```

Required fields per artifact: `id`, `phase`, `kind`, `role`, `path`, and `mime`.

Recommended roles:

```text
analysis_result
dependency_handoff
generation_result
app_manifest
app_source
app_icon
visual_asset_spec
visual_asset_source_record
visual_asset_source
app_runtime_image
visual_asset_build_log
visual_asset_bundle_validation
app_test_result
desktop_screenshot
web_preview_url
package_result
mpk
app_index_entry
deploy_result
publish_result
store_screenshot
upystore_upload_manifest
manual_upload_guidance
publish_bundle
activity_log
session_state
```

Browser-visible source artwork and screenshots must use PNG, JPEG, or WebP. Every Web-fetched image also has a JSON `visual_asset_source_record` containing its search query, source page, resolved image URL, license/attribution evidence, retrieval timestamp, media type, byte length, and SHA-256. LVGL `.bin` files use role `app_runtime_image` and MIME `application/octet-stream`; they are runtime assets, not browser previews. BMP may be stored as raw test evidence but is not publish-ready.

For batch/final-artifact sessions, the browser must not infer readiness from source files or MPKs alone. The manifest must include at least one `store_screenshot` artifact per App and either per-App `publish_result` artifacts or one batch `upystore_upload_manifest` artifact.
