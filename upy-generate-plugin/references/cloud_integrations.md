# Cloud Integrations

Use this reference whenever generated firmware needs an external cloud service: LLM chat, ASR, TTS, vision, MQTT/IoT, webhooks, weather/maps, object storage, or a custom HTTP API.

## Core Rule

Do not silently generate deploy-ready code for a paid or credentialed cloud service. First produce a `cloud_service_plan`, show the user official setup links, and record the user's decision in `generate.cloud_integrations`.

Never write real API keys, tokens, access keys, secrets, or passwords into `firmware/conf.py`, `firmware/main.py`, `firmware/tasks/*.py`, tests, logs, `phase_complete`, or git commits.

## Interaction Flow

1. Detect cloud needs from `requirements`, `devices`, and behavior text. Keywords include `LLM`, `ASR`, `TTS`, `speech`, `voice`, `cloud_http`, `MQTT`, `IoT`, `webhook`, `weather`, `map`, `object storage`, `OpenAI compatible`, provider names, and Chinese equivalents.
2. Load `knowledge/cloud_service_catalog.json`.
3. Pick provider candidates by category and region. Include at least one generic `custom_http_proxy` option when the MCU would otherwise need complex signing, large TLS payloads, or secret-bearing vendor SDKs.
4. Ask the user to choose/confirm provider and readiness. The prompt must include official docs, console, and pricing or billing links when known.
5. Record the decision in `manifest_content.generate.cloud_integrations`.
6. If credentials are not ready, generate mock/simulation code only, or generate code that reads placeholders from a non-committed secret source. Do not set `next_phase=upy-deploy-plugin` unless each required service is deploy-ready or explicitly deferred to deploy with a permission prompt.
7. If the user chooses a service that requires server-side signing, token exchange, or heavy SDK behavior, prefer a gateway/proxy service. Firmware should call the gateway with a short device token, not store cloud account root credentials.
8. Run `scripts/check_cloud_integrations.py --project-dir <project_root>` before success.

## User Prompt Shape

Use an `approval_request` or equivalent plugin interaction:

```json
{
  "type": "approval_request",
  "phase": "upy-generate-plugin",
  "payload": {
    "approval_id": "cloud_service_setup",
    "reason": "Generated firmware needs ASR + LLM + TTS cloud APIs.",
    "options": [
      {
        "provider_id": "aliyun_bailian",
        "label": "Alibaba Cloud Model Studio / Bailian",
        "official_links": {
          "docs": "https://help.aliyun.com/zh/model-studio/get-api-key",
          "console": "https://bailian.console.aliyun.com/",
          "pricing": "https://help.aliyun.com/zh/model-studio/"
        },
        "requires": ["API Key", "billing enabled", "model access"]
      },
      {
        "provider_id": "custom_http_proxy",
        "label": "Use my own HTTPS gateway",
        "official_links": {},
        "requires": ["gateway URL", "device token policy"]
      }
    ],
    "questions": [
      "Which provider should this project target?",
      "Are API credentials already created, should deploy prompt for them later, or should generate stay mock-only?",
      "May firmware call the cloud service directly, or must it call a gateway/proxy?"
    ]
  }
}
```

## Manifest Shape

Record only metadata and secret variable names:

```json
{
  "generate": {
    "cloud_integrations": [
      {
        "provider_id": "aliyun_bailian",
        "category": "llm",
        "services": ["chat_completions"],
        "mode": "direct_https",
        "official_links": {
          "docs": "https://help.aliyun.com/zh/model-studio/get-api-key",
          "console": "https://bailian.console.aliyun.com/",
          "pricing": "https://help.aliyun.com/zh/model-studio/"
        },
        "credential_management": {
          "requires_credentials": true,
          "status": "deferred_to_deploy",
          "secret_names": ["ALIYUN_BAILIAN_API_KEY"],
          "storage": "device_secrets_file",
          "forbidden_locations": ["firmware/conf.py", "git", "phase_complete"]
        },
        "user_action_required": [
          "Create API Key in provider console",
          "Enable billing or token plan if required",
          "Provide secret during deploy permission prompt"
        ],
        "deploy_ready": false,
        "deploy_blocker": "credentials_deferred_to_deploy"
      }
    ]
  }
}
```

Allowed `credential_management.status` values:

| Status | Meaning |
|---|---|
| `ready` | User confirmed credentials and billing are ready; secrets still must not be stored in code. |
| `deferred_to_deploy` | Generate may succeed only if deploy will prompt for secrets before upload. |
| `mock_only` | Generate mock/simulation code only; use `next_phase=upy-simulate-plugin` or `null`. |
| `not_required` | Public endpoint or local gateway that does not require per-device secrets. |
| `blocked` | Missing account, billing, region, model access, or provider choice blocks deploy-ready success. |

## Provider Categories

Use the catalog as data, not hard-coded prose. The current categories are:

- `llm`: OpenAI-compatible chat/completions, vendor model APIs, embedding/rerank if needed.
- `speech`: ASR, TTS, realtime voice, audio translation.
- `vision`: OCR, image analysis, multimodal model calls.
- `iot`: MQTT broker, cloud IoT platform, device shadow, telemetry.
- `notification`: DingTalk, Feishu, WeCom, SMS/email gateways, generic webhooks.
- `storage`: object storage or log upload. Prefer proxy/gateway when vendor signing is complex.
- `data_api`: weather, maps, geocoding, time-series API, custom REST.
- `custom_http_proxy`: user's own service that hides vendor credentials from the device.

## Firmware Patterns

- Put non-secret endpoint constants and feature flags in `firmware/conf.py`.
- Put secret names in `firmware/secrets.example.py` or deploy metadata, never real values.
- If a `firmware/secrets.py` file is generated, it must contain placeholders only and must be ignored by git.
- For direct HTTPS from MicroPython, isolate calls in a task or client wrapper with timeout, retry, backoff, payload size limits, and structured errors.
- In `async` scaffold mode, do not call synchronous HTTP directly inside an async coroutine. Use a cooperative state machine, a worker/thread handoff when supported, or mark the result partial.
- For MQTT, prefer a MicroPython-compatible client and bounded queues. Never block sensor sampling while reconnecting.
- For providers requiring HMAC request signing, OAuth token exchange, mTLS, or large SDKs, prefer `custom_http_proxy`.

## Success Policy

`phase_complete.result=success` with `next_phase=upy-deploy-plugin` is valid only when:

- Every `cloud_integrations[]` item has official links or an explicit `custom_http_proxy` explanation.
- Each credentialed service has `credential_management.status` equal to `ready`, `deferred_to_deploy`, `not_required`, or `mock_only`.
- `mock_only` services do not claim real deploy readiness.
- No generated file contains a hard-coded secret.
- `scripts/check_cloud_integrations.py` passes.

If the cloud plan is unresolved, output `partial` or set `next_phase=null` / `upy-simulate-plugin`, and add a structured error such as `CLOUD_PROVIDER_UNCONFIRMED`, `CLOUD_CREDENTIALS_REQUIRED`, or `CLOUD_GATEWAY_REQUIRED`.
