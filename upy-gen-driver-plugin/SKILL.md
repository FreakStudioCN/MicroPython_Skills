---
name: upy-gen-driver-plugin
description: Plugin workflow skill for generating missing MicroPython hardware drivers from datasheets, Arduino/C/C++ source, GitHub repositories, chip model names, or current project cold-driver items. Use when a plugin global tool such as "生成缺失硬件驱动" is invoked, when a manifest contains devices with driver.status=cold_driver_required, or when deploy/autofix feedback shows a missing or broken hardware driver that must be generated with session/checkpoint/resume, retry, timeout, cancellation, permission prompts, structured errors, and artifact manifests.
---

# upy-gen-driver-plugin

Generate a missing MicroPython driver without modifying the legacy `upy-gen-driver` skill. This skill is the plugin-workflow version: use protocol messages for local file, script, device, and approval operations, and emit resumable artifacts for both plugin runs and local mock tests.

## Operating Modes

- `pipeline`: Run from an active project session after scaffold and before generate. Consume upstream `manifest_content`, update the project driver files, and return to `upy-generate-plugin`.
- `standalone`: Run from the global plugin tool "生成缺失硬件驱动". Ask for PDF, Arduino/C/C++ source, GitHub URL, chip model, or image input, then generate an independent driver package and test material.
- `resume`: Continue from `session_state.upy_gen_driver_plugin.json`; validate artifact hashes before reusing any checkpoint.
- `fix`: Repair a generated driver from deploy/autofix feedback using the smallest code change.

## Required References

Read these only when needed:

- `references/protocol_fields.md`: message envelope, start payload, checkpoint, phase_complete, file_manifest, permissions, structured errors.
- `references/legacy_upy_gen_driver_rules.md`: legacy driver-generation rules that must be preserved.
- `references/norm_driver_p0_rules.md`: production driver normalization checklist.

## Core Rules

- Never overwrite or edit `G:\MicroPython_Skills\upy-gen-driver`.
- Use envelope `phase="upy-gen-driver-plugin"` and payload/domain phase `gen-driver`.
- Keep official artifact paths relative to `artifact_root` or `project_root`; never place Windows drive paths in `phase_complete`.
- Treat `runtime_context.session_root` as the workflow session source of truth. Do not infer the session from the newest `sessions/*` directory.
- Use `permission_request` for local file, script, network, and device operations; use `approval_request` for user business choices.
- Every local action must have a stable `idempotency_key`.
- Every script/device/approval wait must have `timeout_ms`.
- On user cancel, no device, timeout, stale artifact, missing capability, or exhausted hardware verification, emit `result="partial"` with checkpoint and `structured_errors[]`; do not claim success.
- Hardware verification may be skipped only by explicit user choice and the final result must carry a warning. Default behavior is to save a checkpoint and resume later.

## Start Phase Contract

Accept plugin `start_phase` with envelope `protocol_version`, `msg_id`, `session_id`, `phase="upy-gen-driver-plugin"`, `type="start_phase"`, and a stable `idempotency_key`.

Payload fields:

- `mode`: `pipeline`, `standalone`, `resume`, or `fix`.
- `phase` / `domain_phase`: `gen-driver`.
- `source_phase`, `source_phase_complete_path`, `manifest_content`: required for pipeline when available.
- `source`: PDF, Arduino/C/C++ file, GitHub URL, chip model, image, or current cold-driver item. If missing, ask with `approval_request(gen_driver_input)`.
- `runtime_context`: `artifact_root`, `session_root`, `project_root`, `file_operation_root`, `resource_root`.
- `capabilities`: host support for approvals, permissions, file/script/device operations, upload, cancellation, checkpoint resume, and idempotency cache.
- `resume_from`: checkpoint descriptor for resume mode.

If `mode` is absent, infer `pipeline` only when a current manifest contains `driver.status=cold_driver_required`; otherwise use `standalone`.

## Workflow

1. Validate envelope, runtime roots, and capabilities.
2. If source is missing, emit `approval_request(gen_driver_input)` for the global tool input card.
3. Collect one source type: PDF, Arduino/C/C++ source, GitHub URL, chip model, image, or current project cold-driver item.
4. Preprocess sources through protocol `script_run`:
   - PDF: `scripts/extract_pdf.py --input <path> --output <json> --json-summary`
   - Arduino/C/C++: `scripts/convert_arduino.py --input <path> --output <json> --json-summary`
