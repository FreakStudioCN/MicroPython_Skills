# Protocol Fields

Use this reference when creating or validating `start_phase`, `phase_complete`, checkpoints, permissions, file manifests, and structured errors for `upy-gen-driver-plugin`.

## Protocol Identity Guard

The plugin identity is fixed as `upy-gen-driver-plugin`. Do not rename or alias it to `upy-driver-plugin`, `driver`, `gen-driver-plugin`, or any other phase name.

- Envelope `phase` must be `upy-gen-driver-plugin`.
- Payload `phase` and `domain_phase` must be `gen-driver`.
- Final protocol output must be `phase_complete.upy_gen_driver_plugin.json`.
- Session state must be `session_state.upy_gen_driver_plugin.json`.
- `idempotency_key`, `checkpoint_id`, `resume_phase`, and permission action keys must use the `upy-gen-driver-plugin` prefix.
- Existing files with another driver phase name are stale/wrong-phase artifacts; regenerate them with this identity instead of validating or resuming from them.

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

The same envelope applies to plugin-host execution and local mock execution. Local mocks may perform actions directly, but the recorded artifacts must look like plugin protocol results.

## Runtime Context

`runtime_context.session_root` owns the workflow state. `project_root` owns generated project files. `file_operation_root` is the maximum root allowed for file writes. `resource_root` points at the skill resources. Official artifact paths must be relative and POSIX-style.

Required fields: `artifact_root`, `session_root`, `project_root`, `file_operation_root`, and `resource_root`.

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

Start every run by checking required capabilities for the selected mode. Do not defer a missing required capability until after files have been generated unless the capability is optional for the current path.

Use `HOST_CAPABILITY_MISSING` when a required host capability is absent, and record `details.missing_capability`. Use `DEVICE_NOT_FOUND` only after device scan/run capability exists, permission was granted, and the scan/run actually failed to find the target device. A `DEVICE_NOT_FOUND` result must have at least one `payload.permissions[]` entry with `operation="device_scan"` or `operation="device_run"`.

## Checkpoints

Stable checkpoint names: `started`, `input_collected`, `source_preprocessed`, `understanding_written`, `debug_driver_written`, `hardware_verify_ready`, `hardware_verify_passed`, `production_driver_written`, `normalized`, `standalone_assets_written`, `standalone_test_passed`, `manifest_updated`, `phase_completed`, `cancelled`, `verification_exhausted`.

`phase_complete.payload.checkpoint.checkpoint_id` must use this exact shape:

```text
upy-gen-driver-plugin:<session_id>:<checkpoint_name>
```

Do not omit `<session_id>`. The final segment must be one of the stable checkpoint names above.

## Idempotency Keys

Format:

```text
upy-gen-driver-plugin:<session_id>:<step>:<artifact-or-round>:v1
```

Use the same key for retrying the same action. Do not repeat a write when the target hash already matches.

Recommended action keys:

| Action | Key shape |
|---|---|
| Start phase | `upy-gen-driver-plugin:<session_id>:start:v1` |
| Source preprocessing | `upy-gen-driver-plugin:<session_id>:preprocess:<source_hash>:v1` |
| Write understanding | `upy-gen-driver-plugin:<session_id>:write_understanding:<chip>:v1` |
| Write debug driver | `upy-gen-driver-plugin:<session_id>:write_debug_driver:<chip>:v1` |
| Device scan | `upy-gen-driver-plugin:<session_id>:device_scan:<chip>:v1` |
| Device run | `upy-gen-driver-plugin:<session_id>:device_run:<chip>:round<N>:v1` |
| Retry device run | Reuse the same key for the same round and set `retry_of`. |
| Write unverified driver artifact | `upy-gen-driver-plugin:<session_id>:write_driver_artifact:<chip>:v1` |
| Write production driver | `upy-gen-driver-plugin:<session_id>:write_production_driver:<chip>:v1` |
| Manifest update | `upy-gen-driver-plugin:<session_id>:manifest_update:<chip>:v1` |

Use `write_driver_artifact` when `{chip}.py` is emitted with role `artifact` because hardware verification is pending. Use `write_production_driver` only when the corresponding `file_manifest.files[]` entry has role `production_driver`.

## Permissions

Permission entries must include `permission_id`, `operation`, `reason`, `timeout_ms`, `idempotency_key`, and any relevant `paths`, `command_preview`, or `network_domains`.

For `file_read`, `file_write`, and `manifest_update`, `paths[]` is required. Do not use `target` as a substitute because hosts and local tests need per-file auditability.

