# Protocol Fields

Use this reference when creating or validating `start_phase`, `phase_complete`, checkpoints, file manifests, and structured errors.

## Envelope Fields

| Field | Meaning | Required |
|---|---|---|
| `protocol_version` | Protocol schema version. Use `"1.0"` until a breaking change is introduced. | yes |
| `msg_id` | Unique message id for this protocol event. | yes |
| `session_id` | Stable workflow session id. Retries and resumes must keep the same session id. | yes |
| `phase` | Plugin phase name. Use `upy-generate-plugin` in envelopes. | yes |
| `timestamp` | UTC timestamp for event emission. | yes |
| `type` | Event type such as `start_phase`, `status_update`, `file_operation`, `approval_request`, `phase_complete`. | yes |
| `idempotency_key` | Stable key that makes repeated calls safe. Include phase, session id, step, and version. | yes |
| `retry_of` | Previous `msg_id` when this event retries an earlier event; otherwise `null`. | no |

## Start Payload Fields

| Field | Meaning |
|---|---|
| `mode` | `full` for new generation, `fix` for minimal repair. |
| `source_phase` | Upstream phase, normally `upy-scaffold-plugin`. |
| `source_phase_complete_path` | Artifact-relative path to upstream phase_complete. |
| `manifest_content` | Optional direct manifest object. Prefer this over file lookup when provided. |
| `next_phase_preference` | User/host preference: `deploy`, `simulate`, or `stop_after_generate`. |
| `runtime_context.session_root` | Artifact-relative session state directory. |
| `runtime_context.project_root` | Artifact-relative project root containing `firmware/`. |
| `runtime_context.file_operation_root` | Root under which relative file writes are applied. Usually same as `project_root`. |
| `runtime_context.resource_root` | Plugin resource root, normally `upy-generate-plugin`. |
| `capabilities` | Host-supported operations: `file_operation`, `script_run`, `approval_request`, `git_operation`, `checkpoint_resume`, `cancellation`. |
| `timeouts` | Step-level timeout budget in milliseconds. |
| `error_context` | Required in `fix` mode. Contains traceback, deploy logs, user feedback, triage JSON, previous attempts. |

## Session Boundary

Use these terms consistently when a user reopens chats, passes one session as the target, and references another session only for logs.

| Term | Meaning |
|---|---|
| `workflow_session_root` | The active session that owns generated project files, checkpoints, phase_complete files, and the artifact chain. |
| `diagnostic_log_session` | A secondary session used only as evidence, such as deploy logs, REPL output, or prior failure analysis. |

Rules:

- Treat `runtime_context.session_root`, `runtime_context.project_root`, and explicit `source_phase_complete_path` as the workflow session source of truth.
- Treat a user-supplied path in the generate command as `workflow_session_root` unless the user explicitly says it is only diagnostic evidence.
- Do not infer the active workflow session from the newest `sessions/*` directory, a reopened chat, or stale phase logs.
- Do not write generated code, `generate_plan.json`, `phase_complete.upy_generate_plugin.json`, or checkpoint files into a `diagnostic_log_session`.
- If deploy/user feedback references another session, include that path only in `artifacts`, `warnings`, or `error_context`.
- Final `phase_complete.payload.runtime_context.session_root` and `project_root` must point to the workflow session that owns the current generated project.

## Deploy Feedback And Fix Boundary

Deploy collects evidence; generate fixes code semantics.

- `upy-deploy-plugin` must not be treated as a broad semantic preflight engine for Timer, task assembly, or peripheral API correctness.
- Deploy returns `error_context` evidence to `upy-autofix-plugin` or `upy-generate-plugin(mode=fix)`.
- Fix mode must consume the full `error_context`, including deploy result path, serial excerpt, device log excerpt/report, device test result path, mip install result, forbidden upload list, user observation, and previous generate commit when available.
- Fix mode should make the smallest code change, rerun quality gates, and produce a new commit when success is claimed.
- A deploy `PASS` or `PASS_WITH_WARNINGS` means deployment-observation success. It does not authorize ad-hoc source edits inside deploy.

## Checkpoint Names

Use these stable checkpoint names:

```text
started
behavior_confirmed
dependency_resolved
cloud_service_confirmed
generate_plan_validated
drivers_written
middleware_written
driver_api_analyzed
factories_generated
tasks_generated
conf_updated
conf_contract_validated
main_updated
tests_generated
py_compile_passed
flake8_passed
pylint_passed
pc_unittest_passed
mpy_imports_passed
dead_config_passed
skeleton_compliance_passed
final_review_passed
git_committed
optional_outputs_offered
phase_completed
```

