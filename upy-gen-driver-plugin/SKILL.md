---
name: upy-gen-driver-plugin
description: 插件化 workflow skill，用于从 datasheet、Arduino/C/C++ source、GitHub repository、chip model 或当前项目 cold-driver item 生成缺失的 MicroPython hardware driver。适用于插件全局工具 "生成缺失硬件驱动" 被触发、manifest 中存在 devices[].driver.status=cold_driver_required，或 deploy/autofix 反馈显示缺失/损坏硬件驱动，并且流程需要 session/checkpoint/resume、retry、timeout、cancellation、permission prompts、structured errors 和 artifact manifests。
---

# upy-gen-driver-plugin

生成缺失的 MicroPython 驱动，但不要修改 legacy `upy-gen-driver` skill。本 skill 是插件化 workflow 版本：本地文件、脚本、设备和用户确认操作都通过协议消息表达，同时为插件运行和本地 mock 测试输出可恢复的 artifacts。

## Operating Modes

- `pipeline`: 从已有项目 session 进入，位置通常在 scaffold 之后、generate 之前。读取上游 `manifest_content`，写入项目驱动文件，然后返回 `upy-generate-plugin`。
- `standalone`: 从插件全局工具 "生成缺失硬件驱动" 进入。要求用户提供 PDF、Arduino/C/C++ source、GitHub URL、chip model 或 image input，然后生成独立驱动包和测试材料。
- `resume`: 从 `session_state.upy_gen_driver_plugin.json` 继续。复用任何 checkpoint 之前，必须先校验 artifact hash。
- `fix`: 根据 deploy/autofix 反馈修复已生成驱动，优先做最小改动。

## Required References

只在需要时读取这些 reference：

- `references/protocol_fields.md`: message envelope、start payload、checkpoint、phase_complete、file_manifest、permissions、structured errors。
- `references/legacy_upy_gen_driver_rules.md`: 必须保留的 legacy driver-generation 规则。
- `references/norm_driver_p0_rules.md`: production driver normalization checklist。

## Core Rules

