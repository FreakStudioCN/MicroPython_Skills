---
name: mpos-publish-app-web
description: Structured browser release-readiness phase for MicroPythonOS Apps. Use when a backend runner needs to combine package_result.json, app_test_result.json, deploy_result.json, screenshots, upystore read-only checks, metadata readiness, publish_result.json, and manual upload guidance. This does not replace classic mpos-publish-app.
---

# MicroPythonOS Browser Publish Preparation

`mpos-publish-app-web` prepares a release-readiness result for browser workflows. It never logs in or uploads.

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
mpos-dev/reference/docs-packaging.md
mpos-publish-app/SKILL.md
```

## Required Inputs

Read together:

```text
package_result.json
app_test_result.json
deploy_result.json
artifact_manifest.json
```

Missing or failed required inputs block publishing. `desktop-preview` or `web-preview` deploy records are acceptable only when the session explicitly says physical hardware is unavailable or not required.

## Store Metadata

Check:

- `short_description`
- `long_description`
- `release_notes`
- `hardware_tags`
- screenshots in PNG, JPEG, or WebP
- MPK path and filename `<fullname>_rN.mpk`
- manifest `publisher`

Use upystore public endpoints only for read-only version comparison when `network_read=true`. If network is unavailable, warn and continue with `version_status=unknown_unverified`.

## Batch Upload Manifest

For batch sessions or `final_artifacts_only=true`, create a browser-visible upload bundle:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-publish-app/scripts/prepare_upload_manifest.py \
  --repo <repo-root> \
  --app-prefix <fullname-prefix> \
  --mpk-dir <artifact-root>/mpk \
  --screenshot-dir <artifact-root>/screenshots \
  --output <artifact-root>/upystore_upload_manifest.json \
  --artifact-manifest-output <artifact-root>/artifact_manifest.json
```

Expose the upload manifest in `artifact_manifest.json` with role `upystore_upload_manifest`. Do not set `publish_ready=true` if any App entry is missing `publisher`, MPK, icon, or PNG/JPEG/WebP screenshot.

## Output

Write `publish_result.json` with release readiness, blockers, warnings, structured errors, MPK metadata, app metadata, screenshot readiness, upystore comparison, manual upload guidance, and `handoff.next_phase=null`.

Never request credentials, never upload, and never modify package artifacts here.
