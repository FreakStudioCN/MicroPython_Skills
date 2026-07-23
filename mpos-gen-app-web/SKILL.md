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
```

Also read `mpos-dev/reference/mpos_api_summary.json` and `mpos-dev/reference/lvgl_api_summary.json` completely. Do not skip them because this phase appears simple.

Never modify classic `mpos-*` skills, MicroPythonOS OS/framework/build/lvgl files, or App directories outside the current workflow target.

## Read First

Also read:

```text
mpos-dev/reference/docs-app-model.md
mpos-dev/reference/docs-frameworks.md
mpos-dev/reference/docs-packaging.md
mpos-gen-app/SKILL.md
```

## Mandatory Gates

Before broad code writes:

- Read `analysis_result.json`.
- Read `dependency_handoff.json` when present.
- Read both API summary JSON files completely.
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

## Workflow

1. Validate protocol and input artifacts.
2. Build a generation plan and emit it as a status/artifact.
3. Request `file_write` permission if the host requires it.
4. Generate or repair only target App files.
5. Run or request static gates: manifest, syntax, API usage, app-only changes, lint when available.
6. Classify tool gaps such as missing `uv`, `ruff`, or `mpy-cross` as `TOOLCHAIN_MISSING`, not App failure.
7. Write `generation_result.json` and artifact manifest.
8. Route to `mpos-test-app-web` on success or partial with usable files.

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
  "validation": {"gates": []},
  "warnings": [],
  "structured_errors": [],
  "handoff": {"next_phase": "mpos-test-app-web"}
}
```