- 不要覆盖或编辑 `G:\MicroPython_Skills\upy-gen-driver`。
- envelope 使用 `phase="upy-gen-driver-plugin"`，payload/domain phase 使用 `gen-driver`。
- 本 skill 的协议身份固定为 `upy-gen-driver-plugin`。不要缩写、重命名、别名化或推断成 `upy-driver-plugin`、`driver`、`gen-driver-plugin` 或其他名称；发现旧产物使用这些名称时，必须把它当作 stale/wrong-phase artifact，重新生成正确身份的产物。
- 最终协议文件名必须是 `phase_complete.upy_gen_driver_plugin.json`；session state 文件名必须是 `session_state.upy_gen_driver_plugin.json`。不要输出 `phase_complete.upy_driver_plugin.json`、`session_state.upy_driver_plugin.json` 或任何其他 phase 文件名。
- 所有 phase-scoped `idempotency_key`、`checkpoint_id`、`resume_phase` 和 permission action key 必须使用 `upy-gen-driver-plugin` 前缀；业务 payload 里的 `phase` 与 `domain_phase` 只能使用 `gen-driver`。
- 插件调用和本地 skill-call 测试必须使用同一套 message contract。本地测试可以直接执行文件，但仍必须写出插件 host 会收到的 `session_state`、permissions、file manifest、structured errors 和 `phase_complete` artifacts。
- 不要手写 `session_state.upy_gen_driver_plugin.json`。必须通过 `scripts/update_session_state.py` 创建或更新 state，并在写出 `phase_complete` 前运行 `scripts/update_session_state.py --session-dir <session_root> --check`。
- 最终封包必须按固定顺序收尾：先完成所有 artifact 和最终 `session_state` 更新，再生成 draft phase_complete，然后运行 `scripts/finalize_phase_complete.py` 刷新 `payload.file_manifest.files[].sha256/bytes` 并写出最终 `phase_complete.upy_gen_driver_plugin.json`。最终文件写出后，不要再修改 manifest 中列出的文件。
- 正式 artifact path 必须相对 `artifact_root` 或 `project_root`；不要把 Windows drive path 写进 `phase_complete`。
- 将 `runtime_context.session_root` 视为 workflow session 的事实来源。不要从最新的 `sessions/*` 目录推断当前 session。
- MicroPython I2C driver code、debug driver、test script 和 wiring docs 中的默认设备地址必须使用 7-bit address，不要把包含 R/W bit 的 8-bit transfer address 传给 `scan()`、`readfrom_mem()`、`writeto_mem()` 或同类 I2C API。
- datasheet 中的 `0x3C/0x3D` 这类 write/read address 只能作为 datasheet evidence 记录；生成代码前必须归一化为 7-bit address，例如 `0x3C >> 1 == 0x1E`。
- 本地文件、脚本、网络和设备操作使用 `permission_request`；用户业务选择使用 `approval_request`。
- 每个本地 action 都必须有稳定的 `idempotency_key`。
- 每个 script/device/approval wait 都必须有 `timeout_ms`。
- 用户取消、无设备、超时、artifact stale、缺少 capability 或硬件验证耗尽时，输出 `result="partial"`，并携带 checkpoint 和 `structured_errors[]`；不要宣称 success。
- 缺少 host 能力时使用 `HOST_CAPABILITY_MISSING`，并在 `details.missing_capability` 写明能力名；只有 host 已支持并实际执行 device scan/run 后仍找不到设备，才使用 `DEVICE_NOT_FOUND`。不要把 `missing_capability=device_command` 放进 `DEVICE_NOT_FOUND`。
- 只有用户明确选择时才可以跳过硬件验证，并且最终结果必须带 warning。默认行为是保存 checkpoint，等待后续 resume。
- partial 且未完成验证时必须写 `hardware_verified=false` 和 `verification_mode="none"`。不要把无设备、取消、超时或普通未验证 partial 标成 `verification_mode="mock"`。
- `verification_mode="mock"` 只允许用于本地 mock self-test 实际返回 `SELF_TEST_PASS` 的 success 结果；它仍然不能设置 `hardware_verified=true`。
- 未验证 `{chip}.py` 的 file write action 必须使用 `write_driver_artifact` idempotency key；只有 `file_manifest.files[].role="production_driver"` 时才允许使用 `write_production_driver`。
- 未验证 partial 的任何 summary、description、artifact label、permission reason 或 file_manifest description 都不要写 `production driver`；统一写 `driver artifact` 或 `unverified driver artifact`。
- 重试同一个 action 时保持相同 `session_id` 和 action 级 `idempotency_key`；将 `retry_of` 设置为原始 message id，并追加一个 `status="retrying"` 的 state event。
- cancellation 默认是可恢复的 partial result，除非用户明确丢弃 artifacts。保留最后一个可信 artifact，并将 checkpoint 设置为 `cancelled`。
- timeout 不能静默处理。host、script、approval 和 device timeout 都必须转换成 structured errors；如果可以从 checkpoint 继续，设置 `retryable=true`。
- `DEVICE_NOT_FOUND` 必须有可审计的 device 操作证据：`payload.permissions[]` 中至少包含一次 `device_scan` 或 `device_run`。如果本轮只有 file/script 操作，或 host 缺少设备操作能力，不要写 `DEVICE_NOT_FOUND`。
- 所有用户可见文本字段必须是 UTF-8 clean text。不要输出 replacement character、mojibake 片段、smart punctuation、误解码标点或夹在中英文中的异常短外文片段；协议文案必须使用 ASCII punctuation。

## Start Phase Contract

接收插件发送的 `start_phase`。envelope 必须包含 `protocol_version`、`msg_id`、`session_id`、`phase="upy-gen-driver-plugin"`、`type="start_phase"` 和稳定的 `idempotency_key`。

Envelope fields:

| Field | 含义 |
|---|---|
| `protocol_version` | 协议 schema 版本。出现破坏性变更前使用 `"1.0"`；遇到未知 major version 时拒绝继续，不要猜测兼容。 |
| `msg_id` | 当前协议消息的唯一 id。用于 log、`retry_of` 和用户可见诊断。 |
| `session_id` | 稳定的 workflow id。retry、resume、cancellation 和 timeout recovery 都必须保持同一个值。 |
| `phase` | 插件 envelope phase。必须是 `upy-gen-driver-plugin`，不要写成 `gen-driver`。 |
| `timestamp` | UTC ISO timestamp，用于排序和审计。 |
| `type` | 消息类型，例如 `start_phase`、`permission_request`、`script_run`、`device_command`、`status_update` 或 `phase_complete`。 |
| `idempotency_key` | 稳定的 action key。重试同一个 action 时复用同一个 key，避免重复写文件或重复执行设备动作。 |
| `retry_of` | 当前消息是在重试或完成哪个失败 action 时，填写前一个 `msg_id`。首次尝试使用 `null`。 |

Payload fields:

