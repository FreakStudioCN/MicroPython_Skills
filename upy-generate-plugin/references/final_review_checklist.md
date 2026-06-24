# Final Review Checklist

Use this checklist after scripts pass and before git commit.

## Driver API

- Read each downloaded driver source file.
- Confirm factory imports the correct module/class.
- Confirm constructor arguments match the driver source.
- Confirm default I2C address comes from source, README, or example.
- Confirm each task-called public method exists in the real driver.
- Confirm mock method names and signatures match task usage and real driver behavior.
- Confirm self-created I2C drivers were patched only when needed.

## Requirements Coverage

- Every user requirement has a corresponding task or explicit documented omission.
- Every output device in manifest has a task or main wiring.
- Every network behavior has retry/failure logging.
- User-provided behavior details are reflected in `conf.py` and tasks.

## GPIO/SPI/I2C Hardware

- GPIO-only devices have on/off/toggle/value or equivalent API.
- I2C devices have scan helpers when passive scan is meaningful.
- SPI devices handle chip select correctly.
- No pinout changes were made in generate.

## Logging

- Critical runtime events are double-written with `print` and `lib.logger`.
- Logs include module prefixes.
- `main.py` installs rotating logs when scaffold logger exists.
- Startup logs include project and board identity.

## Config

- No secrets in `conf.py`.
- No hardcoded thresholds in tasks/main.
- No generated business config is dead.

## Cloud/API Services

- Every LLM/ASR/TTS/IoT/MQTT/Webhook/third-party REST API has a `generate.cloud_integrations[]` entry.
- User-facing setup prompts include official docs/product, console, and pricing/billing links when known.
- Credential status is explicit: `ready`, `deferred_to_deploy`, `mock_only`, `not_required`, or `blocked`.
- Real API keys, tokens, AK/SK, passwords, webhook secrets, and Bearer values are not present in firmware, tests, logs, `phase_complete`, or git.
- Complex provider signing, OAuth, token exchange, or account-level secrets use `custom_http_proxy` unless the user explicitly accepts direct device credentials.
- `next_phase=upy-deploy-plugin` is used only when cloud setup is ready, deferred to a deploy permission prompt, or not required. `mock_only` routes to simulate/null.

## Tests

- PC tests use `unittest`.
- PC tests cover normal, missing device, and driver exception cases.
- Device tests use only MicroPython unittest subset.
- PC tests run successfully before commit.

## MicroPython Compatibility

- Business firmware imports only MicroPython-compatible modules or project local modules.
- `async` firmware uses `uasyncio`, not CPython `asyncio`.
- No `typing`, `dataclasses`, `pathlib`, or CPython `logging` in firmware runtime.
- External `firmware/lib` risks are recorded.

## Result Decision

Emit `success` only when all strong gates and checklist items pass. Otherwise emit `partial` or `failed` with structured errors and `next_phase=null`.

Before success/git commit, confirm the project tree, `file_manifest`, artifacts, and git HEAD contain no CPython cache files (`__pycache__/` or `*.pyc`).