## File Manifest Entry Fields

| Field | Meaning |
|---|---|
| `path` | POSIX-style project-relative path. Never include a Windows drive. |
| `status` | `created`, `updated`, `unchanged`, `skipped`, or `error`. |
| `encoding` | Normally `utf-8`. |
| `bytes` | UTF-8 byte length after write. |
| `sha256` | Final content hash. |
| `sha256_before` | Previous hash when file existed. |
| `sha256_after` | Desired content hash. |
| `overwrite` | True only when an existing different file was intentionally overwritten. |
| `role` | `plan`, `driver`, `middleware`, `driver_adapter`, `mock`, `business_task`, `entrypoint`, `configuration`, `pc_test`, `device_test`, `manifest`, or `artifact`. |
| `reason` | Optional human-readable reason for skipped/error entries. |

## Phase Complete Payload Fields

| Field | Meaning |
|---|---|
| `phase` | Domain phase. Use `generate`. |
| `domain_phase` | Same domain phase label. Use `generate`. |
| `result` | `success`, `partial`, or `failed`. |
| `summary` | Short human-readable outcome. |
| `next_phase` | `upy-deploy-plugin`, `upy-simulate-plugin`, or `null`. Never put diagram/wiring here. |
| `optional_next_phases` | Extra requested phases such as `upy-diagram-plugin` and `upy-wiring-plugin`. |
| `checkpoint` | Last completed checkpoint. |
| `runtime_context` | Final artifact-relative runtime paths. |
| `source` | Upstream phase and manifest source details. |
| `approval` | User behavior/next phase/optional output decision. |
| `permissions` | Approved file/script/git operations with idempotency keys. |
| `file_manifest` | Final file manifest object. |
| `lint` | Summary for flake8 and pylint. |
| `tests` | PC unittest and device test generation/check summaries. |
| `checks` | Full JSON outputs from quality scripts. |
| `generate` | Generate-specific summary: mode, deploy plan, simulation hints, git, attempts. |
| `manifest_content` | Full updated project manifest object. On success it must have `phase="generate"` and include generate-specific sections, not only a thin summary. |
| `review_findings` | Structured final review findings. On success `blocking` must be an empty list. |
| `structured_errors` | Machine-readable errors. Empty on success. |

## Success Consistency Rules

For `payload.result="success"`:

- `payload.structured_errors` must be empty.
- Strong gates in `lint`, `tests`, and `checks` must be acceptable under `references/validation_gates.md`.
- `payload.source.source_phase_complete_path` or `payload.source.upstream_phase_complete_path` should point to the scaffold/select-hw/flash phase_complete used as the hardware baseline. When present, `check_phase_complete_consistency.py` compares upstream `mcu`, `board`, `devices`, and `pinout` against final `manifest_content`.
- `checks.generate_plan` and `checks.conf_contract` must pass; `file_manifest.files` should include `generate_plan.json` with role `plan`.
- Final generate plan validation must use `check_generate_plan.py --require-plan --check-files`; planned tasks, drivers, middleware, and tests must exist before success.
- Pylint return code `12` is acceptable only when represented as `ok=true` under the default `fail_on_fatal_error_usage` policy; fatal/error/usage bits are never acceptable. Skipped pylint is never acceptable on success.
- CPython fallback imports such as `asyncio` after `uasyncio` are warning-only only when detected by `check_mpy_imports.py` as `MPY_IMPORT_CPYTHON_FALLBACK`.
- `payload.manifest_content.phase` and `project/project-manifest.json.phase` must both be `generate`.
- `payload.manifest_content` must preserve upstream `requirements`, non-empty `devices`, `mcu`, `pinout`, and scaffold context; `generate` must not replace the full manifest.
- Generate must not introduce new hardware, replace devices, change MCU/board, or modify wiring/pinout. Those changes require a new analyze/select-hw/scaffold pass, or a scaffold incremental phase_complete that already contains the updated hardware facts and records `incremental=true` plus `generate_scope=new_devices_only`.
- If the project uses cloud services, `payload.manifest_content.generate.cloud_integrations` must record provider id, category, services, official setup links, credential status, user actions, and deploy readiness. Real secrets must not appear in generated code or protocol artifacts.
- `payload.file_manifest.files` must include the updated `project-manifest.json` with role `manifest`.
- `payload.file_manifest.files` must include `generate_plan.json` with role `plan`.
- `payload.file_manifest.files` must include `session_state.upy_generate_plugin.json` with role `artifact`.
- `payload.checks.session_state_checkpoint.ok` must be `true`, and `payload.artifacts[]` must include a `session_state` entry.
- Completed `payload.checks.session_state_checkpoint.state` must include non-empty `artifacts` and `last_ok_artifact` so resume can identify the last trusted output.
- `payload.optional_next_phases` must offer `upy-diagram-plugin` and `upy-wiring-plugin` as optional post-generate artifacts. `upy-simulate-plugin` belongs in `next_phase` only when the user wants simulation before deploy.
- `payload.generate.git.commit` and disk `session_state.git_commit` must record final project HEAD after all strong gates pass, and `payload.permissions[]` must include an approved `git_commit` or `git_operation` decision. Commit denial or dry-run is `partial`, not success.
- If `project-manifest.json` stores an earlier generation commit, use `generate.git.code_commit` or add `commit_role`; do not imply a manifest-tracked field can self-reference final HEAD.
- `payload.review_findings.blocking` must be empty; final review logs or JSON with critical/blocking findings must prevent success.
- Run `scripts/check_phase_complete_consistency.py` before emitting or accepting success.