| Field | 含义 |
|---|---|
| `mode` | 执行模式：`pipeline`、`standalone`、`resume` 或 `fix`。 |
| `phase` / `domain_phase` | 业务 phase。必须是 `gen-driver`；它用于和插件 envelope phase 区分。 |
| `source_phase` | 请求生成驱动的上游 phase，通常是 `upy-scaffold-plugin`、`upy-generate-plugin` 或 deploy/autofix feedback。 |
| `source_phase_complete_path` | 上游 `phase_complete` artifact 的相对路径，用作证据来源。 |
| `manifest_content` | 当前项目 manifest object。`pipeline` 模式下用它查找 `devices[].driver.status == "cold_driver_required"`，并更新生成驱动路径。 |
| `source` | 驱动证据来源：PDF、Arduino/C/C++ file、GitHub URL、chip model、image 或当前 cold-driver item。缺失时通过 `approval_request(gen_driver_input)` 询问用户。 |
| `runtime_context.artifact_root` | session artifacts 的根目录。输出中的正式路径必须相对此 root。 |
| `runtime_context.session_root` | canonical session 目录。state、logs 和最终 `phase_complete` 都写到这里。 |
| `runtime_context.project_root` | 项目目录，生成的 driver files 和 manifest updates 放在这里。 |
| `runtime_context.file_operation_root` | 通过插件发起文件写入时允许的最大根目录。 |
| `runtime_context.resource_root` | skill resource 目录，用于定位 bundled scripts 和 references。 |
| `capabilities` | host 支持的操作能力。使用 upload、file operations、scripts、device commands、cancellation、checkpoint resume、idempotency cache 或 network 前必须先检查。 |
| `timeouts` | 各操作的 timeout budget，单位毫秒。缺失时使用显式默认值，并把最终采用的 timeout 写入消息。 |
| `resume_from` | `resume` 模式的 checkpoint descriptor。继续前必须校验 hash 和 session identity。 |

如果缺少 `mode`，只有当前 manifest 中存在 `driver.status=cold_driver_required` 时才推断为 `pipeline`；否则使用 `standalone`。

## Output Field Meanings

`phase_complete.payload` fields:

| Field | 含义 |
|---|---|
| `result` | `success`、`partial` 或 `failed`。无设备、用户取消、超时、缺少 capability、artifact stale 或验证耗尽但仍可恢复时使用 `partial`。 |
| `summary` | 简短的人类可读结果说明。必须说明是否完成硬件验证。 |
| `next_phase` | success 后通常是 `upy-generate-plugin`；等待 resume 或用户动作的 partial/failure 使用 `null`。 |
| `checkpoint` | resume anchor，包含 `checkpoint_id`、`resume_phase`、`resume_step` 和 `state_file`；`checkpoint_id` 必须使用 `upy-gen-driver-plugin:<session_id>:<checkpoint_name>`。 |
| `permissions[]` | file/script/device/network/manifest 权限请求或本地 mock 自动授权的审计记录。 |
| `file_manifest.files[]` | 生成、更新、跳过或失败文件的正式清单。每个 path 必须是相对路径，并且必须包含 `role`。 |
| `artifacts[]` | 面向用户展示的 artifact 分组。必须包含一个非空 `file_list` entry，且每个 entry 要有 `files[]` 或 `items[]`。 |
| `structured_errors[]` | 机器可读错误。只有 `success` 时可以为空。 |
| `manifest_content` | `pipeline` 模式下更新后的项目 manifest；`standalone` 且没有项目 manifest 时使用 `null`。 |

`file_manifest.files[]` roles:

| Role | 含义 |
|---|---|
| `source` | 用户提供或网络获取的 source file。 |
| `extracted_text` | `extract_pdf.py` 生成的 PDF extraction output。 |
| `mapping` | `convert_arduino.py` 生成的 Arduino/C/C++ structure 和 API mapping。 |
| `understanding` | `driver_understanding.json`，用于生成驱动的结构化硬件事实。 |
| `debug_driver` | `{chip}_debug.py`，用于硬件验证的 verbose single-file driver。 |
| `production_driver` | `{chip}.py`，用于项目集成的 normalized driver。 |
| `test` | `test_{chip}.py` standalone validation script。 |
| `wiring` | `wiring_{chip}.md` 接线和使用说明。 |
| `verify_log` | 硬件或 mock 验证日志。 |
| `manifest` | 项目 manifest 更新。 |
| `state` | `session_state.upy_gen_driver_plugin.json`。 |
| `phase_complete` | 最终协议结果 artifact。 |

未完成真实硬件验证时，如果保留 `{chip}.py`，`file_manifest.files[].role` 必须使用 `artifact`，面向用户的 `artifacts[].file_list` 文案必须写成 `Driver artifact (unverified)` 或 `Unverified driver artifact`，不要写 `Production driver (unverified)`。

