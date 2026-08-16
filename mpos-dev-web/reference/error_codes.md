# Structured Errors

All phases emit structured errors in this shape:

```json
{
  "code": "LVGL_API_MISSING",
  "message": "lv.obj.set_style_row_gap is not in lvgl_api_summary.json",
  "stage": "generation",
  "phase": "mpos-gen-app-web",
  "owner": "app",
  "retryable": true,
  "details": {},
  "logs": []
}
```

`owner` values: `app`, `skill`, `backend`, `frontend`, `toolchain`, `micropythonos`, `device`, `external`, `user`.

Core error codes:

| Code | Owner | Retryable | Meaning |
|---|---|---|---|
| `MISSING_FIELD` | user | true | Required request or manifest field is missing |
| `INVALID_PROTOCOL_VERSION` | backend | false | Unsupported `protocol_version` |
| `INVALID_PHASE_INPUT` | backend | true | Input JSON does not match phase contract |
| `MPOS_NOT_FOUND` | backend | true | `repo_root` is missing or not MicroPythonOS |
| `MPOS_NOT_INSTALLED_ON_DEVICE` | device | true | Physical target does not have MicroPythonOS installed |
| `LVGL_API_MISSING` | app | true | Generated LVGL call is not in summary/current source evidence |
| `MPOS_API_MISSING` | app | true | Generated MPOS call is not in summary/current source evidence |
| `MPOS_CAPABILITY_API_MISSING` | micropythonos | false | Hardware may exist, but current MPOS has no portable App-level capability API |
| `DIRECT_HARDWARE_ACCESS_FORBIDDEN` | skill | true | Generated App bypasses MPOS with a board import, GPIO/bus constructor, or board-specific driver |
| `HARDWARE_CAPABILITY_UNAVAILABLE` | device | false | A valid portable App ran on a device that does not expose a required capability |
| `WIDGET_ZERO_REFERENCE` | app | true | Widget has no existing App usage in current repo |
| `MANIFEST_MISSING_FIELD` | app | true | `MANIFEST.JSON` lacks required metadata such as `publisher` |
| `MPK_RELEASE_NAME_INVALID` | app | true | MPK filename does not use `<fullname>_rN.mpk` |
| `DESKTOP_RUNNER_SEGFAULT` | micropythonos | true | Desktop binary crashed independent of target App |
| `WEB_PREVIEW_UNSUPPORTED` | external | false | Requested feature cannot run in browser Web port |
| `WEB_PREVIEW_BUILD_FAILED` | toolchain | true | Web target build failed |
| `DEVICE_NOT_CONNECTED` | device | true | Serial device unavailable |
| `DEVICE_PROBE_FAILED` | device | true | Probe failed; may still allow `device-copy` if mpremote works |
| `DEVICE_DEPLOY_FAILED` | device | true | App copy or MPK install failed |
| `SCRIPT_TIMEOUT` | toolchain | true | Script exceeded timeout |
| `PERMISSION_DENIED` | user | true | User denied a required operation |
| `USER_CANCELLED` | user | false | User cancelled the session or phase |
| `TOOLCHAIN_MISSING` | toolchain | true | Missing `uv`, `ruff`, `mpy-cross`, `emcc`, etc. |
| `EXTERNAL_OS_BLOCKED` | micropythonos | false | Failure is in OS/framework/tooling outside App scope |

Never return only a free-form error string. Preserve stdout/stderr excerpts, command, cwd, return code, and artifact paths when available.