## Resume And Stale Artifacts

Run `scripts/check_session_state.py --session-dir <session_root> --project-dir <project_root>` before deciding whether to resume a previous generate attempt.

Maintain the active checkpoint file with:

```bash
python scripts/update_session_state.py --session-dir <session_root> --checkpoint <name> --step <step> --status running --idempotency-key <stable-key>
python scripts/update_session_state.py --session-dir <session_root> --check
```

Record `session_state.upy_generate_plugin.json` after material checkpoints such as `started`, `tests_generated`, `git_committed`, `phase_completed`, `checks_failed`, `cancelled`, or `retrying`. For interruption cases use stable structured error codes such as `NETWORK_DISCONNECTED`, `RATE_LIMITED`, `UPSTREAM_TIMEOUT`, `TOKEN_BUDGET_EXCEEDED`, `MODEL_CONTEXT_EXHAUSTED`, and `CANCELLED_BY_USER`; retryable network/rate/timeout errors should keep the same session id and idempotency keys.

`session_state.upy_generate_plugin.json` must carry these stable fields:

| Field | Meaning |
|---|---|
| `manifest_hash` | SHA256 of the current `project/project-manifest.json`; use `"unknown"` only before a manifest exists. Completed success must record the real file hash, not a git commit. |
| `git_commit` | Final deliverable project HEAD. May be `null` while running, but completed `phase_completed` state must record the commit. |
| `usage.token_budget_status` | `unknown`, `ok`, or `exhausted`; use `exhausted` for token/quota stops. |
| `usage.remaining_budget` | Remaining model/token budget if known, otherwise `null`. |
| `last_ok_artifact` | Last trusted artifact for resume, such as `generate_plan` or `phase_complete`; required on completed success. |
| `artifacts` | Resumable artifacts written so far. Completed success should include at least `project_manifest` and `generate_plan`, and preferably `phase_complete` and `file_manifest`. |

Timeout and cancellation are protocol/state semantics in this plugin version. Record `UPSTREAM_TIMEOUT` or `CANCELLED_BY_USER` in `last_error` and stop or retry according to `retryable`; do not invent partial code or add an untested execution wrapper solely for timeout handling.

Always write this file through `scripts/update_session_state.py`; do not hand-write a reduced state object. For final validation run:

```bash
python scripts/update_session_state.py --session-dir <session_root> --project-dir <project_root> --check
```

The check must fail if `manifest_hash` is copied from `git_commit`, if the disk state is missing required protocol fields, or if `manifest_hash` does not match `project-manifest.json`.

Treat previous `phase_complete.upy_generate_plugin.json` as stale/audit-only when any of these are true:

- The previous generate event says `result=success`, but `project/project-manifest.json.phase` is not `generate`.
- The previous generate event says `result=success`, but `project/generate_plan.json` is missing.
- The previous `file_manifest.files[]` lists generated files that are absent from the current project tree.
- The previous generate log remains while project git state has been restored to scaffold.

When stale state is detected, do not resume from the stale event. Archive or ignore the stale `phase_complete.upy_generate_plugin.json` and `generate_phase_log.md`, then restart generation from the scaffold phase_complete and current project tree.

