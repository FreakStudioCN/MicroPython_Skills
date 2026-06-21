# upy-analyze V0 Protocol Reference

Use this reference when constructing or validating protocol messages for `upy-analyze`. `SKILL.md` contains the workflow; this file defines field meanings, required fields, and enums.

## 1. Envelope Fields

All formal protocol messages use the same top-level envelope.

| Field | Required | Type | Source | Meaning |
|------|----------|------|--------|---------|
| `protocol_version` | yes | string | plugin/server | Protocol version. For V0, always `"1.0"`. |
| `msg_id` | yes | UUID string | message sender | Unique ID for this message. Generate a new UUID for every message. |
| `session_id` | yes | UUID string | plugin | Workflow session ID. Keep unchanged across all messages in one project flow. |
| `phase` | yes | string | plugin/server | Current phase. For this skill, always `"analyze"`. |
| `timestamp` | yes | ISO 8601 string | message sender | Message creation time, UTC preferred. |
| `type` | yes | string | message sender | Message kind, such as `start_phase`, `approval_request`, `status_update`, `script_run`, `phase_complete`. |
| `payload` | yes | object | message sender | Type-specific body. |

Rules:

- `session_id` is created by the plugin in `start_phase`; skill/server only inherit it.
- Claude Code direct-test mode may generate a UUID when no `session_id` is available.
- Top-level `phase` and `payload.phase` are both kept for `phase_complete` and must match.

## 2. start_phase Payload

Plugin starts analyze with:

| Field | Required | Type | Default | Meaning |
|------|----------|------|---------|---------|
| `user_description` | yes | string | none | User's natural-language hardware project request. |
| `pre_selected_board` | no | object or null | `null` | Board selected before analyze. Analyze records this context but does not validate firmware or pins. |
| `preferences` | no | object | `{}` | User preference container. |
| `preferences.mode` | no | string | `"beginner"` | `beginner` uses defaults; `custom` may trigger one requirement supplement card. |
| `preferences.locale` | no | string | `"zh"` | UI/content locale. |
| `existing_hardware` | no | array | `[]` | Hardware the user already owns. |

`pre_selected_board` may contain:

| Field | Required if board exists | Meaning |
|------|---------------------------|---------|
| `id` | yes | Board ID from board database. |
| `display_name` | yes | UI display name. |
| `mcu` | yes | MCU/chip model. |
| `chip_family` | yes | Chip family for downstream firmware checks. |
| `firmware_url` | recommended | MicroPython firmware page or URL. |

## 3. status_update Payload

Use `status_update` only for non-blocking progress.

| Field | Required | Type | Meaning |
|------|----------|------|---------|
| `level` | yes | string | `info`, `warn`, `error`, or `success`. |
| `message` | yes | string | Short user-facing progress message. |
| `step_id` | recommended | string | Stable step identifier, such as `intent_extraction` or `driver_search`. |
| `step_status` | recommended | string | `pending`, `running`, `done`, or `failed`. |
| `progress` | no | number | 0.0 to 1.0. |
| `progress_label` | no | string | Human-readable progress like `2/5`. |
| `detail` | no | string | Extra diagnostic text. |

Required user choices must not be sent as plain text `status_update`; use `approval_request`.

## 4. approval_request Payload

Use `approval_request` for all user decisions.

| Field | Required | Type | Meaning |
|------|----------|------|---------|
| `approval_id` | yes | string | Stable ID for matching the response. |
| `header` | yes | string | Card title. |
| `question` | yes | string | Main question. |
| `summary` | no | object | Short project/board/function summary. |
| `items` | no | array | Selectable choices or devices. |
| `allow_add` | no | boolean | Whether user may add an item. |
| `allow_remove` | no | boolean | Whether user may remove an item. |
| `multi_select` | no | boolean | Whether multiple items can be selected. |
| `actions` | yes | array | Buttons; each item has `label`, `value`, optional `primary`. |

Analyze approval IDs:

| `approval_id` | Required? | Purpose |
|---------------|-----------|---------|
| `device_confirm` | yes | Confirm generated device plan. |
| `requirement_supplement` | conditional | Fill missing scene/power/output/performance context. |
| `alternative_device` | conditional | Choose replacement for system-recommended device with no driver. |

