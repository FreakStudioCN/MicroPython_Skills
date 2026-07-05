# Protocol Fields

Use this reference when creating or validating `start_phase`, `phase_complete`, checkpoints, permissions, file manifests, and structured errors for `upy-gen-driver-plugin`.

## Envelope

Required fields:

| Field | Required | Rule |
|---|---|---|
| `protocol_version` | yes | Use `"1.0"` until a breaking protocol change is introduced. |
| `msg_id` | yes for emitted messages | Unique event id. |
| `session_id` | yes | Stable workflow session id. Retries and resumes keep the same value. |
| `phase` | yes | Must be `upy-gen-driver-plugin`. |
| `timestamp` | yes for emitted messages | UTC ISO timestamp. |
| `type` | yes | `start_phase`, `status_update`, `approval_request`, `permission_request`, `script_run`, `device_command`, `file_operation`, or `phase_complete`. |
| `idempotency_key` | yes for action messages | Include phase, session id, step, artifact or round, and version. |
| `retry_of` | no | Previous `msg_id` when retrying. |

## Runtime Context

`runtime_context.session_root` owns the workflow state. `project_root` owns generated project files. `resource_root` points at the skill resources. Official artifact paths must be relative and POSIX-style.

## Capability Negotiation

| Capability | Needed for | Missing behavior |
|---|---|---|
| `file_upload` | source collection | `partial` with `HOST_CAPABILITY_MISSING` or ask for text/url input. |
| `script_run` | PDF/Arduino preprocessing and run_on_device | Skip only if preprocessed content is provided; otherwise partial. |
| `file_operation` | driver/test/wiring/manifest writes | Required. |
| `permission_request` | local sensitive operations | Fallback to approval-style permission card only if host lacks permission messages. |
| `serial_port_scan` or `device_command` | hardware verification | Save checkpoint and resume later. |
| `mpremote_run` | debug and standalone tests | Save checkpoint unless user explicitly skips verification. |
| `checkpoint_resume` | long flows | Do not start hardware verification loop if missing. |
| `cancellation` | user cancellation | Still expose save/cancel approval actions. |

## Checkpoints

Stable checkpoint names: `started`, `input_collected`, `source_preprocessed`, `understanding_written`, `debug_driver_written`, `hardware_verify_ready`, `hardware_verify_passed`, `production_driver_written`, `normalized`, `standalone_assets_written`, `standalone_test_passed`, `manifest_updated`, `phase_completed`, `cancelled`, `verification_exhausted`.

## Idempotency Keys

Format:

```text
upy-gen-driver-plugin:<session_id>:<step>:<artifact-or-round>:v1
```

Use the same key for retrying the same action. Do not repeat a write when the target hash already matches.

## Permissions

Permission entries must include `permission_id`, `operation`, `reason`, `timeout_ms`, `idempotency_key`, and any relevant `paths`, `command_preview`, or `network_domains`.

Operations: `file_read`, `file_write`, `script_run`, `device_scan`, `device_run`, `network_fetch`, `manifest_update`.

## File Manifest

Each `file_manifest.files[]` entry should include:

| Field | Rule |
|---|---|
| `path` | Relative path, no drive letter, no `..`. |
| `status` | `created`, `updated`, `unchanged`, `skipped`, or `error`. |
| `role` | `source`, `extracted_text`, `mapping`, `understanding`, `debug_driver`, `production_driver`, `test`, `wiring`, `verify_log`, `manifest`, `state`, `phase_complete`, or `artifact`. |
| `sha256` | Final hash when file exists. |
| `bytes` | UTF-8 byte length when known. |
| `overwrite` | True only with explicit approval. |

## Structured Errors

Each error must include: `code`, `severity`, `phase_step`, `retryable`, `message`, `details`, `next_action`.

Known codes: `MISSING_INPUT_SOURCE`, `SOURCE_PREPROCESS_FAILED`, `SOURCE_PREPROCESS_TIMEOUT`, `DATASHEET_PARSE_INSUFFICIENT`, `HOST_CAPABILITY_MISSING`, `PERMISSION_DENIED`, `DEVICE_NOT_FOUND`, `DEVICE_RUN_TIMEOUT`, `HARDWARE_VERIFY_FAILED`, `HARDWARE_VERIFY_EXHAUSTED`, `STANDALONE_TEST_FAILED`, `MANIFEST_UPDATE_CONFLICT`, `ARTIFACT_STALE`, `CANCELLED_BY_USER`, `PHASE_COMPLETE_INVALID`.

## Phase Complete

`phase_complete.payload` must include:

- `phase="gen-driver"`
- `domain_phase="gen-driver"`
- `result`: `success`, `partial`, or `failed`
- `summary`
- `next_phase`: usually `upy-generate-plugin` or `null`
- `runtime_context`
- `checkpoint`
- `file_manifest`
- `artifacts[]` containing a `file_list`
- `permissions[]`
- `structured_errors[]`
- `manifest_content` when a manifest exists
