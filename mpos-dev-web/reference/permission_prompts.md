# Permission Prompts

Browser workflows must request permission before file, script, device, flash, or upload operations.

Permission request shape:

```json
{
  "type": "permission_request",
  "phase": "mpos-deploy-app-web",
  "session_id": "sess_20260723_001",
  "payload": {
    "permission_id": "perm_device_copy_001",
    "permission_type": "device_write",
    "title": "Deploy App to ESP32-S3 device",
    "description": "Copy the generated App to /apps on /dev/ttyACM0 using mpremote.",
    "risk": "medium",
    "required": true,
    "command_preview": "mpremote connect /dev/ttyACM0 fs cp -r app :/apps/",
    "artifact_paths": [],
    "choices": ["allow_once", "deny"]
  }
}
```

Permission types:

```text
file_write
file_overwrite
script_run
dependency_install
desktop_launch
web_build
web_serve
serial_scan
device_read
device_write
microphone_access
destructive_storage
external_hardware_wiring
firmware_flash
network_read
network_upload
cleanup
```

Rules:

- Request permission before executing the operation.
- Include a clear command or action preview when possible.
- Do not ask for API keys or store credentials in artifacts.
- If denied, emit `PERMISSION_DENIED` and preserve session state.
- Firmware flash and erase require explicit user confirmation; no default allow.
- Microphone capture/recording requires `microphone_access`, even when the browser has already granted its own media permission.
- SD format, filesystem erase, and similar destructive operations require `destructive_storage`; mounting or reading must not imply format permission.
- Direct GPIO/bus access for an explicit external accessory requires `external_hardware_wiring` after the wiring and conflict plan is shown. This permission is never valid for silently bypassing an onboard MPOS manager.
