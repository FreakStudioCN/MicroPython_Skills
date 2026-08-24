# mpos-robot-skill/v1

## Contents

- Envelope
- Session and checkpoint
- Retry, cancellation, and timeout
- Capabilities
- Permissions
- Errors
- Artifacts

## Envelope

Use the same logical protocol for direct local invocation and calls relayed by an independently implemented website:

```json
{
  "protocol_version": "mpos-robot-skill/v1",
  "session_id": "stable-session-id",
  "checkpoint_id": null,
  "idempotency_key": "caller-generated-key",
  "operation": "generate",
  "stage": "generate",
  "status": "running",
  "capabilities": {},
  "input": {}
}
```

Valid stages are `analyze`, `prepare_deps`, `generate`, `test`, `package`, `deploy`, and `publish_check`.

Valid terminal or wait statuses are `completed`, `partial`, `blocked`, `waiting_device`, `failed`, `cancelled`, and `timeout`.

## Session and checkpoint

Persist Session state, append-only activity records, operation receipts, permission decisions, artifact manifest, stage results, and checkpoints. Use atomic replacement for mutable JSON files.

Commit a checkpoint only after its result and artifact entries are durable and validated. Record protocol version, normalized-input hash, Skill version, protected-template hash, stage, result IDs, artifact hashes, and next stage. Never include driver source or secrets.

Resume with the original `session_id` and latest valid `checkpoint_id`. Revalidate referenced artifacts. Reuse completed stages and redo only an incomplete stage from its last safe boundary.

## Retry, cancellation, and timeout

Scope idempotency to `session_id + operation + idempotency_key`. Return the stored result for the same input hash. Return `IDEMPOTENCY_CONFLICT` if the same key carries different input.

Retry only errors marked `retryable`. Record `retry_of` and attempt count. Never repeat a successful device write or dependency installation without checking its operation receipt.

Persist `cancel_requested`. Check it between network chunks, motion interpolation steps, audio chunks, tests, and scripts. Do not interrupt an unsafe device-write critical section; cancel at its next safe boundary.

Apply separate network, script, stage, device-wait, and Session deadlines. Return `timeout`, not generic failure, and preserve the last valid checkpoint.

## Capabilities

Negotiate at least:

- `file_read`, `file_write`, `script_run`, `network_read`
- `mpremote`, `device_serial`, `device_write`, `physical_device`
- `desktop_simulation`, `robot_direct_pwm`, `robot_i2s_audio`
- `robot_wifi_conversation`, `permission_prompts`, `artifact_manifest`

Capabilities must be observed or caller-declared. A desktop simulation never proves physical PWM or I2S.

## Permissions

Request permission before `file_create`, `file_overwrite`, `script_run`, `network_read`, `dependency_install`, `package_build`, `serial_scan`, `device_connect`, `device_command`, `device_write`, `firmware_flash`, or `remote_upload`.

Bind each request and decision to `permission_id`, Session, stage, resource, risk, input hash, idempotency key, and expiry. Reuse an unexpired approval only when all bound values still match.

## Errors

Return:

```json
{
  "code": "ROBOT_PIN_CONFLICT",
  "message": "human-readable summary",
  "stage": "generate",
  "retryable": false,
  "owner": "skill",
  "details": {},
  "logs": [],
  "artifact_ids": [],
  "permission_id": null
}
```

Use stable codes including `ROBOT_PROFILE_INVALID`, `ROBOT_PIN_CONFLICT`, `ROBOT_CAMERA_CONFLICT`, `ROBOT_TEMPLATE_MODIFIED`, `DEPENDENCY_UNAVAILABLE`, `RUNTIME_CAPABILITY_MISSING`, `CHECKPOINT_INCOMPATIBLE`, `CHECKPOINT_CORRUPTED`, `IDEMPOTENCY_CONFLICT`, `DEVICE_NOT_FOUND`, `PERMISSION_DENIED`, `OPERATION_CANCELLED`, and `STAGE_TIMEOUT`.

## Artifacts

Record artifact ID, kind, role, Session-relative path, MIME type, SHA-256, size, stage, revision, and creation time. Reject absolute paths and parent traversal.

Register results, dependency-resolution metadata, generated App source, default profile, tests, package, deploy result, activity log, and Session state. Do not register installed uPyPI driver files as Skill artifacts.