5. Write `driver_understanding.json` through `file_operation(write)`. Include protocol, address, ID register, ready strategy, data integrity, register map, source evidence, and ambiguity notes.
6. Generate `{chip}_debug.py` through `file_operation(write)`. The debug driver must include self-test prints and bounded polling.
7. Update session state checkpoint `debug_driver_written`.
8. Request permission for device scan and debug run. If no device is present, emit `approval_request(gen_driver_no_device)` with `retry`, `save_partial`, and `cancel`.
9. Run hardware verification for at most 10 rounds with `scripts/run_on_device.py --com <port> --file <debug.py> --capture --timeout-ms 30000 --json-summary`.
10. If `SELF_TEST_PASS` appears, checkpoint `hardware_verify_passed`. Otherwise analyze the log, edit the debug driver, and retry until max rounds.
11. Generate production `{chip}.py` only after verified pass or explicit skip warning. Strip debug prints, keep meaningful exceptions, keep dependency injection.
12. Normalize production driver using `references/norm_driver_p0_rules.md`.
13. Generate `test_{chip}.py` and `wiring_{chip}.md` for standalone hardware validation.
14. Optionally run standalone test after `approval_request(gen_driver_standalone_test)`.
15. In `pipeline` mode, update `project/project-manifest.json` and `manifest_content.devices[].driver` with the generated local driver.
16. Emit `approval_request(gen_driver_next_step)` only when user choice is required. Common choices: integrate to `upy-generate-plugin`, finish, or publish later.
17. Write `phase_complete.upy_gen_driver_plugin.json`, validate it with `scripts/validate_phase_complete.py`, then emit it as the final result.

## Checkpoints

Use these stable checkpoint names:

`started`, `input_collected`, `source_preprocessed`, `understanding_written`, `debug_driver_written`, `hardware_verify_ready`, `hardware_verify_passed`, `production_driver_written`, `normalized`, `standalone_assets_written`, `standalone_test_passed`, `manifest_updated`, `phase_completed`, `cancelled`, `verification_exhausted`.

Maintain state with:

```bash
python scripts/update_session_state.py --session-dir <session_root> --session-id <session_id> --checkpoint <name> --step <step> --status running --idempotency-key <key>
python scripts/update_session_state.py --session-dir <session_root> --check
```

## Structured Errors

Use stable codes from `references/protocol_fields.md`. Important codes include `MISSING_INPUT_SOURCE`, `HOST_CAPABILITY_MISSING`, `PERMISSION_DENIED`, `SOURCE_PREPROCESS_FAILED`, `SOURCE_PREPROCESS_TIMEOUT`, `DEVICE_NOT_FOUND`, `DEVICE_RUN_TIMEOUT`, `HARDWARE_VERIFY_FAILED`, `HARDWARE_VERIFY_EXHAUSTED`, `STANDALONE_TEST_FAILED`, `MANIFEST_UPDATE_CONFLICT`, `ARTIFACT_STALE`, and `CANCELLED_BY_USER`.

Each error must include `code`, `severity`, `phase_step`, `retryable`, `message`, `details`, and `next_action`.

## Required Artifacts

On success, include these in `payload.file_manifest.files[]` when produced:

- `gen_driver/docs/driver_understanding.json`
- `project/firmware/drivers/<chip>_driver/<chip>_debug.py`
- `project/firmware/drivers/<chip>_driver/<chip>.py`
- `project/firmware/drivers/<chip>_driver/test_<chip>.py`
- `project/firmware/drivers/<chip>_driver/wiring_<chip>.md`
- `gen_driver/logs/driver_verify_round<N>.log` or an explicit skip-verification artifact
- `session_state.upy_gen_driver_plugin.json`
- `phase_complete.upy_gen_driver_plugin.json`
- `project/project-manifest.json` in pipeline mode

On partial, include the last trusted artifact and a checkpoint that can resume from it.

## Local Mock Testing

Local testing may write files, but it must also write protocol artifacts under `sessions/<session_id>/gen_driver/`. Use:

```bash
python test/smoke_tests.py
python test/run_local_mock_session.py --mode standalone --scenario no_device
python scripts/validate_phase_complete.py --input sample/phase_complete.upy_gen_driver_plugin.partial.no_device.json
```

Do not treat mock outputs as proof of real hardware verification.
