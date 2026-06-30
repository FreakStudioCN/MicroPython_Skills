# Validation Gates

Run these gates before any `phase_complete.result=success`.

Before resuming or regenerating in an existing session, first run:

```bash
python scripts/check_session_state.py --session-dir <session_root> --project-dir <project_root>
```

If it reports `STALE_GENERATE_PHASE_COMPLETE`, `STALE_GENERATE_PLAN_MISSING`, or `STALE_GENERATE_FILE_MANIFEST_MISSING_FILES`, treat prior generate artifacts as stale/audit-only and restart from scaffold input. Do not let a stale success phase_complete drive resume.

## Required Order

```text
1. ensure .pylintrc exists
2. check_generate_plan.py --project-dir <project_root> --require-plan
3. py_compile generated project Python files
4. check_conf_contract.py --project-dir <project_root>
5. compile downloaded driver sources
6. flake8 firmware test tools --extend-exclude=firmware/lib
7. pylint generated firmware entrypoint/adapters/tasks --rcfile=.pylintrc
8. python -m unittest discover -s test/pc
9. check_mpy_imports.py --project-dir <project_root>
10. check_mpy_imports.py --project-dir <project_root> --include-lib
11. check_dead_config.py --project-dir <project_root>
12. check_task_no_machine_import.py --project-dir <project_root>
13. check_device_unittest_subset.py --project-dir <project_root>
14. check_runtime_dependencies.py --project-dir <project_root>
15. check_doc_evidence.py --project-dir <project_root>
16. check_skeleton_compliance.py --project-dir <project_root>
17. check_generated_semantics.py --project-dir <project_root>
18. check_cloud_integrations.py --project-dir <project_root>
19. update_session_state.py --session-dir <session_root> --project-dir <project_root> --check
20. final review checklist
21. check_final_review_consistency.py --phase-complete <phase_complete> --log <generate_phase_log.md>
22. check_phase_complete_consistency.py --phase-complete <phase_complete> --project-dir <project_root>
23. shared session chain validation when a full plugin session exists
```

## Plan-First Contract

Before writing runtime code, create `project/generate_plan.json` and validate it with `check_generate_plan.py --require-plan`.

The plan must declare scheduler mode, tasks, driver adapters, `config_constants`, `main_assembly`, tests, resource plan, and cloud integrations when needed. The plan is a strong P0 gate: do not continue to broad code generation when it fails.

For voice, sensor, cloud API, state-machine, pipeline, or other cross-stage flows, the plan must declare `data_flow_contract[]`. Each contract needs `name`, `producer`, `consumer`, `invariant`, test coverage, and `storage` when producer/consumer are in different ticks or states. The matching PC contract test should use sentinel data or spy objects to prove the generated consumer receives the produced data.

After runtime code is written, run the final plan gate with file existence checking:

```bash
python scripts/check_generate_plan.py --project-dir <project_root> --require-plan --check-files
```

The final plan gate must prove every planned task, driver adapter, middleware file, and PC/device test path exists. A planned file that was not generated is a P0 failure (`GENERATE_PLAN_FILE_MISSING`) and cannot be hidden by a passing `phase_complete`.

After writing `conf.py` and `main.py`, run `check_conf_contract.py` immediately. This catches undefined `conf.X` references, duplicate constants, secret-like values, and deploy-blocking placeholders earlier than PC tests.

## Gate Levels

- **P0 generate contract gates:** `check_generate_plan`, `py_compile`, `check_conf_contract`, `check_phase_complete_consistency`, file manifest completeness, no Python cache artifacts, and git status cleanliness. These must pass for any `result=success`.
- **P1 deploy-ready gates:** cloud setup, credential status, MicroPython imports, resource plans, skeleton compliance, and device smoke constraints. These must pass before `next_phase=upy-deploy-plugin`.
- **P2 advisory gates:** pylint warning/refactor/convention-only output, optional diagram/wiring availability, scaffold helper usage, and style-only concerns.

## Strong Gates

The following failures must block deploy-ready success:

