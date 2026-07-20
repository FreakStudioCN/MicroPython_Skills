---
name: mpos-plan-app
description: Orchestrate a MicroPythonOS App workflow across analyze, dependency preparation, generation, testing, packaging, deployment, and upystore publishing. Use when Codex needs to start from a natural-language app request, continue or resume an interrupted MPOS app task, decide the next mpos-* skill, maintain per-app plan_state.json and activity_log.jsonl under tmp/mpos-plan-app, handle user requirement changes with invalidation confirmation, or run the default path through mpos-publish-app. Does not implement code, download dependencies, test, package, deploy, flash, or upload directly.
---

# MicroPythonOS App Planner

## Role

Act as the conversational entry point and state machine for one MicroPythonOS App. Keep the project state current, route to phase skills, and make resumption deterministic.

Do not do downstream work directly. Use the phase skills:

- `mpos-analyze-app`
- `mpos-prepare-deps`
- `mpos-gen-app`
- `mpos-test-app`
- `mpos-package-app`
- `mpos-deploy-app`
- `mpos-publish-app`

`mpos-gen-app` remains strictly two-phase. This skill must not bypass its write confirmation.

## User-Facing Language

Follow `mpos-dev` language continuity: if the workflow starts in Chinese, keep user-facing planning, questions, and summaries in Chinese; if it starts in English, keep them in English. Keep code, commands, paths, API names, and JSON keys in English.

## Unified Project Log

Before writing any artifact, determine the active MicroPythonOS repository root:

- If the user gives a repository path, use that path as `<repo-root>`.
- Otherwise, use the current working directory when it contains `internal_filesystem/apps` and `scripts`.
- Never fall back to `/home/leeqingshui/MicroPythonOS` when the user is testing in an isolated clone, worktree, or temporary copy.
- For build, simulator, desktop-preview, web-preview, or integration-test operations, prefer an isolated clone/worktree/temporary copy. Do not mutate the user's main MicroPythonOS checkout unless the user explicitly allows it.

At workflow start and resume time, read `mpos-dev/reference/mpos_api_summary.json` and `mpos-dev/reference/lvgl_api_summary.json` completely. Every mpos-* phase depends on these references; do not skip them because the next phase looks simple.

Every MPOS app project uses:

```text
<repo-root>/tmp/mpos-plan-app/<fullname>/
  plan_state.json
  activity_log.jsonl
```

All mpos-* phase skills should append a concise event after producing a phase result. Use:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill <mpos-skill-name> \
  --phase <phase> \
  --result <success|partial|failed|blocked|planned> \
  --artifact <kind>=<path> \
  --next-skill <next-skill-or-null> \
  --event "<short summary>"
```

Do not hand-write `plan_state.json` or `activity_log.jsonl`. Always call `update_plan_state.py record`, `discover`, or `invalidate` so the state uses schema `mpos-plan-app-v1`. After creating or updating state, run `validate_plan_state.py` on `<repo-root>/tmp/mpos-plan-app/<fullname>/plan_state.json`.

Common artifact keys:

- `analysis_result`
- `dependency_handoff`
- `generation_result`
- `app_test_result`
- `package_result`
- `deploy_result`
- `publish_result`

If `fullname` is unknown, discover the most recent project:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py discover \
  --repo <repo-root>
```

When auto-selecting, tell the user which App was selected and why. If multiple plausible candidates are close in time or the user intent conflicts, ask before continuing.

## Default Workflow

Default goal is from request to upystore publishing handoff:

1. `mpos-analyze-app`
2. `mpos-prepare-deps`, only if external app-layer dependencies are needed
3. `mpos-gen-app plan`
4. wait for user confirmation, then `mpos-gen-app create/update/repair`
5. `mpos-test-app`
6. if App-owned test failure occurs, return to `mpos-gen-app repair`, then test again
7. `mpos-package-app`
8. `mpos-deploy-app`
9. `mpos-publish-app`

Before step 8, ask whether a physical device and serial port are available and whether MicroPythonOS is already installed on that device. If yes, route deploy toward `mpk-install` for release verification unless the user chooses another device mode; if MPOS runtime probing fails but filesystem copy is acceptable, route to `device-copy`. If no physical board exists, a `desktop-preview` or `web-preview` `deploy_result.json` is enough to satisfy the publish-chain deployment record, and the result must record `hardware_available=false`.

## Resumption

For "continue", "resume", "next step", or after context loss:

1. Locate `plan_state.json` by fullname if provided.
2. If fullname is absent, run `update_plan_state.py discover`.
3. Read the latest phase artifacts referenced by `plan_state.json`.
4. Validate result states:
   - `success`: continue.
   - `partial`: continue with warnings unless the target phase requires success.
   - `failed`: route according to the failing artifact's `handoff.next_skill`.
5. Compare `plan_state.artifact_status[*].result` with the actual artifact file's current `result`. If the JSON was edited after the last record event, trust the actual artifact and immediately call `update_plan_state.py record` again before routing.
6. If the state is stale or missing, reconstruct it from `tmp/mpos-*/*/*.json`, then record a `mpos-plan-app` resume event.

Do not restart from analyze when enough trustworthy artifacts exist.

## Requirement Changes

When the user changes requirements, first list the invalidation scope and ask for confirmation. Do not modify files or delete artifacts before the user confirms the invalidation.

Suggested invalidation scopes:

- UI copy/layout only: invalidate `generation_result`, `app_test_result`, `package_result`, `deploy_result`, `publish_result`.
- App behavior or feature logic: invalidate `generation_result`, `app_test_result`, `package_result`, `deploy_result`, `publish_result`.
- Dependency, hardware, protocol, or async behavior: invalidate `analysis_result` if feature meaning changed, plus `dependency_handoff`, `generation_result`, `app_test_result`, `package_result`, `deploy_result`, `publish_result`.
- App fullname/name identity: treat as a new project unless the user explicitly wants a rename migration.
- Version or store metadata only: usually invalidate `package_result` and `publish_result`; do not retest unless code or manifest changed.
- Test failure caused by App code: route to `mpos-gen-app repair`; do not bump version by default.
- Manual App file edits: mark downstream artifacts stale and rerun `mpos-gen-app` validation and `mpos-test-app`.

Record a proposed invalidation with:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py invalidate \
  --repo <repo-root> \
  --fullname <fullname> \
  --reason "<why artifacts are stale>" \
  --scope generation_result \
  --scope app_test_result \
  --scope package_result
```

After the user confirms, rerun the command with `--confirmed` and continue to the right upstream phase.

## Routing Rules

- Vague or new app request: `mpos-analyze-app`.
- Clear app request with external dependency gap: `mpos-prepare-deps`.
- Requirements and dependency handoff ready: `mpos-gen-app`.
- Generated code ready: `mpos-test-app`.
- Runtime smoke failed from App code: `mpos-gen-app repair`.
- Runtime smoke blocked by OS/tooling: report blocked; do not ask `mpos-gen-app` to edit App code.
- Test success and publish goal active: `mpos-package-app`.
- Package success or partial with warnings: ask the physical device/serial-port question, then route to `mpos-deploy-app` for preview/deploy record.
- Deploy preview or device install result available and publish goal active: `mpos-publish-app`.
- User only asks to deploy, package, test, or publish: route directly to the named phase but still update `plan_state.json`.

## Output

When acting as planner, always report:

- selected `fullname`
- current phase
- artifacts found
- stale artifacts, if any
- next skill and why
- blocking questions, if any
- project log path

Validate state with:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/validate_plan_state.py \
  <repo-root>/tmp/mpos-plan-app/<fullname>/plan_state.json
```
