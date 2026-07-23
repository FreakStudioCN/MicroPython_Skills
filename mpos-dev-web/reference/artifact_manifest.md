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
app_test_result
desktop_screenshot
web_preview_url
package_result
mpk
app_index_entry
deploy_result
publish_result
activity_log
session_state
```

Image artifacts for screenshots or upload guidance must be PNG, JPEG, or WebP. BMP may be stored as raw test evidence but is not publish-ready.
