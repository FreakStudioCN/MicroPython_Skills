---
name: mpos-prepare-deps-web
description: Structured browser dependency preparation for MicroPythonOS App workflows. Use when analysis_result.json requires App-local pure Python or MPY dependencies, adapters, vendored files, or dependency_handoff.json before mpos-gen-app-web. This does not replace classic mpos-prepare-deps.
---

# MicroPythonOS Browser Dependency Preparation

`mpos-prepare-deps-web` prepares App-local dependencies for a browser workflow. It does not modify MicroPythonOS OS libraries or install host packages without permission.

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
```

## Boundaries

- Only prepare dependencies that live inside the generated App directory, usually under `assets/`.
- Do not modify `internal_filesystem/lib`, `mpos`, `lvgl_micropython`, or MicroPythonOS build files.
- Do not install host dependencies unless the host sends a `dependency_install` permission grant.
- Do not write API keys or tokens.

## Workflow

1. Read `analysis_result.json`.
2. Classify dependencies as builtin MPOS, pure Python App-local, MPY-compatible, external service, or unsupported.
3. For sync libraries, require an adapter plan so LVGL events and MPOS tasks are not blocked.
4. Emit file operations or artifacts for dependency files.
5. Record unresolved dependencies as structured errors or warnings.
6. Emit `dependency_handoff.json` and route to `mpos-gen-app-web`.

## Output

Write:

```text
sessions/<session_id>/artifacts/dependency_handoff.json
sessions/<session_id>/phase_complete.mpos_prepare_deps_web.json
```

`dependency_handoff.json` includes `imports`, `runtime_files`, `adapter_requirements`, `sync_needs_adapter`, `async_compatible`, `warnings`, and `structured_errors`.