After sending an `approval_request`, stop and wait for the plugin/user response.

## 5. script_run Payload

Use `script_run` for deterministic local scripts. Analyze uses it to run `scripts/init_manifest.py`.

| Field | Required | Type | Meaning |
|------|----------|------|---------|
| `script_id` | yes | string | Stable ID for matching result. |
| `interpreter` | yes | string | For analyze, use `"python"`. |
| `script` | yes | string | Script path, usually `{skill_dir}/scripts/init_manifest.py`. |
| `args` | yes | string[] | Command args. |
| `cwd` | yes | string | `{project_dir}` or session artifact dir. |
| `timeout_ms` | yes | number | Timeout in milliseconds. |

Allowed analyze script actions:

```text
--input manifest_draft.json --write-path manifest_validated.json
--validate-phase-complete --input phase_complete.analyze.json --compare-manifest manifest_validated.json
```

Do not use arbitrary shell for analyze validation.

## 6. Manifest Draft Fields

`manifest_draft.json` is the unvalidated draft created by analyze.

Top-level:

| Field | Required | Meaning |
|------|----------|---------|
| `project_name` | yes | Short project name. |
| `requirements` | yes | User requirements with defaults filled. |
| `devices` | yes | Confirmed device list. |

`requirements`:

| Field | Required | Default | Valid values |
|------|----------|---------|--------------|
| `description` | yes | none | Free text. |
| `scene` | yes | `indoor` | `indoor`, `outdoor`, `vehicle`, `industrial`, `wearable`, `underwater`, `unknown` |
| `power` | yes | `usb` | `usb`, `battery_li`, `battery_disposable`, `solar`, `poe`, `unknown` |
| `network` | yes | `none` | `none`, `wifi`, `ble`, `mqtt`, `zigbee`, `lora`, `4g`, `unknown` |
| `sample_rate` | yes | `normal_1hz` | `high_100hz_plus`, `normal_1hz`, `low_minute`, `triggered`, `unknown` |
| `precision` | yes | `normal` | `high`, `normal`, `low_power_first`, `unknown` |
| `response_time` | yes | `1s` | `ms_level`, `1s`, `minute_level`, `unknown` |
| `temp_range` | yes | `normal_0_40` | `normal_0_40`, `extended_-20_70`, `industrial_-40_85`, `unknown` |
| `size_constraint` | yes | `none` | `none`, `compact`, `wearable`, `custom`, `unknown` |
| `budget_yuan` | yes | `medium_50` | `low_30`, `medium_50`, `medium_100`, `high_200`, `unlimited`, `unknown` |
| `experience` | yes | `beginner` | `beginner`, `experienced`, `unknown` |
| `output` | yes | `["serial"]` | Array of output enum values. |
| `existing_hardware` | yes | `[]` | Array. |
| `special_requirements` | yes | `["none"]` | Array of special requirement enum values. |
| `mcu_specified` | yes | `null` | String or null. |

`output` enum:

```text
serial / display_oled / display_lcd / display_eink / buzzer / led / led_rgb /
cloud_mqtt / cloud_http / local_file / relay / motor / servo
```

`special_requirements` enum:

```text
watchdog / ota_update / deep_sleep / encryption / button_control /
voice_control / battery_monitor / error_led / none
```

`devices[]`:

| Field | Required | Meaning |
|------|----------|---------|
| `name` | yes | Device model or descriptive name. |
| `type` | yes | Normalized device type, e.g. `temperature_humidity_sensor`. |
| `interface` | yes | Hardware interface. |
| `source` | yes | `user_specified` or `system_recommended`. |
| `quantity` | yes | Integer quantity, default 1. |
| `driver` | yes | Driver object. |

`interface` enum:

```text
I2C / SPI / UART / GPIO / PWM / ADC / I2S / 1-Wire / CAN / USB / WiFi / BLE
```

`driver.source` enum:

```text
builtin_runtime / micropython_lib / upypi / awesome-micropython / github / local / cold-driver / none
```

Driver source meanings:

