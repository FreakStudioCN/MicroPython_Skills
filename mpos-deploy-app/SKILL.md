---
name: mpos-deploy-app
description: Deploy or preview a MicroPythonOS app on desktop, web, device copy, MPK install, or installer/flash guidance paths. Use when Codex needs to launch a confirmed app for manual preview, copy it to a board with mpremote, validate an MPK on-device, or route firmware install and erase to install.micropythonos.com. Does not own app generation, static lint, packaging, or default smoke testing.
---

# MicroPythonOS App Deploy

## Role

Orchestrate one deployment or preview target for one confirmed MicroPythonOS App. This skill is reentrant: run it again when the user changes board, port, install mode, or asks to retry after failure.

## Unified Project Log

After any preview/deploy path writes `deploy_result.json`, record it in the shared project state:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill mpos-deploy-app \
  --phase deploy \
  --result <success|partial|failed|blocked> \
  --artifact deploy_result=<deploy_result.json> \
  --next-skill <handoff.next_skill-or-null> \
  --event "Recorded deploy or preview result"
```

For publish flow without physical hardware, `desktop-preview` or `web-preview` is an acceptable deploy record. Device copy or `mpk-install` remains preferred when hardware is available.

## Read first

- `mpos-dev/reference/docs-deploy-targets.md`
- `mpos-dev/reference/docs-web-port.md`
- `mpos-dev/reference/docs-packaging.md`
- `<repo-root>/AGENTS.md`
- `<repo-root>/internal_filesystem/lib/mpos/content/app_manager.py`
- `<repo-root>/internal_filesystem/lib/mpos/content/streaming_unzip.py`
- `<repo-root>/scripts/run_desktop.sh`
- `<repo-root>/scripts/run_web.sh`
- `<repo-root>/scripts/install.sh`
- `<repo-root>/scripts/flash_over_usb.sh`
- `<repo-root>/scripts/mpos_controller.py`

## Default flow

1. Confirm the target mode first. Do not assume desktop, web, device copy, MPK install, install-site guidance, or local flash.
2. For any device or flash path, explicitly confirm the board model and serial port before doing anything. Do not reuse stale board state.
3. If the user wants firmware install or erase, route them to `https://install.micropythonos.com/` by default. That site can identify supported boards itself; local flash is only allowed when the user explicitly says `允许本机执行 flash`.
4. Desktop launch is preview only. Do not treat it as a smoke-test gate or a replacement for `mpos-test-app`.
   Use `scripts/launch_desktop_preview.py` or `scripts/run_desktop.sh` for the manual launch path.
5. Web preview should serve existing `web/` artifacts with `scripts/run_web.sh --no-build`. If artifacts are missing, pause and ask whether to build.
6. Device install has two paths: direct app copy with `mpremote` or `mpos_controller.py installapp`, or MPK install by uploading the MPK to the device and calling `AppManager.install_mpk()`. Prefer MPK install for release verification.
7. Always write `deploy_result.json` and validate it before handing off.

## Modes

- `desktop-preview`
- `web-preview`
- `device-copy`
- `mpk-install`
- `install-site`
- `local-flash`

## Helper scripts

- `scripts/detect_device.py`
- `scripts/launch_desktop_preview.py`
- `scripts/deploy_app_copy.py`
- `scripts/deploy_mpk_install.py`
- `scripts/serve_web_preview.py`
- `scripts/validate_deploy_result.py`

## Output

Use `templates/deploy_result.json` as the shape. Record the chosen mode, board, port, command, result, warnings, artifacts, and next step.

Validate with:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-deploy-app/scripts/validate_deploy_result.py \
  <deploy_result.json>
```

## Rules

- Do not modify MicroPythonOS OS/build source.
- Do not run desktop smoke assertions here.
- Do not login or upload anywhere.
- Do not auto-build web artifacts unless the user confirms.
- Do not local-flash or erase unless the user explicitly allowed it.
- Use the built-in MicroPythonOS tools only.