- Syntax compile failure in generated firmware/tasks/drivers/main/test code.
- Missing or invalid `generate_plan.json`.
- `generate_plan.json` declares generated files that do not exist after generation.
- Missing `data_flow_contract[]` or missing contract test coverage for complex voice/sensor/cloud/state-machine flows.
- Undefined `conf.X` reference, duplicate `conf.py` constant, or real secret value in `conf.py`.
- flake8 failure in generated non-lib code.
- pylint fatal/error/usage in generated non-lib firmware code.
- PC unittest failure.
- MicroPython import failure outside `firmware/lib`.
- Dead generated business config.
- `machine` import inside task code.
- Unsupported device-side `unittest` assertion, helper, or CPython-only test import inside `test/device` or `device/tests`.
- Device-side `unittest` tests without `runtime_dependencies.mip` entry for `unittest`.
- Firmware or tests importing mip-provided packages without deploy-phase `runtime_dependencies.mip` entries.
- Hardware/peripheral/port MicroPython APIs without `generate.doc_evidence[]` entries pointing to official MicroPython docs.
- `payload.manifest_content` changes upstream hardware facts (`mcu`, `board`, `devices`, or `pinout`) compared with scaffold/select-hw/flash `phase_complete`; new devices or wiring changes must go back through analyze/select-hw/scaffold first.
- New generated device-side MicroPython unittest files missing from `device/tests` when no legacy project layout requires `test/device`.
- `generate.deploy_plan.source_only` missing `firmware/main.py`, `firmware/boot.py`, or `firmware/conf.py`, or `generate.deploy_plan.upload_exclude` missing `firmware/drivers/**/mock.py` and `firmware/drivers/**/mock.mpy`.
- Runtime firmware depending on generated `firmware/drivers/**/mock.py`; mocks are test/support artifacts and must not be uploaded as production device code.
- Modifying scaffold-owned framework files (`firmware/lib/logger/*`, `firmware/lib/scheduler/*`, `firmware/lib/time_helper.py`, `firmware/tasks/maintenance.py`) to hide generator/checker/deploy issues.
- Missing boot delay.
- Scheduler mode mismatch.
- `board.py` instantiates hardware or pinout changed silently.
- Runtime placeholder payloads or TODO implementations in generated firmware.
- Per-tick state-machine reset that loses state across calls.
- Async tasks calling synchronous HTTP/network operations without a cooperative strategy.
- Async tasks calling blocking driver/time operations such as `time.sleep_ms`, `read_samples`, `play_samples`, `connect`, or busy scan calls inside `async def` without an async adapter.
- Async code hiding blocking driver/time/network calls behind `getattr`, `__getattribute__`, alias variables, reflection helpers, lambdas, or synchronous wrapper functions.
- Async wrappers that only `await asyncio.sleep_ms(...)` before calling blocking `record`, `play`, `connect`, scan, or synchronous HTTP APIs. A real strategy must be cooperative state-machine steps, thread/worker handoff, a genuinely non-blocking driver API, or `partial`.
- Captured device data discarded before payload/output use.
- Shared I2S/SPI/UART resources without a `generate.resource_plan`.
- `main.py` creates or scans I2C when manifest has no I2C device.
- `main.py` assigns I2C SCL/SDA to GPIO already assigned to non-I2C peripherals in `pinout[]`.
- Cloud provider choice, official setup links, credential status, or deploy readiness missing when firmware uses external APIs.
- Hard-coded API keys, tokens, access keys, passwords, authorization headers, or provider secrets in generated files.
- Blocking final review findings.
- Missing or invalid `session_state.upy_generate_plugin.json` checkpoint/resume state.
- Missing `session_state` `manifest_hash`, `git_commit`, or `usage` fields; completed `phase_completed` state without a real manifest hash or git commit.
- Completed `session_state` without resumable `artifacts` and `last_ok_artifact`.
- `manifest_hash` copied from `git_commit`, or any `manifest_hash` that does not match SHA256 of `project-manifest.json`.
- `phase_complete.payload.generate.git.commit` or disk `session_state.git_commit` does not match final project HEAD.
- `manifest_content.generate.git.commit` present without `commit_role`; use `code_commit` or declare that it is an earlier code-generation commit, not final HEAD.
- `project-manifest.json` with `phase=generate` but stale `domain_phase=scaffold` or `final_status=scaffolded`.
- Project tree, file manifest, or git commit contains CPython cache files (`__pycache__/` or `*.pyc`).

