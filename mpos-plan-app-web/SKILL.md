---
name: mpos-plan-app-web
description: Browser workflow orchestrator for MicroPythonOS App generation sessions. Use when a backend runner needs to create, resume, retry, cancel, or route an mpos-ai-app/v1 session across mpos-*-web phases with checkpoints, artifact manifests, permissions, and structured errors. This does not replace classic mpos-plan-app.
---

# MicroPythonOS Browser Session Orchestrator

`mpos-plan-app-web` owns session creation, resume, retry, cancel, and phase routing for browser-driven MicroPythonOS App generation. It does not generate App code itself.

## Shared Requirements

Before acting, read `mpos-dev-web/SKILL.md`, then read these references as needed:

```text
mpos-dev-web/reference/protocol.md
mpos-dev-web/reference/state_machine.md
mpos-dev-web/reference/error_codes.md
mpos-dev-web/reference/artifact_manifest.md
mpos-dev-web/reference/permission_prompts.md
mpos-dev-web/reference/capabilities.md
mpos-dev-web/reference/board_capabilities.json
mpos-dev-web/reference/visual_assets.md
```

Also read `mpos-dev/reference/mpos_api_summary.json` and `mpos-dev/reference/lvgl_api_summary.json` completely. Do not skip them because this phase appears simple.

Never modify classic `mpos-*` skills, MicroPythonOS OS/framework/build/lvgl files, or App directories outside the current workflow target.

## Inputs

Accept `start_phase`, `resume`, `retry`, and `cancel` messages. Required payload fields:

- `prompt` or `source_phase_complete_path` for a new or resumed workflow.
- `runtime_context.session_root`, `project_root`, `artifact_root`, `repo_root`, and `skills_root`.
- `capabilities` object from the host.
- Persisted `required_capabilities`, `required_accessories`, `runtime_fallbacks`, and `physical_validation_required` when analysis has completed. These are App feature requirements, not a selected board.
- Persisted `visual_asset_plan`, runtime-byte budget, its hash, runtime image metadata, and stale state after analysis has completed. Rendering strategy is normally selected automatically by analysis, not by a required frontend question.

If required fields are missing, emit `MISSING_FIELD` and `phase_complete(result=blocked)`.

## Workflow

1. Validate `protocol_version == "mpos-ai-app/v1"`.
2. Create or read `session_state.json` and `activity_log.jsonl`.
3. Normalize requested App identity if already known: `fullname`, `publisher`, `version`, `name`.
4. Select the next phase from the state machine. Never insert a board-selection phase; board metadata is consulted only after a device connection or for test diagnostics:
   - New natural-language request: `mpos-analyze-app-web`.
   - Dependency handoff required: `mpos-prepare-deps-web`.
   - Confirmed analysis: `mpos-gen-app-web`.
   - Generated code: `mpos-test-app-web`.
   - Tested or test partial: `mpos-package-app-web`.
   - Packaged: `mpos-deploy-app-web`.
   - Deploy/preview record exists: `mpos-publish-app-web`.
5. Preserve artifacts and errors from prior attempts.
6. Reuse unchanged visual assets by plan/spec/source hash. When a revision changes visual intent, selected Web source, source bytes, dimensions, transparency, renderer, or converter, mark runtime images, screenshots, MPKs, deploy results, and publish results stale.
7. Emit `phase_complete` with `next_phase` and checkpoint.

## Batch / Final Artifact Mode

If the browser session requests multiple Apps, a project library, or `final_artifacts_only=true`, the session may omit per-App intermediate display artifacts, but it must still route through final evidence creation:

- `mpos-test-app-web` must produce or reference PNG/JPEG/WebP screenshots for every App.
- `mpos-package-app-web` must produce fresh `<fullname>_rN.mpk` files.
- `mpos-publish-app-web` must produce an `upystore_upload_manifest` or per-App `publish_result` artifacts.
- `artifact_manifest.json` must expose screenshots, MPKs, and upload guidance explicitly.

Do not emit `completed` or `publish_ready=true` while any App lacks a screenshot or upload metadata. Emit `partial` with structured missing-artifact errors instead.

## Output

Write:

```text
sessions/<session_id>/session_state.json
sessions/<session_id>/activity_log.jsonl
sessions/<session_id>/artifact_manifest.json
sessions/<session_id>/phase_complete.mpos_plan_app_web.json
```

`phase_complete.payload.result` is normally `success` when routing is determined, `blocked` when input or permission is missing, or `cancelled` on user cancellation.
