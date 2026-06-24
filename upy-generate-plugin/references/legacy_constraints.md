# Legacy Generate Constraints

This reference preserves the key rules from `G:\MicroPython_Skills\upy-generate\SKILL.md`. Apply these rules when generating full code or fix diffs.

## Core Philosophy

Generated firmware must follow unit-test-centered embedded development:

- Hardware and software must be decoupled.
- Except for `firmware/main.py` and hardware factory/adapters, business files must not import `machine`.
- Drivers are created by factory functions and injected into task functions.
- Real drivers and mocks expose compatible duck-typed APIs.
- PC tests in `test/pc/` must run under CPython without hardware.
- `firmware/lib/logger`, `firmware/lib/time_helper`, scheduler, and maintenance helpers should provide or preserve CPython fallbacks.
- Each task must be testable with normal data, missing device (`None`), and driver exception scenarios.

## Generation Order

Use this order in full mode:

1. Read scaffold phase_complete and project files.
2. Confirm user behavior details and next phase preference.
3. Resolve driver and middleware dependencies.
4. Download files as JSON and write them under `firmware/lib`.
5. Read driver source, README, example, and metadata.
6. Analyze driver API before writing factory/mock/task code.
7. Generate factory adapters under `firmware/drivers/<name>_driver/`.
8. Generate mock classes under the same driver package.
9. Generate task files under `firmware/tasks/`.
10. Update `firmware/conf.py`.
11. Update `firmware/main.py` for DI and scheduling.
12. Generate `test/pc/` and `test/device/`.
13. Run quality gates.
14. Perform final review checklist.
15. Git commit.
16. Emit phase_complete.

## Hard Architectural Rules

- Do not modify pinout or board selection in generate.
- Do not silently change `firmware/board.py`; report a structured error if pinout is impossible.
- Do not write Wi-Fi passwords, API keys, tokens, or secrets into `conf.py`.
- Do not generate a global `firmware/mock/` directory.
- Do not hardcode business thresholds in tasks or `main.py`; put them in `conf.py`.
- Do not treat downloaded third-party driver style issues as business-code failures; compile and import-risk scan them separately.
- Do not output deploy-ready success when required drivers are missing.
- Do not skip git commit after successful full/fix generation unless permission is denied; permission denial means `partial`, not deploy-ready success.

## Logging Requirements

Use module prefixes in messages, for example `[sensor]`, `[display]`, `[alarm]`, `[network]`, `[driver]`, `[main]`.

Always double-write user-visible runtime events:

```python
from lib.logger import info, warning, error, debug

msg = "[sensor] AHT20 temperature=25.2 humidity=61.0"
debug(msg)
print(msg)
```

`print()` is for live REPL/mpremote visibility. `lib.logger` is for device-side rotating logs. Do not rely on only one for critical events.

## Allowed File Responsibilities

| File/dir | Responsibility |
|---|---|
| `firmware/board.py` | Pin constants and query helpers only. No hardware instantiation. |
| `firmware/conf.py` | Non-secret constants, thresholds, intervals, logging config. |
| `firmware/main.py` | Hardware instantiation, DI, scheduling, logger setup. |
| `firmware/drivers/*_driver/__init__.py` | Factory and hardware connectivity helpers. |
| `firmware/drivers/*_driver/mock.py` | Mock class with API matching the real driver. |
| `firmware/tasks/*.py` | Business logic; no direct hardware construction. |
| `firmware/lib/*` | Downloaded drivers and scaffold-provided libraries. |
| `test/pc/*` | CPython unittest tests. |
| `test/device/*` | MicroPython smoke tests for hardware connectivity. |

## Fix Mode Rules

In fix mode:

- Read `error_context`, generated files, manifest, `generate_fix_history.json`, and previous attempts.
- Make the smallest possible change.
- Preserve pinout and scaffold mode.
- Rerun all quality gates.
- Commit successful fixes.
- Record changed files, code diff, attempts, quality result, and knowledge refs.