未完成真实硬件验证时，如果写入 `{chip}.py`，permission/action 的 `idempotency_key` 必须使用 `upy-gen-driver-plugin:<session_id>:write_driver_artifact:<chip>:v1`。通过真实硬件验证、用户明确 skip verification 或 local mock success 后，才允许使用 `write_production_driver`。

`structured_errors[]` fields:

| Field | 含义 |
|---|---|
| `code` | 稳定的大写错误码，例如 `DEVICE_RUN_TIMEOUT`。 |
| `severity` | `warning`、`error` 或 `fatal`。 |
| `phase_step` | 错误发生的步骤，例如 `source_preprocess` 或 `hardware_verify`。 |
| `retryable` | 是否可以不创建新 session，通过 retry/resume 继续。 |
| `message` | 人类可读说明。 |
| `details` | 机器可读上下文，例如 timeout、command、port、path、source hash、missing capability 或 log path。 |
| `next_action` | 建议下一步动作，例如 `connect_device_and_resume`、`retry_device_run` 或 `request_pdf_or_arduino_source`。 |

## Plugin and Local Compatibility

两种执行形态使用同一套 contract：

- Plugin host：发出协议消息，并等待 `approval_response`、`permission_response`、`file_result`、`script_result`、`device_result` 或 `cancellation`。
- Local mock test：在本地执行等价动作，然后把同样协议形状的 event 写入 `sessions/<session_id>/gen_driver/message_log.jsonl` 或最终 artifacts。
- 两种形态都必须生成 `sessions/<session_id>/session_state.upy_gen_driver_plugin.json`。
- 两种形态都必须为 success、partial、failed、cancelled 和 timeout outcome 生成 `phase_complete.upy_gen_driver_plugin.json`。
- 本地测试不能绕过 permission 语义。即使 mock 自动授权，也要在 `payload.permissions[]` 中记录 file/script/device permissions。
- 本地 no-device mock 如果返回 `DEVICE_NOT_FOUND`，也必须记录 `device_scan` 或 `device_run` permission entry；缺少设备操作能力时使用 `HOST_CAPABILITY_MISSING`。
- 本地测试不能把 mock `SELF_TEST_PASS` 当成真实硬件证明。只有本地 mock self-test 实际返回 `SELF_TEST_PASS` 时才标记 `verification_mode="mock"`；无设备、取消、超时或没有运行 mock self-test 的 partial 必须标记 `verification_mode="none"`。

## Workflow

1. 校验 envelope、runtime roots 和 capabilities。
2. 如果缺少 source，发出 `approval_request(gen_driver_input)`，让全局工具输入卡片收集材料。
3. 收集一种 source type：PDF、Arduino/C/C++ source、GitHub URL、chip model、image 或当前项目 cold-driver item。
4. 通过协议 `script_run` 预处理 source：
   - PDF: `scripts/extract_pdf.py --input <path> --output <json> --json-summary`
   - Arduino/C/C++: `scripts/convert_arduino.py --input <path> --output <json> --json-summary`
5. 通过 `file_operation(write)` 写入 `driver_understanding.json`。内容必须包含 protocol、addressing、ID register、ready strategy、data integrity、register map、source evidence 和 ambiguity notes。I2C `addressing` 必须区分 `address_7bit`、datasheet write/read transfer address、derivation 和证据来源。
6. 通过 `file_operation(write)` 生成 `{chip}_debug.py`。debug driver 必须包含 self-test prints 和 bounded polling。
7. 更新 session state checkpoint `debug_driver_written`。
8. 请求 device scan 和 debug run 权限。如果没有设备，发出 `approval_request(gen_driver_no_device)`，提供 `retry`、`save_partial` 和 `cancel`。
9. 最多运行 10 轮硬件验证，命令形态为 `scripts/run_on_device.py --com <port> --file <debug.py> --capture --timeout-ms 30000 --json-summary`。
10. 如果出现 `SELF_TEST_PASS`，checkpoint 到 `hardware_verify_passed`。否则分析 log、编辑 debug driver，并重试直到达到上限。
11. 只有 verified pass 或用户明确 skip warning 后，才能生成生产版 `{chip}.py`。移除 debug prints，保留有意义的 exceptions，并保持 dependency injection。
12. 使用 `references/norm_driver_p0_rules.md` 规范化生产驱动。
13. 生成 `test_{chip}.py` 和 `wiring_{chip}.md`，用于 standalone hardware validation。
14. 在 `approval_request(gen_driver_standalone_test)` 后，可选运行 standalone test。
15. 在 `pipeline` 模式下，更新 `project/project-manifest.json` 和 `manifest_content.devices[].driver`，指向生成的 local driver。
16. 只有需要用户选择时才发出 `approval_request(gen_driver_next_step)`。常见选择包括接入 `upy-generate-plugin`、结束流程或稍后 publish。
17. 将最终 checkpoint 写入 `session_state.upy_gen_driver_plugin.json`，并运行 `scripts/update_session_state.py --session-dir <session_root> --check`。
18. 写入 draft phase_complete，然后运行 `scripts/finalize_phase_complete.py --input <draft_phase_complete> --output <session_root>/phase_complete.upy_gen_driver_plugin.json --artifact-root <artifact_root> --session-state <session_root>/session_state.upy_gen_driver_plugin.json`。通过后才作为最终结果输出。

