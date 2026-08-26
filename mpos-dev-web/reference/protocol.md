# Browser Workflow Protocol

Use this protocol for all `mpos-*-web` skills. It is compatible with a browser frontend and backend runner; it is not the same interface as `/mpos-gen-app ...` in Claude Code.

## Message Envelope

All messages use this envelope:

```json
{
  "protocol_version": "mpos-ai-app/v1",
  "type": "start_phase",
  "phase": "mpos-gen-app-web",
  "session_id": "sess_20260723_001",
  "checkpoint_id": "requirements_analyzed",
  "idempotency_key": "mpos-gen-app-web:sess_20260723_001:attempt-1",
  "timestamp": "2026-07-23T12:00:00Z",
  "payload": {}
}
```

Required fields:

- `protocol_version`: use `mpos-ai-app/v1` until a breaking schema change is made.
- `type`: one of `start_phase`, `status_update`, `approval_request`, `permission_request`, `file_operation`, `script_run`, `device_command`, `artifact_manifest`, `structured_error`, `phase_complete`, `cancel`, `retry`, `resume`.
- `phase`: exact skill name, for example `mpos-package-app-web`.
- `session_id`: stable browser workflow identifier.
- `idempotency_key`: stable per requested action; reuse it for retries of the same user action.
- `payload`: phase-specific object.

## Runtime Context

Every `start_phase` payload must include:

```json
{
  "runtime_context": {
    "session_root": "sessions/<session_id>",
    "project_root": "sessions/<session_id>/project",
    "artifact_root": "sessions/<session_id>/artifacts",
    "repo_root": "vendor/MicroPythonOS",
    "skills_root": "vendor/MicroPython_Skills",
    "file_operation_root": "sessions/<session_id>/project",
    "resource_root": "vendor/MicroPython_Skills/mpos-gen-app-web"
  }
}
```

Do not infer these paths from host-specific absolute paths when the runner provides them.

## Binary File Operations

When the host applies files instead of allowing direct project writes, binary App assets use an explicit encoding and role:

```json
{
  "type": "file_operation",
  "phase": "mpos-gen-app-web",
  "session_id": "sess_20260723_001",
  "payload": {
    "operation": "write_binary",
    "path": "internal_filesystem/apps/com.example.game/assets/images/player_ship.bin",
    "encoding": "base64",
    "content_base64": "...",
    "mime": "application/octet-stream",
    "role": "app_runtime_image",
    "sha256": "..."
  }
}
```

The host validates the decoded byte length and SHA-256, rejects absolute paths and `..`, and writes only below `runtime_context.file_operation_root`. Prefer registering a runtime file already produced by a whitelisted script instead of copying a large base64 payload through multiple protocol messages.

## Web Image Acquisition

For `generation_mode=web`, the host owns search and download. The model emits a search query and selection criteria, not a command, credential, request header, or unvalidated URL fetch. After `network_read` permission, record the selected source before conversion:

```json
{
  "schema_version": "mpos-visual-asset-source-v1",
  "asset_id": "named_character",
  "search_query": "official named character transparent artwork",
  "source_page_url": "https://example.org/artwork-page",
  "image_url": "https://cdn.example.org/artwork.png",
  "resolved_image_url": "https://cdn.example.org/artwork.png",
  "source_domain": "example.org",
  "license": "CC-BY-4.0",
  "license_url": "https://creativecommons.org/licenses/by/4.0/",
  "attribution": "Creator name",
  "retrieved_at": "2026-08-26T12:00:00Z",
  "mime": "image/png",
  "size": 12345,
  "sha256": "..."
}
```

The host must require HTTPS, resolve and block loopback/private/link-local targets, revalidate every redirect, cap redirects, response bytes, decoded pixels, and time, accept only configured image MIME types, verify decoded content rather than trusting extensions, and strip metadata before packaging. Do not package a source with unknown redistribution rights. Prefer official or primary source pages, but an official page is provenance evidence rather than automatic redistribution permission.

## Phase Complete

Every phase ends with `phase_complete`:

```json
{
  "type": "phase_complete",
  "phase": "mpos-gen-app-web",
  "session_id": "sess_20260723_001",
  "payload": {
    "schema_version": "mpos-gen-app-web-v1",
    "result": "success",
    "checkpoint_id": "code_generated",
    "next_phase": "mpos-test-app-web",
    "app": {
      "fullname": "com.example.calculator",
      "publisher": "com.example",
      "version": "1.0.0"
    },
    "artifacts": [],
    "warnings": [],
    "structured_errors": []
  }
}
```

`result` values: `success`, `partial`, `failed`, `blocked`, `cancelled`.

Use `partial` when useful artifacts were produced but non-required checks or external capabilities are missing. Use `blocked` when user input, permissions, device access, or missing tooling prevents progress.

## Cancellation

On `cancel`, stop new writes, terminate owned child processes if the host allows it, preserve existing artifacts, and emit `phase_complete(result=cancelled)`.

## Retry

Retries must be idempotent. Reuse `idempotency_key` for the same user action; use a new key only when input changes. Before retrying, read `session_state.json` and the last phase result to avoid duplicating files or reusing stale errors.

## Resume

On `resume`, read `session_state.json`, artifact manifest, and the last successful checkpoint. Continue from the next incomplete phase unless the user explicitly requests a different phase.
