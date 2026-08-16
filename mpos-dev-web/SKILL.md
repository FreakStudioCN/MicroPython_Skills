---
name: mpos-dev-web
description: Shared browser-orchestrated MicroPythonOS App workflow protocol and constraints. Use when Codex or a runner needs session/checkpoint JSON, structured errors, artifact manifests, permission prompts, capability negotiation, board support facts, Web preview limits, or common rules for any mpos-*-web skill. This does not replace classic mpos-dev.
---

# MicroPythonOS Web Workflow Foundation

`mpos-dev-web` is the shared foundation for the browser version of the MicroPythonOS App workflow. It is a protocol layer for backend runners and browser hosts. It must not replace or weaken the classic local Claude Code skills.

Classic local skills remain available and compatible:

```text
mpos-dev
mpos-plan-app
mpos-analyze-app
mpos-prepare-deps
mpos-gen-app
mpos-test-app
mpos-package-app
mpos-deploy-app
mpos-publish-app
```

Browser-orchestrated skills use the `-web` suffix:

```text
mpos-dev-web
mpos-plan-app-web
mpos-analyze-app-web
mpos-prepare-deps-web
mpos-gen-app-web
mpos-test-app-web
mpos-package-app-web
mpos-deploy-app-web
mpos-publish-app-web
```

Do not create `mpos-debug-app-web`; `mpos-debug-app` is not part of the current MPOS App workflow.

## Required References

Read the relevant reference before acting:

| Need | Read |
|---|---|
| Protocol envelope, start/resume/retry/cancel, phase events | `reference/protocol.md` |
| Checkpoints, stage transitions, idempotency | `reference/state_machine.md` |
| Structured error schema and codes | `reference/error_codes.md` |
| File/artifact manifest schema | `reference/artifact_manifest.md` |
| Browser permission request schema | `reference/permission_prompts.md` |
| Capability negotiation fields | `reference/capabilities.md` |
| Cross-device policy and known board facts | `reference/board_capabilities.md` and `reference/board_capabilities.json` |
| Web preview scope and known limits | `reference/web_preview_limits.md` |

For App/API rules, also load classic shared references from `mpos-dev`:

```text
mpos-dev/reference/mpos_api_summary.json
mpos-dev/reference/lvgl_api_summary.json
mpos-dev/reference/docs-app-model.md
mpos-dev/reference/docs-frameworks.md
mpos-dev/reference/docs-hardware-capabilities.md
mpos-dev/reference/docs-camera-apps.md
mpos-dev/reference/docs-packaging.md
mpos-dev/reference/docs-deploy-targets.md
mpos-dev/reference/docs-os-development.md
mpos-dev/reference/docs-web-port.md
```

The API summary JSON files are mandatory for every mpos-*-web phase. Read them completely; do not skip them because a request looks simple.

## Hard Rules

- Keep classic `mpos-*` skills compatible; do not edit them while implementing a `-web` workflow unless the user explicitly asks.
- Treat the browser workflow as a long-running protocol, not a chat transcript.
- Emit structured JSON artifacts; do not rely on final natural-language text as the source of truth.
- Preserve `session_id`, `checkpoint_id`, `idempotency_key`, `protocol_version`, `capabilities`, `permission_prompts`, `artifacts`, `warnings`, and `structured_errors`.
- Only modify generated App files and workflow artifacts. Do not modify MicroPythonOS OS/framework/build/lvgl code to fix App generation.
- Confirm whether MicroPythonOS is installed on a device before any physical deploy or MPK install path.
- Do not require a frontend board selector. Generate against MPOS capabilities, probe them at runtime, and treat `board_capabilities.json` as advisory metadata only.
- For camera Apps, use `CameraManager`/`CameraActivity`; never generate board drivers, GPIO mappings, sensor-specific orientation fixes, or direct `webcam` use for ESP32.
- Apply the same boundary to every onboard peripheral: no `mpos.board.*`, direct GPIO/bus constructors, or board-specific drivers in normal generated Apps. A non-portable contract returns `MPOS_CAPABILITY_API_MISSING`.
- Interactive Apps must remain operable with pointer and LVGL focus navigation; do not assume a touchscreen.
- Always expose the real hardware path. Desktop preview and Web preview are not replacements for physical validation.
- Web preview is optional and may fail due to Web port, browser, or toolchain issues. Classify those failures as external/tooling unless logs prove an App bug.
- If a browser workflow touches `internal_filesystem/builtin/`, OS/framework/build files, board support, filesystem images, or firmware artifacts, treat it as an OS-level operation: require explicit permission, rebuild `.mpy`/freezefs/firmware, flash the full image, record USB/BOOT state, and require physical-device evidence before claiming hardware success.

## Output Discipline

Every `mpos-*-web` phase must write a phase result JSON and an artifact manifest update. Phase result files live under the browser session/work directory, not in the main MicroPythonOS checkout unless the runner explicitly maps that directory.

Recommended layout:

```text
sessions/<session_id>/
  session_state.json
  activity_log.jsonl
  artifacts/
  phase_complete.<phase>.json
  project/
```

When adapting to the existing classic local workflow, map classic artifacts into the same protocol fields instead of changing their classic schemas.