Operations: `file_read`, `file_write`, `script_run`, `device_scan`, `device_run`, `network_fetch`, `manifest_update`.

Local mock tests must still write permission entries. If the mock auto-grants permission, set `result="granted"` and include `mock=true` in the entry details.

Do not reuse the same `idempotency_key` for different permission actions. Reuse is allowed only for retrying the same action signature: same operation, same paths, same command preview, same network domains, and the later permission entry must include `retry_of`.

All user-facing protocol text fields and generated text artifacts (`.py`, `.md`, `.json`, `.txt`, `.yaml`, source snippets) must be UTF-8 clean. Reject replacement characters, mojibake sequences, C1 control characters, smart punctuation, and isolated foreign-script fragments in otherwise English/Chinese protocol text. Use ASCII punctuation for generated protocol strings, code comments, and Markdown.

Example:

```json
{
  "permission_id": "device_run_sht30_round1",
  "operation": "device_run",
  "reason": "Run SHT30 debug driver on the selected MicroPython device.",
  "paths": ["sessions/sample/project/firmware/drivers/sht30_driver/sht30_debug.py"],
  "command_preview": "mpremote connect <port> resume run <debug-driver>",
  "timeout_ms": 60000,
  "idempotency_key": "upy-gen-driver-plugin:sample:device_run:sht30:round1:v1",
  "result": "granted"
}
```

## Retry, Cancellation, Timeout, Resume

Retry:

- Keep `session_id`.
- Keep the same `idempotency_key` when retrying the same action.
- Set `retry_of` to the original message id.
- Append a `session_state.events[]` item with `status="retrying"`.
- For partial results, record at least one resume artifact in `session_state.artifacts[]` or `session_state.last_ok_artifact`.

Cancellation:

- Treat cancellation as resumable partial unless artifacts are explicitly discarded.
- Use checkpoint `cancelled`.
- Return `CANCELLED_BY_USER` with `retryable=true` and `next_action="resume_upy_gen_driver_plugin"` when resume is possible.

Timeout:

- Every approval, script, device, and network operation must declare `timeout_ms`.
- Convert timeouts into structured errors. Use `SOURCE_PREPROCESS_TIMEOUT` for preprocessing and `DEVICE_RUN_TIMEOUT` for device execution.
- Do not continue to `success` after a timeout unless a later retry completed the required step.

Resume:

- Validate `session_id`, `protocol_version`, `phase`, checkpoint name, and last trusted artifact.
- Validate hashes when `sha256` is present.
- Return `ARTIFACT_STALE` if the artifact or manifest changed underneath the checkpoint.
- Do not re-run completed writes when the output hash already matches.

## File Manifest

Each `file_manifest.files[]` entry should include:

| Field | Rule |
|---|---|
| `path` | Relative path, no drive letter, no `..`. |
| `status` | `created`, `updated`, `unchanged`, `skipped`, or `error`. |
| `role` | `source`, `extracted_text`, `mapping`, `understanding`, `debug_driver`, `production_driver`, `test`, `wiring`, `verify_log`, `manifest`, `state`, `phase_complete`, or `artifact`. |
| `sha256` | Final SHA-256 hash for every existing/generated file. Do not use `hash="unverified"` or placeholder hashes. |
| `bytes` | UTF-8 byte length or binary file byte length for every existing/generated file. |
| `overwrite` | True only with explicit approval. |

Build the final manifest after the final `session_state.upy_gen_driver_plugin.json` update. Prefer `scripts/finalize_phase_complete.py` over hand-written hashes:

```bash
python scripts/finalize_phase_complete.py --input <draft_phase_complete> --output <session_root>/phase_complete.upy_gen_driver_plugin.json --artifact-root <artifact_root> --session-state <session_root>/session_state.upy_gen_driver_plugin.json
```

Do not modify files listed in `payload.file_manifest.files[]` after this command. If `session_state` or any artifact changes, rerun the command so `sha256` and `bytes` match disk.

`production_driver` may appear only when real hardware verification passed or when the user explicitly skipped verification and the payload records `verification_skipped_by_user=true` with a warning. Mock verification must not set `hardware_verified=true`, must not set `next_phase`, and must write manifest driver status as `unverified`. A no-device, timeout, cancellation, local mock, or unverified partial result must not label `{chip}.py` as `production_driver`.

If an unverified `{chip}.py` is emitted for inspection, use role `artifact` and UI text such as `Driver artifact (unverified)` or `Unverified driver artifact`. Do not display it as `Production driver (unverified)`.