## Driver Understanding Contract

在写任何 driver file 之前，先写 `gen_driver/docs/driver_understanding.json`。这个 object 是 source material 和 generated code 之间的 evidence bridge。

至少包含：

| Field | 含义 |
|---|---|
| `chip` | 用于 filename 的 normalized chip/module id。 |
| `source_evidence[]` | 作为证据使用的 datasheet pages、Arduino lines、URLs 或 user notes。 |
| `protocol` | `i2c`、`spi`、`uart`、`onewire` 或其他明确 bus type。 |
| `addressing` | I2C address、SPI mode/CS notes、UART baud rate 或等价连接事实。I2C 必须写出 `address_7bit`；如果 datasheet 给出 8-bit write/read transfer address，还必须写出 `datasheet_write_8bit`、`datasheet_read_8bit`、`derivation` 和 `code_address_rule="Use address_7bit for MicroPython I2C APIs."`。 |
| `chip_identification` | ID/WHO_AM_I/CHIP_ID register 和 expected value；如果没有，则写 `N/A` 并提供 fallback read/write sanity check。 |
| `ready_strategy` | status-bit polling、interrupt pin、fixed delay 或 no ready signal。必须包含 timeout 和 datasheet timing。 |
| `register_map[]` | address、name、bit fields、read/write permissions、reset/default value 和 write-only notes。 |
| `init_sequence[]` | reset/configuration steps、timing 和 read-back expectations。 |
| `data_format` | endianness、signedness、scaling formula、units 和 CRC/checksum rules。 |
| `shadow_state` | `_gain`、`_vref`、`_mode` 等 internal variables，以及每个变量归属的 setter。 |
| `ambiguities[]` | 需要用户确认或保守处理的 unresolved facts。 |

不要只根据非结构化 notes 生成 production driver。如果 understanding 不完整，返回 `DATASHEET_PARSE_INSUFFICIENT` 并保存 checkpoint。

## Debug Driver Requirements

生成 `project/firmware/drivers/<chip>_driver/<chip>_debug.py`，作为单文件快速迭代版本。它应该 verbose、可在设备上运行，并且便于修复。

必须满足：

- 打印 ASCII/English self-test messages。
- 如果使用 `const(...)`，必须 `from micropython import const` 或提供 MicroPython-safe fallback；不要依赖隐式全局 `const`。
- `const(...)` 只用于 integer constants。float constants、scale factors 和 sensitivity values 必须使用普通变量，例如 `_MGAUSS_PER_LSB = 1.5`，不要生成 `const(1.5)`。
- 在文件头打印 source evidence，例如 datasheet page/table 或 Arduino line。
- 使用 bus 前先校验 constructor arguments。
- 使用外部注入的 I2C/SPI/UART objects；不要在 driver class 内部实例化 board pins。
- 对 I2C，不要用 `isinstance(i2c, I2C)` 限死 bus 类型；使用 capability/duck typing 检查，让 `machine.I2C` 和 `SoftI2C` 兼容对象都可用。
- 初始化时通过 reset 或显式 configuration confirmation，让芯片进入 known state。
- 对 I2C，尽可能 scan 并验证 expected address。
- 对 I2C，`scan()` 只能和 7-bit expected address 比较；如果 datasheet evidence 是 `0x3C/0x3D`，debug driver 仍应检查 `0x1E`。
- 对 SPI，验证 CS handling，并读取 known register 或 safe read-back。
- 对 UART，在适用时发送 `AT` 等 known command 并验证 response。
- 如果存在 ID register，读取并比对 expected value。
- 如果没有 ID register，用 safe register read/write sanity check 替代。
- 将 write-only registers 标注为 `write-only`，并跳过 read-back。
- datasheet 提供 ready signal 时，优先使用 ready/status-bit polling with timeout，而不是 fixed sleeps。
- 只有没有 ready signal 时才使用 fixed sleeps；延时应包含 conversion time plus margin。
- 芯片提供 CRC/checksum 时必须验证。
- 失败时打印 expected vs actual values。
- 失败时打印 wiring/power/protocol hints。
- 捕获底层 `OSError`，并 raise 或 print 带 address、register 和 operation 的描述性上下文。
- 每个 wait/poll loop 都必须用 `ticks_ms()`/`ticks_diff()` 或固定 iteration count 限界。
- 重复 bus I/O 尽量预分配 bytearrays。
- self-test 成功时以 `SELF_TEST_PASS` 结束；否则打印 `SELF_TEST_FAIL: <reason>`。