| Source | Meaning |
|--------|---------|
| `builtin_runtime` | MicroPython runtime API is enough, such as `machine.Pin`, `machine.I2S`, `network`. |
| `micropython_lib` | Official MicroPython ecosystem middleware/general-purpose package. |
| `upypi` | Concrete driver package from upypi. |
| `awesome-micropython` | Driver found via awesome-micropython index. |
| `github` | Driver found directly from GitHub. |
| `local` | Local driver; analyze should avoid this unless explicitly provided. |
| `cold-driver` | No ready driver and user-specified device or user rejected replacement. |
| `none` | No ready driver and no better classification; avoid when builtin runtime applies. |

## 7. phase_complete Payload

`phase_complete` is the only phase-completion signal.

| Field | Required | Type | Meaning |
|------|----------|------|---------|
| `phase` | yes | string | Must be `"analyze"` and match envelope phase. |
| `result` | yes | string | `success`, `partial`, or `failed`. |
| `summary` | yes | string | Human-readable summary. |
| `next_phase` | yes | string or null | `select-hw` on success, `null` on partial/failed. |
| `manifest_content` | yes | object | Normalized manifest snapshot for downstream phase. |
| `artifacts` | yes | array | Tables, file lists, markdown, etc. |
| `warnings` | yes | string[] | Human-readable warnings. |
| `errors` | yes | string[] | Human-readable errors. |
| `structured_errors` | yes | object[] | Machine-readable errors. |
| `checkpoint` | required for partial | object | Resume marker for partial result. |

Result rules:

| result | Required `next_phase` | Manifest | Extra requirement |
|--------|-----------------------|----------|-------------------|
| `success` | `"select-hw"` | Valid manifest required | No checkpoint required. |
| `partial` | `null` | Best available manifest snapshot required | `checkpoint` required. |
| `failed` | `null` | Best available manifest snapshot required if possible | `structured_errors` should explain failure. |

## 8. checkpoint Fields

| Field | Required | Type | Meaning |
|------|----------|------|---------|
| `checkpoint_id` | yes | UUID string | Unique checkpoint ID. |
| `resume_phase` | yes | string | Must be `"analyze"`. |
| `resume_step` | yes | string | Step to resume, such as `device_confirm` or `driver_search`. |
| `resume_label` | yes | string | User-facing resume label. |
| `reason` | yes | string | Why partial happened, e.g. `user_cancelled`, `timeout`, `partial_driver_search`. |

## 9. structured_errors Fields

| Field | Required | Type | Meaning |
|------|----------|------|---------|
| `code` | yes | string | Stable error code. |
| `message` | yes | string | Human-readable detail. |
| `severity` | yes | string | `info`, `warning`, `error`, or `fatal`. |
| `recoverable` | recommended | boolean | Whether user/system can recover. |
| `retryable` | recommended | boolean | Whether retry may help. |
| `source` | recommended | string | Component that produced the error. |

## 10. artifact Fields

Supported `artifact.type`:

```text
table / file_tree / markdown / html / code_diff / file_list
```

`file_list.files[]`:

| Field | Required | Type | Meaning |
|------|----------|------|---------|
| `path` | yes | string | Path relative to session artifact directory. |
| `status` | yes | string | `created`, `updated`, `unchanged`, `skipped`, or `error`. |
| `kind` | recommended | string | Logical kind, such as `manifest`, `log`, `phase_complete`. |
| `mime_type` | recommended | string | MIME type. |
| `description` | recommended | string | Human-readable description. |

Direct-test required file declarations:

```text
manifest_draft.json
manifest_validated.json
phase_complete.analyze.json
driver_search_log.md
```

`analyze_phase_log.md` is recommended for Claude Code direct tests but is not a formal protocol-required artifact.

## 11. Validation Commands

Normalize manifest:

```bash
python {skill_dir}/scripts/init_manifest.py --input manifest_draft.json --write-path manifest_validated.json
```

Validate phase_complete:

```bash
python {skill_dir}/scripts/init_manifest.py --validate-phase-complete --input phase_complete.analyze.json --compare-manifest manifest_validated.json
```

Validate file_list paths in a direct-test session directory:

```bash
python {skill_dir}/scripts/init_manifest.py --validate-phase-complete --input phase_complete.analyze.json --compare-manifest manifest_validated.json --artifact-root .
```

If any validation command fails, do not claim `result="success"`.