For unverified partial outcomes, no summary, file manifest description, artifact label, permission reason, or other user-facing text should use `production driver` wording.

The idempotency key for that unverified file write must use `write_driver_artifact`, not `write_production_driver`.

## Driver Understanding

For I2C devices, `driver_understanding.json` must distinguish datasheet evidence from MicroPython runtime addresses:

| Field | Rule |
|---|---|
| `addressing.address_7bit` | Required I2C address used by MicroPython APIs. |
| `addressing.datasheet_write_8bit` | Optional datasheet write transfer address, evidence only. |
| `addressing.datasheet_read_8bit` | Optional datasheet read transfer address, evidence only. |
| `addressing.derivation` | Required when 8-bit transfer addresses are present, e.g. `0x3C >> 1 = 0x1E`. |
| `addressing.code_address_rule` | Use `Use address_7bit for MicroPython I2C APIs.` |

Do not pass datasheet 8-bit transfer addresses to `scan()`, `readfrom_mem()`, `writeto_mem()`, or equivalent MicroPython I2C APIs.

## Driver Static Quality

Before emitting `phase_complete`, validate generated Python artifacts without writing `__pycache__`:

- Compile source text with `compile(source, path, "exec")`.
- Reject undefined driver names, except MicroPython builtins and guarded imports.
- Reject helper method arity mismatches such as calling `_read_reg(reg, buf)` when `_read_reg` only accepts `reg`.
- Reject I2C duck-typing checks that do not include the exact methods used later.
- Reject test scripts that use `const(...)` without importing `const` from `micropython` or defining a fallback.
- Reject `const(...)` calls with non-integer literal arguments. Keep float scale factors as normal variables.
- Reject `__pycache__` directories and `.pyc` files under `artifact_root`.

## Structured Errors

Each error must include: `code`, `severity`, `phase_step`, `retryable`, `message`, `details`, `next_action`.

Known codes: `MISSING_INPUT_SOURCE`, `SOURCE_PREPROCESS_FAILED`, `SOURCE_PREPROCESS_TIMEOUT`, `DATASHEET_PARSE_INSUFFICIENT`, `I2C_ADDRESS_AMBIGUOUS`, `I2C_ADDRESS_NORMALIZATION_REQUIRED`, `HOST_CAPABILITY_MISSING`, `PERMISSION_DENIED`, `APPROVAL_TIMEOUT`, `DEVICE_NOT_FOUND`, `DEVICE_RUN_TIMEOUT`, `HARDWARE_VERIFY_FAILED`, `HARDWARE_VERIFY_EXHAUSTED`, `STANDALONE_TEST_FAILED`, `MANIFEST_UPDATE_CONFLICT`, `ARTIFACT_STALE`, `CANCELLED_BY_USER`, `PROTOCOL_VERSION_UNSUPPORTED`, `IDEMPOTENCY_CONFLICT`, `PHASE_COMPLETE_INVALID`.

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
- `artifacts[]` containing a non-empty `file_list`
- `permissions[]`
- `structured_errors[]`
- `hardware_verified`
- `verification_mode`: `hardware`, `mock`, `skipped`, or `none`
- `manifest_content` when a manifest exists

For every `file_list` artifact, include non-empty `files[]` or `items[]`. Do not emit a placeholder file list with only `title`, `label`, or an empty array.

Write `phase_complete` as the last workflow file. It must not include a self-referential `file_manifest` entry for `phase_complete.upy_gen_driver_plugin.json`; host or an external sidecar may audit that envelope separately.

For `result="partial"`:

- `checkpoint.resume_phase` must be `upy-gen-driver-plugin`.
- `checkpoint.resume_step` must identify the next runnable step.
- `structured_errors[]` must be non-empty.
- `file_manifest.files[]` must include the last trusted artifact when one exists.
- Set `hardware_verified=false`.
- Set `verification_mode="none"` for no-device, timeout, cancellation, permission denial, capability missing, and ordinary unverified partial outcomes.
- Do not set `mock_verification=true`.

For `result="success"`:

- `structured_errors[]` must be empty.
- Hardware verification must be true, the payload must explicitly mark verification skipped by user approval, or a local mock self-test must have actually returned `SELF_TEST_PASS`.
- Use `verification_mode="hardware"` when real hardware passed.
- Use `verification_mode="mock"` only for local mock self-test success, with `hardware_verified=false` and a warning.
- Use `verification_mode="skipped"` only when `verification_skipped_by_user=true` and a warning exists.
