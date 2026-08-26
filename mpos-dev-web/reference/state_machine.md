# Browser Workflow State Machine

Canonical phase order:

```text
mpos-plan-app-web
-> mpos-analyze-app-web
-> mpos-prepare-deps-web
-> mpos-gen-app-web
-> mpos-test-app-web
-> mpos-package-app-web
-> mpos-deploy-app-web
-> mpos-publish-app-web
```

`mpos-prepare-deps-web` may be skipped when analysis proves there are no App-local dependencies.

## Checkpoints

Use these checkpoint IDs:

```text
session_created
requirements_analyzed
dependencies_prepared
code_generated
desktop_test_done
web_preview_done
package_done
deploy_done
publish_check_done
completed
failed
blocked
cancelled
```

Each checkpoint records `protocol_version`, `session_id`, `phase`, `checkpoint_id`, `attempt`, `idempotency_key`, `input_hash`, `repo_commit`, `skills_commit`, `api_summary_generated_at`, `visual_asset_plan_hash`, runtime-byte budget/actual bytes, `result`, `artifacts`, `warnings`, `structured_errors`, and `next_phase`.

## Session State

`session_state.json` must be append-friendly and resume-safe:

```json
{
  "schema_version": "mpos-ai-app-session-v1",
  "session_id": "sess_20260723_001",
  "protocol_version": "mpos-ai-app/v1",
  "current_phase": "mpos-gen-app-web",
  "checkpoint_id": "requirements_analyzed",
  "attempts": {"mpos-gen-app-web": 1},
  "completed_phases": [],
  "last_error": null,
  "next_phase": "mpos-gen-app-web"
}
```

Write `activity_log.jsonl` for all state changes. Each line is one JSON object.

## Idempotency

Before writing files, compare `session_id`, `phase`, `idempotency_key`, `input_hash`, and target artifact paths. If the same key already completed with success and inputs match, return the existing phase result instead of writing again.

Persist `visual_asset_plan` after analysis. Reuse an existing runtime image only when its plan/spec hash, source URL/content hash, renderer version, converter version, and output hash still match. A changed visual plan or changed Web source marks the runtime image, screenshots, MPK, deploy result, and publish result stale before generation resumes.

## Timeout

Every script, device, Web preview, or build operation must have a timeout from host input or a conservative default. On timeout, emit `SCRIPT_TIMEOUT`, `DEVICE_TIMEOUT`, or `WEB_PREVIEW_TIMEOUT` with `retryable=true` unless cancellation was requested.