## Hardware Verification Gate

硬件验证是生成 production driver 前的正常门禁。

Plugin-mode behavior:

- scan ports 或 devices 前，请求 `permission_request(device_scan)`。
- 运行 `run_on_device.py` 或 `mpremote` 前，请求 `permission_request(device_run)`。
- 如果 host 缺少 `serial_port_scan`、`device_command` 或 `mpremote_run` 能力，返回 `HOST_CAPABILITY_MISSING` partial，不要伪造 device scan 或写成 `DEVICE_NOT_FOUND`。如果 device scan 已被授权并执行但未发现目标设备，返回 `DEVICE_NOT_FOUND`。
- 使用 `scripts/run_on_device.py --com <port> --file <debug.py> --capture --timeout-ms <ms> --json-summary`。
- repair verification 最多 10 轮。
- 每轮 run log 保存为 `gen_driver/logs/driver_verify_round<N>.log`。
- 出现 `SELF_TEST_PASS` 时，checkpoint 到 `hardware_verify_passed`。
- 无设备、timeout、permission denial 或用户 cancellation 时，输出带 resumable checkpoint 的 partial。
- 无设备或 verification 未通过时，不要在 `file_manifest.files[]` 中把 `{chip}.py` 标记为 `production_driver`，除非用户明确 skip verification 且输出包含 warning 和 skip metadata。
- 无设备、timeout、permission denial 或用户 cancellation 的 partial 必须写 `hardware_verified=false`、`verification_mode="none"`、`next_phase=null`，并把 `resume_step` 指向下一次可执行的验证步骤。
- 如果 UI/CLI 表格展示未验证 `{chip}.py`，Role 必须显示 `Driver artifact (unverified)` 或 `Unverified driver artifact`；不要显示 `Production driver (unverified)`。

只有满足下面任一条件，才允许生成 production driver：

| Condition | Required output |
|---|---|
| Real hardware verification passed | `hardware_verified=true`，不需要 warning。 |
| User explicitly skipped hardware verification | `hardware_verified=false`，必须有 warning artifact 和 structured note。 |
| Local mock returned `SELF_TEST_PASS` | 标记为 mock verification；不要宣称 real hardware proof。 |

不要因为设备不可用，就从 debug generation 静默跳到 production success。

## Production Driver Requirements

只有通过上面的 hardware gate 后，才能生成 `project/firmware/drivers/<chip>_driver/<chip>.py`。

从 `upy-gen-driver` 继承的 production driver rules：

- 移除 debug banners 和 step-by-step prints。
- 可保留简洁 diagnostic methods，例如 `_self_test()` 或 `scan()`，但不要默认运行。
- 保留带 register/address/action context 的有意义 exception messages。
- 代码组织顺序为 constants、class、`__init__`、public methods、private helpers 和 `deinit()`。
- 保持 I2C/SPI/UART dependency injection。
- I2C address constants 必须是 7-bit address，例如 `_I2C_ADDR = const(0x1E)`；不要把 `_I2C_ADDR_WRITE = const(0x3C)` 或 `_I2C_ADDR_READ = const(0x3D)` 作为实际 API 调用地址。
- I2C driver 必须通过 duck typing 接受 `machine.I2C`、`SoftI2C` 或兼容对象；不要通过 strict `isinstance(i2c, I2C)` 拒绝 `SoftI2C`。
- 生成 `{chip}.py`、`{chip}_debug.py` 和 `test_{chip}.py` 后，必须执行静态质量检查：Python syntax、未定义常量/名称、helper method 调用参数数量、I2C capability check 与实际 I/O API 使用一致性。
- 静态质量检查和 PC-side compile/test 必须禁止写入 `__pycache__` 或 `.pyc` 到 session/project artifacts；运行 CPython 检查时使用 `python -B` 或等价方式。
- 不要让 debug driver 和 production driver 的 constant 命名风格漂移；如果 debug driver 使用 `_ODR_10HZ` / `_MD_IDLE`，production driver 要么定义同名常量，要么全部改为 `ODR_10HZ` / `MODE_IDLE` 并同步所有引用。
- helper method 签名必须覆盖所有调用形式；例如代码调用 `_read_reg(reg, buf)` 时，定义必须是 `def _read_reg(self, reg, buf=None)` 或等价形式。
- I2C constructor capability check 必须覆盖实际使用的方法；如果 helper 调用 `readfrom_mem_into`，不要只检查 `readfrom_mem`。
- 在 `__init__` 中校验 argument types 和 ranges。
- 在 `__init__` 中让芯片进入 known state。
- 按 setter 独立追踪 shadow state；`set_gain()` 不得修改 `_vref`，`set_vref()` 不得修改 `_gain`。
- 可行时，在 hardware write 成功后再更新 shadow state。
- datasheet 支持 standby/powerdown 时，实现 `deinit()`。
- device code 不要依赖 CPython-only modules。
- hot read loops 中尽量避免 dynamic allocation。
- datasheet page/table comments 只用于解释 constants、timing、formulas 或 register behavior，不要写成教程。