## Structured Error Fields

| Field | Meaning |
|---|---|
| `code` | Stable uppercase code, for example `PYLINT_FAILED`, `DRIVER_API_MISMATCH`, `DEAD_CONFIG`. |
| `severity` | `warning`, `error`, or `fatal`. |
| `phase_step` | Step that produced the error. |
| `retryable` | Whether retry after changes is meaningful. |
| `message` | Human-readable explanation. |
| `details` | Optional object with command output, files, line numbers, or device observations. |
| `next_action` | Suggested next phase or fix action. |

## Knowledge Pitfall JSON Fields

Files under `knowledge/*.pitfall.json` are an extensible error/attention knowledge base. Use `knowledge/_template.pitfall.json` as the canonical template.

| Field | Meaning |
|---|---|
| `field_descriptions` | Template-only documentation explaining each JSON field. Keep it in `_template.pitfall.json`; other pitfall files may omit it. |
| `id` | Stable kebab-case pitfall id. |
| `title` | Short human-readable pitfall title. |
| `category` | Domain category such as `micropython`, `driver`, `scheduler`, `lint`, `deploy`, or `user-feedback`. |
| `applies_to.modes` | `full`, `fix`, or both. |
| `applies_to.scheduler_modes` | Scheduler modes affected: `timer`, `async`, `thread`. |
| `applies_to.device_types` | Hardware classes affected, for example `i2c`, `spi`, `gpio`, `network`, `display`. |
| `applies_to.files` | Project-relative path patterns affected by the pitfall. |
| `symptoms` | User-visible symptoms, exceptions, logs, or deploy observations. |
| `wrong_pattern` | Anti-pattern to avoid. |
| `correct_pattern` | Correct generation or fix pattern. |
| `detection.script` | Bundled checker that can detect the issue, if any. |
| `detection.grep` | Search hint for manual review. |
| `detection.structured_error_code` | Stable structured error code to emit when triggered. |
| `fix_guidance` | Ordered repair hints. |
| `references` | Source docs or local reference files supporting the rule. |
| `verified_by` | Tests/checks that prove the issue is fixed. |
| `confidence` | `high`, `medium`, or `low`. |
| `last_seen` | Date this rule was last confirmed. |

## Cloud Integration Fields

Use `references/cloud_integrations.md` and `knowledge/cloud_service_catalog.json` whenever generated firmware calls an external API or paid cloud service.

`manifest_content.generate.cloud_integrations[]` entries use these fields:

| Field | Meaning |
|---|---|
| `provider_id` | Catalog provider id such as `volcengine_ark`, `aliyun_bailian`, `tencent_hunyuan`, `baidu_qianfan`, `openai`, `aliyun_iot`, or `custom_http_proxy`. |
| `category` | `llm`, `speech`, `vision`, `iot`, `notification`, `storage`, `data_api`, or `custom_http_proxy`. |
| `services` | Concrete service list such as `chat_completions`, `asr`, `tts`, `mqtt_publish`, or `webhook_post`. |
| `mode` | `direct_https`, `direct_mqtt`, `gateway_https`, `mock_only`, or another explicit transport mode. |
| `official_links` | Provider docs/product, console, and pricing/billing links shown to the user before API key or token setup. |
| `credential_management.requires_credentials` | Whether the integration needs a key/token/secret/password. |
| `credential_management.status` | `ready`, `deferred_to_deploy`, `mock_only`, `not_required`, or `blocked`. |
| `credential_management.secret_names` | Environment or secret-file variable names only; never values. |
| `user_action_required` | Steps the user must perform, for example create API key, enable billing, buy token quota, or provide deploy secret. |
| `deploy_ready` | Whether this integration can proceed to real device deploy. |
| `deploy_blocker` | Reason when deploy is blocked or deferred. |

When `next_phase=upy-deploy-plugin`, each cloud integration must be `ready`, `deferred_to_deploy`, or `not_required`. `mock_only` must route to simulate/null, not deploy.

## Next Phase Rules

| Condition | `next_phase` |
|---|---|
| User wants real device run and checks pass | `upy-deploy-plugin` |
| User wants PC logic simulation first | `upy-simulate-plugin` |
| User wants to stop after generation | `null` |
| Any strong quality gate fails | `null` |
| Cold driver is required for deploy | `null` or `upy-simulate-plugin` only if user accepts mock-only simulation |

`upy-autofix-plugin` is not a normal success next phase. It is a failure/feedback orchestrator.
