# Runtime dependencies

## Resolution

Resolve packages for each new Session:

1. Request `GET https://upypi.net/api/search?q={package}`.
2. Read `results[].url` as the versioned package URL.
3. Request `{package_url}/package.json`.
4. Validate `name`, `version`, `chips`, `fw`, `deps`, and `urls`.
5. Recursively inspect `deps` for compatibility and reporting.

New Sessions re-resolve uPyPI. Resume and retry reuse their Session's recorded versioned URLs for idempotency. Store only dependency metadata and installation receipts; never store driver source in the Skill or artifact manifest.

## Required packages

- `xfyun_asr`
- `xfyun_tts`
- Dependencies declared by those packages, including `async_websocket_client`
- A separately selected MicroPython-compatible asynchronous HTTP/SSE client for the configured LLM provider

Never assume versions from this document. Use the resolver output.

## Installation

Prefer host-side deployment:

```text
mpremote mip install --target=<app-private-lib> <versioned-package-url>
```

Allow device-side installation only when requested:

```python
mip.install(versioned_package_url, target=app_private_lib)
```

Add the private library directory to `sys.path` before importing installed modules. Use shared `/lib` only after explicit approval.

MIP reads `package.json`, installs `urls`, and follows `deps`. Do not independently download files into the App template. Do not fall back to a bundled copy while offline.

## Verification

After installation, probe imports and required symbols:

- `xfyun_asr`
- `xfyun_tts`
- `async_websocketclient.AsyncWebsocketClient`
- `fastb64.b64encode_str`
- `fastb64.b64decode`

The target firmware has been tested with `fastb64`. If a probe fails, return `RUNTIME_CAPABILITY_MISSING`; do not patch or republish the driver.

## Failure behavior

Classify unavailable network, package not found, incompatible chip/firmware, storage full, permission denial, import failure, and symbol failure separately. Mark retryable network failures as resumable and keep the last valid checkpoint.
