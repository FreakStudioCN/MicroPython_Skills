---
name: mpos-package-app-web
description: Structured browser MPK packaging phase for MicroPythonOS Apps. Use when a backend runner needs manifest validation, publisher checks, stable fullname_rN.mpk output, package_result.json, app_index_entry.json, artifact manifest entries, and release-number errors. This does not replace classic mpos-package-app.
---

# MicroPythonOS Browser App Packaging

`mpos-package-app-web` validates and packages a generated App for the browser workflow. It does not repair App code or upload releases.

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
mpos-dev/reference/docs-packaging.md
mpos-package-app/SKILL.md
```

## Required Checks

- `MANIFEST.JSON` exists and includes non-empty `fullname`, `name`, `publisher`, and `version`.
- Activity entrypoints exist and class names are present.
- `icon_64x64.png` exists or warning/error policy is explicit.
- Every `generation_result.visual_assets[]` runtime path exists under `assets/images/`, matches its recorded SHA-256, and is included in the package. Source previews and host drawing specs remain session artifacts unless explicitly required at runtime.
- Every Web-sourced runtime image has a matching source record and verified redistribution/attribution decision. Include required attribution in the App/package; do not package unknown-rights artwork.
- MPK filename uses `<fullname>_rN.mpk` such as `com.example.app_r1.mpk`.
- MPK has a single top-level directory and valid local headers.

## Workflow

1. Read `generation_result.json` and `app_test_result.json` when available.
2. Validate App layout, manifest, runtime image references, rights decisions, and asset hashes. Run `mpos-gen-app-web/scripts/validate_visual_asset_bundle.py` against actual files and block when actual total runtime bytes exceed the plan budget.
3. Request `script_run` and `file_write` permissions if required.
4. Run classic package scripts or host-equivalent commands.
5. Write `package_result.json`, `app_index_entry.json`, and artifact manifest entries.
6. Route to `mpos-deploy-app-web`.

## Final Artifact Mode

When `final_artifacts_only=true`, per-App `package_result.json` may remain internal, but fresh MPK files are mandatory final artifacts. Add every MPK to `artifact_manifest.json` with role `mpk`, and mark downstream artifacts stale if App source changed after packaging.

## Output

`package_result.json` includes `app`, `package.revision`, `package.mpk_path`, `package.filename_policy`, checks, warnings, structured errors, and handoff.

If `publisher` is missing, emit `MANIFEST_MISSING_FIELD` or `MISSING_FIELD` and route back to `mpos-gen-app-web` repair.