然后运行 `references/norm_driver_p0_rules.md` 中的 P0 normalization checklist，并用 `scripts/validate_phase_complete.py --input <phase_complete> --artifact-root <session_root> --session-state <state_file>` 校验真实文件内容。`--session-state` 必须传入，不能只校验 phase_complete JSON。validator 会检查 state 完整性、permission paths、device error evidence、用户可见文本编码质量、未验证文案、CPython cache artifacts 和真实文件 hash；失败时不要输出可继续集成的结果。

## Checkpoints

使用这些稳定 checkpoint names：

`started`, `input_collected`, `source_preprocessed`, `understanding_written`, `debug_driver_written`, `hardware_verify_ready`, `hardware_verify_passed`, `production_driver_written`, `normalized`, `standalone_assets_written`, `standalone_test_passed`, `manifest_updated`, `phase_completed`, `cancelled`, `verification_exhausted`.

`phase_complete.payload.checkpoint.checkpoint_id` 必须使用 `upy-gen-driver-plugin:<session_id>:<checkpoint_name>`。例如 `upy-gen-driver-plugin:8234517f-d65a-4620-a391-3936c7c9eda4:hardware_verify_ready`；不要只写 `upy-gen-driver-plugin:hardware_verify_ready`。

必须使用下面命令维护 state：

```bash
python scripts/update_session_state.py --session-dir <session_root> --session-id <session_id> --checkpoint <name> --step <step> --status running --idempotency-key <key>
python scripts/update_session_state.py --session-dir <session_root> --check
```

Resume rules:

- 要求 `session_id`、`phase`、`protocol_version` 和 checkpoint name 一致。
- `session_state.upy_gen_driver_plugin.json` 中的当前 checkpoint 必须和 `phase_complete.payload.checkpoint.checkpoint_id` 的 checkpoint 部分一致；partial 结果尤其不能把 state 写成 `phase_completed`。
- 如果存在 hash，必须验证 last trusted artifact 存在且 hash 匹配。
- 如果 checkpoint 之后 manifest hash 发生变化，返回 `ARTIFACT_STALE`，或退回到上一个 safe checkpoint。
- 当目标文件 hash 已经匹配时，不要重复执行已完成的 write。
- 保持 `verify_round < max_verify_rounds`；耗尽时 checkpoint 到 `verification_exhausted` 并返回 partial。

## Retry, Cancellation, and Timeout

使用下面的结果形态：

| Event | State update | Final or next message |
|---|---|---|
| 用户重试 | `status="retrying"`，同一 checkpoint，同一 action idempotency key，`retry_of=<msg_id>` | 重新发出 action request，或从 checkpoint 继续 |
| LLM repair retry | 增加 `verify_round`，保持 session，写入 verify log | 继续直到 pass 或 `verification_exhausted` |
| 用户取消 | `status="cancelled"`，checkpoint `cancelled` | `phase_complete.result="partial"`，并携带 `CANCELLED_BY_USER` |
| Approval timeout | `status="partial"`，回到前一个 safe checkpoint | `APPROVAL_TIMEOUT` 或 `DEVICE_RUN_TIMEOUT` structured error |
| Script timeout | 根据策略设置 `status="partial"` 或 `retrying` | `SOURCE_PREPROCESS_TIMEOUT` 或 `DEVICE_RUN_TIMEOUT` |
| Capability missing | `status="partial"` | `HOST_CAPABILITY_MISSING`，并在 details 中写明 missing capability |

Timeout defaults:

- approval/input card: `300000`
- PDF extraction: `30000`
- Arduino conversion: `15000`
- GitHub/datasheet fetch: `30000`
- device scan: `5000`
- device debug run: host `60000`, device script `30000`
- standalone test: host `30000`, device script `15000`

