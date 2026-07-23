# Capability Negotiation

The backend host must pass capabilities. The skill must adapt instead of assuming tools exist.

Example:

```json
{
  "capabilities": {
    "file_operation": true,
    "script_run": true,
    "approval_request": true,
    "permission_request": true,
    "checkpoint_resume": true,
    "cancellation": true,
    "retry": true,
    "timeout": true,
    "desktop_preview": true,
    "web_preview": true,
    "physical_device": false,
    "serial_port_scan": false,
    "mpremote": true,
    "firmware_flash": false,
    "network_read": true,
    "network_upload": false
  }
}
```

Rules:

- If `file_operation=false`, emit planned writes as artifacts or file operations for the host; do not write directly.
- If `script_run=false`, emit command plans and block required script phases with structured errors.
- If `physical_device=false`, do not claim hardware validation.
- If `web_preview=false`, skip Web preview with a warning.
- If `network_read=false`, skip upystore version comparison and mark it `unknown_unverified`.
- If `network_upload=false`, never upload; current publish skill is manual guidance only.
