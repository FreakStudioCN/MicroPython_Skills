---
name: mpos-deploy-app
description: Deploy or preview a MicroPythonOS app on desktop, web, device copy, MPK install, or installer/flash guidance paths. Use when Codex needs to launch a confirmed app for manual preview, copy it to a board with mpremote, validate an MPK on-device, or route firmware install and erase to install.micropythonos.com. Does not own app generation, static lint, packaging, or default smoke testing.
---

# MicroPythonOS App Deploy

## Role

Orchestrate one deployment or preview target for one confirmed MicroPythonOS App. This skill is reentrant: run it again when the user changes board, port, install mode, or asks to retry after failure.

## User-Facing Language

Follow `mpos-dev` language continuity: if the workflow starts in Chinese, keep deploy summaries, warnings, questions, and next steps in Chinese; if it starts in English, keep them in English. Keep code, commands, paths, API names, and JSON keys in English.

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

For publish flow without physical hardware, `desktop-preview` or `web-preview` is an acceptable deploy record only after the user confirms no physical device/serial port is available. Device copy or `mpk-install` remains preferred when hardware is available.

## Read first

- `mpos-dev/reference/mpos_api_summary.json`
- `mpos-dev/reference/lvgl_api_summary.json`
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

Read the two API summary JSON files completely even for preview/deploy-only work. They are required shared context for MPOS App identity, AppManager/install semantics, and avoiding stale API assumptions.

## Default flow

1. Before every deploy run, ask whether a physical device and serial port are available. Do not silently choose desktop or web preview.
2. Confirm the target mode first. Do not assume desktop, web, device copy, MPK install, install-site guidance, or local flash.
3. For any device or flash path, explicitly confirm the board model, serial port, and whether MicroPythonOS is already installed. Do not reuse stale board state.
4. If MicroPythonOS is not installed or the user is unsure, route them to `https://install.micropythonos.com/` first. That site can identify supported ESP32/ESP32-S3 boards itself; local flash is only allowed when the user explicitly says `允许本机执行 flash`.
5. Desktop launch is preview only. Do not treat it as a smoke-test gate or a replacement for `mpos-test-app`.
   Use `scripts/launch_desktop_preview.py` or `scripts/run_desktop.sh` for the manual launch path.
6. Web preview should serve existing `web/` artifacts with `scripts/run_web.sh --no-build`. If artifacts are missing, pause and ask whether to build.
7. Device install has two paths:
   - `device-copy`: primary recovery/iteration path. Use direct `mpremote connect <port> fs cp -r <app_dir> :/apps/` and verify `:/apps/<fullname>`. This path can succeed even when `mpos_controller.py` / AIOREPL probing fails, but it only proves filesystem deployment unless MPOS runtime is later verified.
   - `mpk-install`: release-verification path. Upload the MPK and call `AppManager.install_mpk()` only after the target can import `mpos` and the runtime probe succeeds.
8. Always write `deploy_result.json` and validate it before handing off. Use `--output-dir` only for directories; never pass a `deploy_result.json` file path as `--output-dir`.
9. In the publish chain, successful or partial deploy/preview records normally hand off to `mpos-publish-app`; do not send the user back to `mpos-test-app` unless they explicitly ask for another runtime smoke check.

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

Typical physical App copy command:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-deploy-app/scripts/deploy_app_copy.py \
  --repo <repo-root> \
  --app-fullname <fullname> \
  --board <board> \
  --serial-port <port>
```

Typical MPK install command, only when MicroPythonOS runtime probing succeeds:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-deploy-app/scripts/deploy_mpk_install.py \
  --repo <repo-root> \
  --app-fullname <fullname> \
  --mpk-path <repo-root>/tmp/mpos-package-app/<fullname>/<fullname>_r1.mpk \
  --board <board> \
  --serial-port <port>
```

## Output

Use `templates/deploy_result.json` as the shape. Record the chosen mode, `hardware_available`, board, port, command, result, warnings, artifacts, and next step. For preview-only modes set `hardware_available=false`; for device or flash modes set it to `true`.

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
- Do not accept `desktop-preview` or `web-preview` as the deploy record until the user confirms no physical device/serial port is available.
- Use the built-in MicroPythonOS tools only.