## Structured Errors

使用 `references/protocol_fields.md` 中的稳定 code。重要 code 包括 `MISSING_INPUT_SOURCE`、`HOST_CAPABILITY_MISSING`、`PERMISSION_DENIED`、`SOURCE_PREPROCESS_FAILED`、`SOURCE_PREPROCESS_TIMEOUT`、`DEVICE_NOT_FOUND`、`DEVICE_RUN_TIMEOUT`、`HARDWARE_VERIFY_FAILED`、`HARDWARE_VERIFY_EXHAUSTED`、`STANDALONE_TEST_FAILED`、`MANIFEST_UPDATE_CONFLICT`、`ARTIFACT_STALE` 和 `CANCELLED_BY_USER`。

每个 error 都必须包含 `code`、`severity`、`phase_step`、`retryable`、`message`、`details` 和 `next_action`。

## Required Artifacts

success 时，如果已生成对应文件，必须把下面内容写入 `payload.file_manifest.files[]`：

- `gen_driver/docs/driver_understanding.json`
- `project/firmware/drivers/<chip>_driver/<chip>_debug.py`
- `project/firmware/drivers/<chip>_driver/<chip>.py`
- `project/firmware/drivers/<chip>_driver/test_<chip>.py`
- `project/firmware/drivers/<chip>_driver/wiring_<chip>.md`
- `gen_driver/logs/driver_verify_round<N>.log` 或 explicit skip-verification artifact
- `session_state.upy_gen_driver_plugin.json`
- `pipeline` 模式下的 `project/project-manifest.json`

`phase_complete.upy_gen_driver_plugin.json` 是最终协议 envelope，不要求放进自己的 `payload.file_manifest.files[]`。如果需要审计它，由 host 或外部 sidecar manifest 记录；不要为了自引用 hash 把它强塞进自身 file manifest。

partial 时，必须包含 last trusted artifact 和可从中 resume 的 checkpoint。

`file_manifest.files[]` 中每个已存在或已生成文件都必须包含真实 `sha256` 和 `bytes`。不要使用 `"hash": "unverified"` 或其他占位字段替代 `sha256`。
不要手算最终 manifest。`session_state.upy_gen_driver_plugin.json` 也在 manifest 中时，必须在最后一次 state 更新之后再计算它的 `sha256` 和 `bytes`；如果 state 被再次修改，必须重新运行 `scripts/finalize_phase_complete.py`。
`payload.artifacts[]` 中必须包含非空 `file_list`，其 `files[]` 或 `items[]` 至少列出本次产生或保留的可信文件；不要只给 `title`、`label` 或空数组。

## Local Mock Testing

本地测试可以写文件，但也必须在 `sessions/<session_id>/gen_driver/` 下写出协议 artifacts。使用：

```bash
python test/smoke_tests.py
python test/run_local_mock_session.py --mode standalone --scenario no_device
python test/run_local_mock_session.py --mode standalone --scenario cancelled
python test/run_local_mock_session.py --mode standalone --scenario timeout
python test/run_local_mock_session.py --mode standalone --scenario retry_success
python scripts/finalize_phase_complete.py --input <draft_phase_complete> --output <session_root>/phase_complete.upy_gen_driver_plugin.json --artifact-root <artifact_root> --session-state <session_root>/session_state.upy_gen_driver_plugin.json
python scripts/validate_phase_complete.py --input sample/phase_complete.upy_gen_driver_plugin.partial.no_device.json
```

不要把 mock outputs 当成真实硬件验证证明。`no_device`、`cancelled`、`timeout` 都必须使用 `verification_mode="none"`；只有 `retry_success` 这类本地 mock self-test 成功路径才可以使用 `verification_mode="mock"`，并且必须带 `MOCK_VERIFICATION_ONLY` warning。

Minimum local coverage:

- `no_device`: partial checkpoint at `hardware_verify_ready`, `DEVICE_NOT_FOUND`。
- `missing_device_capability`: partial checkpoint at `hardware_verify_ready`, `HOST_CAPABILITY_MISSING`，`details.missing_capability` 指向缺失能力。
- `cancelled`: partial checkpoint `cancelled`, `CANCELLED_BY_USER`。
- `timeout`: partial checkpoint at `hardware_verify_ready`, `DEVICE_RUN_TIMEOUT`。
- `retry_success`: 第一次 device run timeout，retry 保持同一个 session，并带 `retry_of` 产出 success。
- idempotency: 重跑同一个 action 时，不得重复 file manifest entries，也不得覆盖已经 hash 匹配的文件。