## Warn-Only Gates

These should be warnings unless the project explicitly requires deploy readiness:

- pylint warning/refactor/convention-only exit bits when there are no fatal/error/usage bits.
- Third-party `firmware/lib` import risks.
- Third-party `firmware/lib` style issues.
- Reserved scaffold config unused.
- Optional diagram/wiring phase unavailable.
- Cloud service catalog entry is unknown but the generated manifest still includes explicit official links and a safe credential plan.

## .pylintrc Baseline

Use `scripts/ensure_pylintrc.py` to create project `.pylintrc` when absent. The config should ignore MicroPython import noise but still check generated business code.

Run quality gates with `PYTHONDONTWRITEBYTECODE=1`, compile generated Python to temporary `.pyc` targets, and use `pylint --persistent=n`. Before committing, remove project-local `__pycache__/` and `*.pyc`; generated file manifests and git commits must not include them.

## Pylint Scope

Run pylint as a strong gate on generate-owned runtime code:

```text
firmware/main.py
firmware/drivers/**/*.py
firmware/tasks/*.py except scaffold maintenance helpers
```

Do not use scaffold framework libraries or downloaded third-party `firmware/lib` style warnings as a strong generate gate. They are covered by compile/import-risk checks instead.

## Pylint Exit Policy

Pylint uses a bitmask return code:

| Bit | Meaning | Default gate |
|---|---|---|
| 1 | fatal | fail |
| 2 | error | fail |
| 4 | warning | warn |
| 8 | refactor | warn |
| 16 | convention | warn |
| 32 | usage error | fail |

Default generate policy is `fail_on_fatal_error_usage`. For example, return code `12` means warning + refactor and is warning-only when `ok=true`. Use `run_quality_gates.py --strict-pylint` only when the project deliberately wants all pylint messages to block.

## MicroPython Import Policy

`check_mpy_imports.py` fails direct CPython-only runtime imports such as `asyncio`, `typing`, `dataclasses`, `pathlib`, and `logging`.

Allowed PC compatibility fallback pattern:

```python
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
```

The fallback import is warning-only when it is inside an `except ImportError` or `except ModuleNotFoundError` handler and the corresponding MicroPython module was imported in the `try` body. Direct `import asyncio` outside that pattern remains a strong failure.

CPython-only branches guarded by `_IS_MICROPYTHON` are warning-only as `MPY_IMPORT_CPYTHON_ONLY_GUARD` when the import is unreachable on MicroPython, for example scaffold `rotating_logger.py` importing CPython `logging` only in the non-MicroPython branch. Direct runtime `import logging` remains a strong failure.

## Official Documentation Evidence

Hardware/peripheral API evidence must be exact enough for the generated API surface.

- For specific MicroPython classes such as `machine.Timer`, `machine.Pin`, `machine.I2S`, `network.WLAN`, and `neopixel`, cite the corresponding specific MicroPython official page when `knowledge/micropython_official_library_index.json` has one.
- A parent page such as `machine` is not sufficient for a specific class when the index has a dedicated page.
- If the index entry only points to CPython docs or the MicroPython page has no substantive content, treat it as insufficient evidence and add a port-specific MicroPython source or emit `partial`.
- Record evidence in `manifest_content.generate.doc_evidence[]` with `module`, official `url`, and `reason`.

## phase_complete Recording

Record quality gates in:

```json
{
  "lint": {
    "flake8": {"returncode": 0},
    "pylint": {"returncode": 12, "ok": true, "policy": "fail_on_fatal_error_usage"}
  },
  "tests": {
    "pc_unittest": {"returncode": 0}
  },
  "checks": {
    "py_compile": {"returncode": 0},
    "generate_plan": {"returncode": 0},
    "conf_contract": {"returncode": 0},
    "driver_source_compile": {"returncode": 0},
    "mpy_imports": {"returncode": 0},
    "mpy_imports_lib": {"returncode": 0},
    "dead_config": {"returncode": 0},
    "task_no_machine_import": {"returncode": 0},
    "device_unittest_subset": {"returncode": 0},
    "runtime_dependencies": {"returncode": 0},
    "doc_evidence": {"returncode": 0},
    "skeleton_compliance": {"returncode": 0},
    "generated_semantics": {"returncode": 0},
    "cloud_integrations": {"returncode": 0},
    "session_state_checkpoint": {"returncode": 0, "ok": true}
  }
}
```

## Success Consistency

Before emitting `phase_complete.result=success`, validate the complete event with:

```bash
python scripts/check_phase_complete_consistency.py --phase-complete <phase_complete> --project-dir <project_root>
```

When the upstream scaffold/select-hw/flash phase_complete is known, pass it explicitly:

```bash
python scripts/check_phase_complete_consistency.py --phase-complete <phase_complete> --project-dir <project_root> --upstream-phase-complete <session_root>/phase_complete.upy_scaffold_plugin.json
```

The checker treats upstream `mcu`, `board`, `devices`, and `pinout` as immutable hardware facts for generate. If the user adds or replaces hardware during generate, emit `partial` with `next_phase=null` and route back to analyze/select-hw/scaffold. If scaffold incremental has already produced the updated manifest with `incremental=true` and `generate_scope=new_devices_only`, use that incremental scaffold phase_complete as the upstream baseline.

For end-to-end plugin runs, validate the whole session before treating the workflow as formally complete:

```bash
python shared-plugin-scripts/workflow/session_chain_validate.py --session-dir <session_root> --require-deploy
```

This catches cross-skill failures that individual gates cannot see: mixed workflow/diagnostic sessions, stale generate git commits, invalid deploy phase_complete schema, and transient project-root artifacts such as a file named `-`.

Success is invalid when any strong gate is failed, `structured_errors` is non-empty, final review has blocking findings, `manifest_content` is a thin summary, or `project/project-manifest.json` still has `phase=scaffold`. The plugin must update `project-manifest.json` to `phase=generate`, include the full updated manifest in `payload.manifest_content`, and include `project-manifest.json` in `file_manifest.files`.

`payload.manifest_content` must preserve upstream `requirements`, non-empty `devices`, `mcu`, `pinout`, and scaffold context. `generate` is an added section, not a replacement for the full project manifest.

Success also requires:

- `lint.pylint.returncode` is an integer from a real pylint run. `returncode=null`, `skipped_no_pylintrc`, or any skipped pylint status is invalid. Always run `ensure_pylintrc.py` first.
- `file_manifest.files` includes `generate_plan.json` with role `plan`.
- `checks.session_state_checkpoint.ok=true`, `file_manifest.files` includes `session_state.upy_generate_plugin.json` with role `artifact`, and `artifacts[]` includes a `session_state` entry.
- `checks.session_state_checkpoint.state` includes `manifest_hash`, `git_commit`, and `usage`; completed success must not leave `manifest_hash="unknown"` or `git_commit=null`.
- `checks.session_state_checkpoint.state` includes non-empty `artifacts` and `last_ok_artifact` for completed success.
- `payload.artifacts[]` includes both `type=session_state` and `type=file_manifest`.
- `manifest_hash` is the SHA256 of `project-manifest.json`; it must not be the git commit.
- `payload.generate.git.commit` and disk `session_state.git_commit` match `git rev-parse HEAD`.
- `optional_next_phases` offers `upy-diagram-plugin` and `upy-wiring-plugin`.
- `manifest_content.generate.deploy_plan.source_only` keeps `firmware/main.py`, `firmware/boot.py`, and `firmware/conf.py` as source uploads, and `upload_exclude` excludes `firmware/drivers/**/mock.py` plus stale `firmware/drivers/**/mock.mpy`.
- A completed git commit is recorded in `payload.generate.git.commit`, with a matching approved git permission record. If commit permission is denied, unavailable, or the project is not a git repository and cannot be initialized, emit `partial` with `next_phase=null`.
- `next_phase=upy-deploy-plugin` means code generation is clean enough to hand off. If cloud services are `mock_only`, provider setup is blocked, or deploy blockers remain, route to `upy-simulate-plugin` or `null`.
