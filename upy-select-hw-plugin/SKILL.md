---
name: upy-select-hw-plugin
description: 插件化工作流版 select-hw。消费 upy-analyze-plugin 的 phase_complete.payload.manifest_content，完成板卡/MCU 确认、MicroPython 固件核验、引脚分配和 BOM，输出 phase_complete(select-hw) 给 MPY 固件烧录阶段。
---

# 插件化工作流版硬件选型与引脚分配 Skill

## 角色定位

`upy-select-hw-plugin` 是长期工作流协议中的 `select-hw` phase。它承接 `upy-analyze-plugin` 的阶段产物，并为后续“对应 MCU 的 MicroPython 固件烧录步骤”准备硬件事实。

本 phase 只负责：

- 读取 `phase_complete(analyze).payload.manifest_content`
- 基于 `requirements` 和 `devices` 选择/确认 MicroPython 开发板
- 核验固件下载入口与烧录工具类型
- 根据板卡 `pin_layout` 和器件接口分配引脚
- 生成 BOM 和估算总价
- 通过 `select_hw_manifest.py` 校验/规范化
- 输出 `phase_complete(select-hw)`，`next_phase` 固定为 `upy-flash-mpy-firmware-plugin`

本 phase 不负责：

- 重新分析用户自然语言
- 搜索或生成驱动
- 生成业务代码
- 烧录设备
- 直接用本地写盘结果作为阶段事实源

## 输入事实源

正式输入是上游消息：

```text
phase_complete(analyze).payload.manifest_content
```

直测时允许从 session 目录读取 `phase_complete.analyze.json`，但仍必须取其中的 `payload.manifest_content`。不要从 `manifest_draft.json`、日志或旧 conversation 推断项目状态。

当前 `upy-analyze-plugin` 真实直测产物采用 session 隔离：

```text
sessions/<session_id>/
  manifest_draft.json
  manifest_validated.json
  phase_complete.analyze.json
  driver_search_log.md
  analyze_phase_log.md
```

正式消费顺序：

1. 首选 `phase_complete.analyze.json` 的 `payload.manifest_content`
2. 直测 fallback 可读 `manifest_validated.json`
3. `manifest_draft.json`、`driver_search_log.md`、`analyze_phase_log.md` 只作排查参考

`start_phase.payload.user_pin_constraints` 可选。插件或上游 analyze 若已解析到用户指定引脚，必须用结构化数组传入 select-hw。每项至少包含 `device`、`device_pin`、`mcu_pin`、`signal`，可选 `voltage`、`notes`。

## 路径与 root 约定

必须区分三个 root：

| root | 含义 | 允许内容 |
| --- | --- | --- |
| `resource_root` | skill/resource 所在根，通常是 `G:\MicroPython_Skills` 或已安装的 `.claude/skills` 父级 | `upy-select-hw-plugin`、`upy-analyze-plugin/boards` |
| `artifact_root` | 当前项目/测试输出根，例如用户传入的 `G:\test\test`；`phase_complete.payload.artifacts.file_list.files[].path` 默认相对它解析 | `sessions/<session_id>` 及 phase 产物 |
| `session_root` | 当前 session 目录 | `select_hw_*.json`、`phase_complete.select_hw.json`、日志 |

资源加载必须以 `resource_root` 为基准使用相对路径，例如：

```text
upy-analyze-plugin/boards
upy-analyze-plugin/sample/phase_complete.analyze.success.json
upy-select-hw-plugin/scripts/select_hw_manifest.py
upy-select-hw-plugin/sample/phase_complete.select_hw.success.json
```

产物写入必须以 `artifact_root` 或 `session_root` 为基准使用相对路径，例如：

```text
sessions/<session_id>/select_hw_draft.json
sessions/<session_id>/select_hw_validated.json
sessions/<session_id>/phase_complete.select_hw.json
```

`artifact_root` 是“本次运行产物根目录”，不是 skill/resource 根目录。例如 `artifact_root=G:\test\test` 时，artifact path 应写 `sessions/<session_id>/select_hw_draft.json`；如果宿主把 `artifact_root` 设置为当前 `session_root`，artifact path 才应写 `select_hw_draft.json`。校验命令、phase log 和 file manifest 必须使用同一个 root 口径。

用户传入的项目目录（例如 `G:\test\test`）默认是 `artifact_root`，不是 `resource_root`。不得因为 `artifact_root` 下缺少 `upy-select-hw-plugin` 或 `upy-analyze-plugin`，就把 skill 脚本、boards 目录或半截 skill 复制到 `artifact_root`。

不要在协议、脚本参数或样例里把 `G:\MicroPython_Skills` 写成业务依赖。测试命令可以在文档里展示绝对路径，但实现要用 `resource_root / relative_path` 读取资源，用 `artifact_root / relative_path` 写产物。

phase log、命令历史和 artifact 描述也必须使用相对路径。不要把本机插件安装目录（例如用户目录下的 skill/plugin 路径）写成业务事实源。

如果宿主只能在 artifact workspace 内执行脚本，必须显式把 `resource_root` 作为只读资源路径传入，或者由宿主提供 script execution capability；不得通过复制 `upy-select-hw-plugin/scripts` 到 artifact workspace 来伪造相对路径。

### runtime_context 约定

Claude Code / 插件运行时必须通过 `phase_complete.payload.runtime_context` 传递当前工作目录和 session 目录口径，skill 不得自行猜测根目录：

```json
{
  "runtime_context": {
    "artifact_root": ".",
    "artifact_root_mode": "cwd",
    "session_root": "sessions/<session_id>",
    "resource_root": "<runtime-provided>"
  }
}
```

字段约束：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `artifact_root` | 是 | 产物根目录，默认 `.`（当前工作目录） |
| `artifact_root_mode` | 是 | `cwd` 或 `session_root` |
| `session_root` | 是 | 当前 session 目录的相对路径 |
| `resource_root` | 是 | skill/resource 所在根（由运行时提供） |

路径口径规则：

- `artifact_root_mode=cwd` 时，`file_list.files[].path` 必须相对当前工作目录，格式为 `sessions/<session_id>/<filename>`。
- `artifact_root_mode=session_root` 时，才允许裸文件名（如 `select_hw_draft.json`）。
- 同一个 `phase_complete` 内不能混用两种路径口径。
- `runtime_context` 缺失时，校验视为 error。

## 时间规则

所有时间字段必须来自运行时统一时间源，禁止手写占位时间：

- `timestamp` — 由 Claude Code / 插件运行时注入，或通过 `upy-project-gen-toolchain-spec/scripts/workflow_time.py` 获取。
- `pin_review.confirmed_at` — 必须是用户确认发生的真实 UTC 时间，禁止日期零点或样例占位值。
- `manifest_content.created_at` / `updated_at` — 由 `select_hw_manifest.py` 规范化时自动生成。
- 所有时间字段必须是 ISO-8601 格式，带 UTC 时区（`Z` 后缀）。

`confirmed_at` 写入顺序：必须先写回 `select_hw_draft.json`，再以 draft 为单一事实源生成 `select_hw_validated.json` 和 `phase_complete.select_hw.json`。

`phase_complete.timestamp` 必须在脚本校验通过后重新调用 `workflow_time.py --json` 获取，确保 ≥ 所有引用 artifact 的 `updated_at` 和 `created_at`。禁止复用 `pin_review.confirmed_at` 或更早时间作为 `phase_complete.timestamp`。

## 长期协议要求

所有正式消息必须使用完整 envelope：

```json
{
  "protocol_version": "1.0",
  "msg_id": "uuid",
  "session_id": "uuid",
  "phase": "select-hw",
  "timestamp": "<runtime-utc-now>",
  "type": "status_update",
  "idempotency_key": "select-hw:<session_id>:step:v1",
  "retry_of": null,
  "payload": {}
}
```

字段约束：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `protocol_version` | 是 | V0 固定为 `"1.0"` |
| `msg_id` | 是 | 当前消息 UUID |
| `session_id` | 是 | 由插件创建，phase 继承 |
| `phase` | 是 | 当前 phase，固定 `select-hw` |
| `timestamp` | 是 | UTC ISO 时间 |
| `type` | 是 | 消息类型枚举 |
| `idempotency_key` | 建议 | 同一动作 retry 时保持不变 |
| `retry_of` | 可选 | 指向原始失败消息 |

消息类型枚举：

```text
start_phase
status_update
approval_request
approval_response
script_run
script_result
file_operation
file_result
device_command
device_result
phase_complete
```

## capability negotiation

启动前应知道宿主能力：

```json
{
  "capabilities": {
    "protocol_versions": ["1.0"],
    "approval_request": true,
    "script_run": true,
    "file_operation": true,
    "device_command": false,
    "artifact_root": true,
    "relative_paths": true
  }
}
```

V0 不需要 `device_command`。如果宿主不支持 `approval_request` 或 `script_run`，不得宣称 select-hw 成功。

## 标准消息序列

```text
Step 0 读取上游 manifest
  -> status_update(upstream_manifest_loaded)

Step 1 板卡候选生成
  -> status_update(board_matching)
  -> approval_request(board_select)  # pre_selected_board 来自插件 UI 时可跳过；板卡库缺失时改发 board_unavailable
  <- approval_response

Step 1B 加载完整板卡定义
  -> status_update(board_definition_loaded)
  从 upy-analyze-plugin/boards/<selected_board.id>.json 加载完整 board JSON
  若不存在或缺 pin_layout：
    -> approval_request(board_unavailable 或 board_select)

Step 2 固件核验
  -> status_update(firmware_check)
  -> status_update(firmware_ok)

Step 3 引脚分配
  -> status_update(pin_assignment)
  若候选板卡缺 pin_layout：
    -> 选择功能类似且有 pin_layout 的已知板卡
    -> approval_request(board_select)
  若存在 start_phase.payload.user_pin_constraints 或 approval_response.payload.user_pin_constraints：
    -> 优先按用户指定引脚生成 pinout/pin_decisions；`pinout[].source` 必须为 `user_wiring`
  -> status_update(pin_assignment_draft_ready)

Step 3B 引脚方案确认
  -> approval_request(pin_plan_review)
  用户确认后：
    -> status_update(pin_assignment_done)
  用户要求调整或不确认：
    -> phase_complete(result=partial, checkpoint.resume_step=pin_assignment)

Step 4 BOM 生成
  -> status_update(bom_ready)

Step 5 manifest 校验/规范化 (第 1 次: draft → validated)
  -> script_run(select_hw_manifest.py --input <draft> --write-path <validated> --board-root ...)
  <- script_result

Step 6 manifest 内容二次校验 (第 2 次: validate manifest_content)
  -> script_run(select_hw_manifest.py --validate-manifest-content --input <validated> --board-root ...)
  <- script_result

Step 7 获取阶段完成时间戳
  -> 调用 workflow_time.py --json 获取当前 UTC 时间
  <- phase_timestamp = <utc-now>

Step 8 phase_complete 最终校验与输出 (第 3 次: validate phase_complete)
  -> script_run(select_hw_manifest.py --validate-phase-complete --input <phase_complete.json> --compare-manifest <validated> --artifact-root ... --expected-artifact ...)
  <- script_result
  -> 校验通过后输出 phase_complete(timestamp=<phase_timestamp>, result=success, next_phase=upy-flash-mpy-firmware-plugin)
```

## status_update 枚举

level 只使用：

```text
info
warn
error
success
```

step_id 枚举：

```text
upstream_manifest_loaded
board_matching
board_unavailable
board_definition_loaded
board_definition_invalid
board_selected
board_change_requires_restart
firmware_check
firmware_ok
pin_assignment
pin_assignment_draft_ready
pin_plan_review
pin_risk_detected
pin_conflict
pin_assignment_done
bom_ready
manifest_validation
```

## approval_request: board_select

`requirements.mcu_specified` 表示 MCU/芯片/模组型号，不等于具体开发板，因此默认必须弹 `board_select`。如果 `pre_selected_board` 已经来自插件 UI，可跳过，但必须记录跳过原因并校验该板卡存在固件和 `pin_layout`。

板卡确认边界：

- `select-hw` 只允许在上游 `requirements` 已确定的 MCU/芯片/模组兼容范围内确认具体开发板，或者在未指定 MCU 时从候选池中选择。
- 如果用户在 `select-hw` 中要求跨 MCU、跨芯片族、跨固件目标或明显改变主控能力边界的板卡更换，不得静默改写上游需求并输出 `success`。
- 这类变更必须输出 `partial`，`next_phase=null`，`checkpoint.resume_step=load_upstream_manifest` 或 `board_select`，`reason=board_change_requires_analyze`，并提醒用户新建对话或重新运行 analyze/select-hw。
- 通用判定依据是上游 `requirements.mcu_specified`、已确认的 `pre_selected_board`、候选板卡 `mcu`、`chip_family`、`firmware.board_name` 是否仍兼容；规则不得写成某个 MCU 的特例。

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "board_select",
    "header": "确认主控板卡",
    "question": "请确认用于该项目的 MicroPython 开发板",
    "summary": {
      "project_name": "语音对话助手",
      "mcu_specified": "ESP32-C3",
      "source_phase": "analyze"
    },
    "items": [
      {
        "id": "esp32-c3-devkitm",
        "name": "ESP32-C3-DevKitM-1",
        "subtitle": "WiFi/BLE, MicroPython ESP32_GENERIC_C3",
        "meta": "匹配上游 MCU 偏好",
        "selected": true
      }
    ],
    "multi_select": false,
    "actions": [
      {
        "label": "确认板卡",
        "value": "confirm",
        "primary": true
      },
      {
        "label": "稍后继续",
        "value": "save_partial"
      }
    ]
  }
}
```

用户取消或选择稍后继续时，输出：

```text
result = partial
next_phase = null
checkpoint 必填
```

## approval_request: board_unavailable

当用户指定的具体板卡或 `pre_selected_board.id` 不在 `upy-analyze-plugin/boards` 中时，不要直接失败。先按同系列、同 `chip_family`、相同固件 port、相近功能需求排序，推荐一个已知且有 `pin_layout` 的替代板卡；同时给用户保留手动描述接线的选项。

必须提供这些互斥动作：

| action value | 含义 | 后续行为 |
| --- | --- | --- |
| `use_recommended_similar` | 使用系统推荐的同系列/相似功能已知板卡 | 继续固件核验和引脚分配 |
| `select_known_board` | 用户改选板卡库中的其他已知板卡 | 重新进入 `board_select` |
| `manual_wiring_description` | 用户手动描述“MCU 引脚 -> 器件引脚” | 产出 partial/checkpoint，等待用户补充结构化接线 |
| `save_partial` | 暂停 | 产出 partial/checkpoint |

手动接线描述要求用数组表达，每条记录说明 `mcu_pin`、`device`、`device_pin`、`signal`、`voltage`、`notes`。示例：`GPIO21 -> AHT20 SDA`、`3V3 -> AHT20 VCC`、`GND -> AHT20 GND`。

## approval_request: pin_plan_review

引脚分配不能只依赖 LLM 的一次性推断。V0 采用“脚本只拦硬错误 + 用户确认方案”的简化策略：生成初步 `pinout` 和 `pin_decisions` 后，必须让用户确认引脚方案，提醒用户查看官方原理图、板卡丝印、模块版本和外设数据手册。用户确认前不得输出 `phase_complete(result=success)`。

必须提醒用户重点核查：

- 默认总线引脚是否真实引出、是否与其他器件冲突
- `restricted_gpio`、boot/strapping、flash/PSRAM、USB/JTAG/REPL/UART 占用
- `onboard_peripherals` 是否真实占用该 GPIO，是否可释放
- 外设模块的 VCC/GND/配置脚是否是 MCU 控制还是硬接电源/地
- 板卡变体差异、原理图版本、丝印和实际模组是否一致

动作枚举：

| action value | 含义 | 后续行为 |
| --- | --- | --- |
| `confirm_pin_plan` | 用户确认引脚方案可按当前草案继续 | 继续 BOM 与最终校验 |
| `revise_pin_plan` | 用户要求重新分配一个或多个引脚 | 回到 `pin_assignment` |
| `manual_wiring_description` | 用户手动描述接线 | 产出 partial/checkpoint，等待结构化接线 |
| `save_partial` | 暂停 | 产出 partial/checkpoint |

当用户选择 `revise_pin_plan` 或 `manual_wiring_description` 时，插件应在 `approval_response.payload.user_pin_constraints` 返回结构化引脚约束：

```json
{
  "approval_id": "pin_plan_review",
  "action": "revise_pin_plan",
  "user_pin_constraints": [
    {
      "device": "AHT20",
      "device_pin": "SDA",
      "mcu_pin": "GPIO21",
      "signal": "i2c_data",
      "voltage": "3.3V",
      "notes": "用户指定 SDA"
    }
  ]
}
```

`user_pin_constraints[]` 字段含义：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `device` | 是 | 器件名，必须能对应上游 `devices[].name` 或当前 `pinout[].device` |
| `device_pin` | 是 | 器件侧引脚/信号名，如 `SDA`、`SCL`、`OUT`、`DIN`、`VCC`、`GND` |
| `mcu_pin` | 是 | 用户指定的 MCU/板卡侧引脚。GPIO 可写 `GPIO21` 或 `21`；电源/地可写 `3V3`、`5V`、`GND` |
| `signal` | 是 | 引脚功能类型，应映射到 `pinout[].type`，如 `i2c_data`、`i2c_clock`、`gpio_in`、`gpio_out`、`uart_tx`、`uart_rx`、`power_3v3`、`gnd` |
| `voltage` | 否 | 电压说明，如 `3.3V`、`5V`、`0V`，仅用于校验提示和 notes |
| `notes` | 否 | 用户说明或插件 UI 备注 |

处理规则：

- 将合法的 `user_pin_constraints[]` 转换为 `pinout[]`，并设置 `pinout[].source="user_wiring"`。
- 同步生成 `pin_decisions[]`，并设置 `decision_type="user_wiring"`、`source="user_wiring"`。
- `mcu_pin` 中的 `GPIO21` 和 `21` 视为同一个 GPIO；电源/地必须保持为 `3V3`、`5V`、`GND`。
- 缺少必填字段时，不要继续 success；输出 `partial`，`checkpoint.resume_step=pin_assignment`。
- 用户指定引脚仍必须通过 board JSON 校验；非法引脚不得静默改写。

payload 必须包含：

```json
{
  "approval_id": "pin_plan_review",
  "header": "确认引脚分配",
  "summary": {
    "board_id": "selected-board-id",
    "board_definition": "upy-analyze-plugin/boards/<board_id>.json",
    "requires_schematic_review": true
  },
  "pinout": [],
  "pin_decisions": [],
  "warnings": []
}
```

确认后写入 `hardware_plan.pin_review`：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `approval_id` | 是 | 固定 `pin_plan_review` |
| `confirmed` | 是 | 用户是否确认；`success` 前必须为 `true` |
| `confirmed_by` | confirmed=true 时必填 | 用户、插件 UI 或审批来源 |
| `confirmed_at` | confirmed=true 时必填 | 本次确认发生的真实 UTC 时间，ISO-8601 格式；不得使用样例占位时间或日期零点 |
| `source` | 是 | `approval_response`、`plugin_ui_confirmed`、`user_confirmed` |
| `note` | 可选 | 用户确认或调整说明 |

## 板卡数据

V0 复用相对路径：

```text
upy-analyze-plugin/boards
```

不要复制板卡数据到 `artifact_root`，除非后续 select-hw 需要独立扩展 schema。测试 staging 如确需复制，必须复制完整 `boards` 目录（至少包含所有 board json 与 `matching-rules.json`），不得只复制当前选中的单个 board JSON；否则会破坏未指定 MCU、候选排序、相似板卡推荐和 board_unavailable 流程。

处理策略：

- 候选生成阶段必须枚举 `resource_root/upy-analyze-plugin/boards/*.json` 的完整板卡库，跳过 `_template.json` 和说明文档；不能只加载 selected board。
- `requirements.mcu_specified` 存在时，按 `mcu`、`chip_family`、`firmware.board_name` 匹配候选。
- `pre_selected_board` 已来自插件 UI 时可跳过确认，但仍需校验。
- `selected_board.id` 必须对应 `upy-analyze-plugin/boards/<id>.json`。确认板卡后必须加载完整 board JSON，不允许只凭 MCU 名称或 `selected_board` 摘要分配引脚。
- 完整 board JSON 是 `firmware`、`pin_layout`、`restricted_gpio`、`onboard_peripherals` 的事实源。`selected_board` 只能作为 UI 摘要。
- 未指定 MCU 时，候选池必须优先限制在 Pico/RP2 系列和 ESP32 系列；除非需求明确需要其他系列，不要优先推荐 STM32、Teensy、Pyboard 等板卡。
- 未指定 MCU 的默认排序：Pico/Pico W、ESP32 DevKit、ESP32-S3、ESP32-C3；按需求加分后输出 Top 1 和 Top 2 备选。
- 需要 WiFi/BLE 时加分 ESP32 系列和 Pico W；需要 AI/语音/摄像头时加分 ESP32-S3；低功耗/电池供电加分 ESP32-C3；纯 GPIO 或新手入门加分 Pico/Pico W；极致低价可加分 ESP8266/Pico，但 ESP8266 不应压过 Pico/ESP32，除非预算是唯一主约束。
- 用户指定板卡不存在于板卡库时，优先推荐同系列或功能相似且有 `pin_layout` 的已知板卡；同时发 `approval_request(board_unavailable)`，允许用户改选已知板卡或手动描述接线。
- 用户在 `select-hw` 中要求跨 MCU/芯片族/固件目标更换板卡时，不要继续成功产物；输出 partial/checkpoint，要求新建对话或回到 analyze 阶段重新确认需求。
- 缺少 `pin_layout` 时，默认换功能类似且有 `pin_layout` 的已知板卡。
- `cold-driver` 不影响 MCU 推荐、引脚分配或 BOM，只增加 warnings。
- select-hw 不负责确认 MicroPython 固件的实时最新版本。板卡库中的固件版本只能视为缓存信息；正式烧录阶段再访问 `firmware.url` 检查最新 release。select-hw 输出重点保留 `firmware_url`、`firmware_board_name`、`flash_tool`。

## 引脚分配规则

基础规则：

- I2C 器件默认共享一条 I2C 总线并优先使用 `pin_layout.default_bus_pins`；若 `i2c_addr` 冲突，改用第二条 I2C 或输出 partial。
- SPI 器件共享 MOSI/MISO/SCK，每个器件独立 CS，并优先使用 `pin_layout.default_bus_pins`。
- UART 避开 REPL/USB 串口。
- I2S 需要分配 BCK/WS/DIN/DOUT；麦克风和功放可共享 BCK/WS，但数据方向不同。
- ADC 只能用 ADC-capable pin。
- GPIO 避开 boot/strapping、flash/PSRAM、USB OTG、只读脚；条件可用脚可以进入方案，但必须在 warnings/notes 和 `pin_plan_review` 中提示用户核对。
- 电源与 GND 必须进入 `pinout`。
- 如果 board JSON 有 `pin_options`，重映射只能在 `pin_options` 允许范围内进行；如果是 flexible matrix，也必须避开硬禁用脚。条件可用脚不作为 schema 硬失败，交给 warnings 与用户确认处理。
- 偏离 `pin_layout.default_bus_pins` 必须在 `pinout[].notes` 和 warnings 中说明原因。
- 用户传入接线时，优先保留用户接线，但必须通过 board JSON 的 restricted/occupied 校验；非法用户接线不能静默成功。
- 用户指定引脚只表示偏好/约束，不表示跳过安全校验。若指定引脚命中 hard forbidden、输入输出方向不匹配、已被 `always_used` 板载外设占用，输出 `partial`，`checkpoint.resume_step=pin_assignment`，并在 `structured_errors` 中说明冲突原因；非法引脚不得静默改写，也不要自动换脚后继续 success。
- 板载器件与用户指定器件或系统推荐器件一致时，复用 `onboard_peripherals` 声明的板载默认/占用引脚，不重复分配外接 GPIO，也不重复加入 BOM。
- 板载器件与当前需求不一致时，`onboard_peripherals[].occupied_pins` 视为已占用资源，外接器件只能使用空余引脚。
- 如果用户要求释放板载器件占用脚，必须确认 `always_used=false`，并在 notes/warnings 中说明释放原因。
- `pin_assignment_log.md` 和 phase log 中的 GPIO 汇总必须从完整 board JSON 与最终 `pinout` 计算，不允许手写静态列表。V0 至少包含 `used_gpio`、`unused_gpio`、`restricted_or_occupied_gpio` 三组；不要把条件可用脚包装成绝对安全，只需在 warnings 中说明限制和确认点。
- 如果启用 WiFi 且使用了 `adc2_wifi_conflict` 中的 GPIO，必须完整列出所有相关 GPIO。只有 `pinout[].type=adc` 时是冲突；作为 I2C/I2S/GPIO 等数字信号使用时允许，但必须在 warnings 或 notes 中说明“WiFi 只影响 ADC 读数，不影响数字用途”。
- 使用板卡默认 UART/REPL/USB 串口相关引脚做普通 GPIO 时，必须确认该串口不用于调试/通信，或者把该占用写入 warning 并给出可重分配建议。

`restricted_gpio` 分级：

| board 字段 | 默认策略 | 校验级别 |
| --- | --- | --- |
| `flash_psram_occupied` | 禁止使用 | error |
| `reserved` / `internal_only` | 禁止使用 | error |
| `usb_serial_pins` | 默认禁止，除非明确不使用 USB 串口或用户显式接线 | error 或 warning |
| `strapping` / `boot` | 默认避开；必须使用时写入 warning 并交给 pin_plan_review | warning；strict 模式为 error |
| `input_only` | 只能用于输入类 pin type | error |
| `adc_only` | 只能用于 ADC 输入 | error |
| `adc2_wifi_conflict` | 仅在 `type=adc` 且 WiFi 启用时冲突；数字输入输出可用但应说明 | ADC 为 error；数字用途为 warning |
| `onboard_peripherals[].occupied_pins` | `always_used=true` 时禁止；否则默认避开或说明释放原因 | error 或 warning |

`pinout[].type` 枚举：

```text
power_3v3
power_5v
gnd
i2c_data
i2c_clock
spi_mosi
spi_miso
spi_sck
spi_cs
uart_tx
uart_rx
gpio_out
gpio_in
gpio_in_pullup
adc
pwm
i2s_bck
i2s_ws
i2s_data_in
i2s_data_out
wifi_internal
reserved
```

`pinout[]` 字段含义：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `device` | 是 | 连接的器件名，电源项可用 `power` |
| `pin_name` | 是 | 器件侧信号名，如 `SDA`、`SCL`、`VCC`、`GND`、`OUT` |
| `gpio` | 是 | MCU 侧 GPIO 编号或电源名，如 `8`、`3V3`、`GND` |
| `type` | 是 | 引脚电气类型，只能取上方 `pinout[].type` 枚举 |
| `bus` | 可选 | 总线编号，如 `i2c0`、`spi0`、`uart1`、`i2s0` |
| `i2c_addr` | 可选 | I2C 地址，用于冲突检测 |
| `physical_pin` | 可选 | 板卡丝印/物理引脚编号，板卡库有数据时填写 |
| `side` | 可选 | 引脚在板卡哪一侧，建议 `left/right/top/bottom` |
| `pos` | 可选 | 在 `side` 上的顺序位置，建议 0-based |
| `notes` | 可选 | 限制、复用或替代原因 |
| `source` | 建议 | 引脚来源，只能取 `default_bus`、`auto_assigned`、`user_wiring`、`onboard_peripheral`、`power` |

## pin_decisions 与 deviation

必须生成结构化 `pin_decisions[]` 并在最终 `manifest_content` 中保留。默认总线、自动分配、用户接线、板载器件复用、固定电源/地都要有对应 decision；自然语言 notes 只能补充说明，不能替代结构化证据。

`pin_decisions[]` 字段：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `device` | 是 | 器件名 |
| `pin_name` | 是 | 器件侧信号名 |
| `assigned_gpio` | 是 | 最终 MCU GPIO 或电源/地 |
| `decision_type` | 是 | 决策类型枚举 |
| `source` | 是 | `board_default`、`auto_assigned`、`user_wiring`、`onboard_peripheral`、`fixed_power` |
| `evidence` | 是 | 来自 board JSON 或用户接线的结构化证据 |
| `requires_user_review` | 是 | 是否建议用户在 `pin_plan_review` 中重点确认；V0 不要求逐个风险脚精确覆盖 |
| `review_prompt` | 可选 | 给用户核对原理图/丝印/模块资料的提示 |
| `deviation` | 可选 | 偏离默认或占用释放的结构化说明 |

`decision_type` 枚举：

```text
use_default_bus
auto_assign_free_gpio
remap_default_conflict
avoid_restricted_gpio
avoid_onboard_occupied
reuse_onboard_peripheral
fixed_power_tie
user_wiring
manual_review_required
```

`deviation` 字段：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `from_gpio` | 是 | 原默认/候选 GPIO |
| `to_gpio` | 是 | 重映射后的 GPIO 或电源/地 |
| `reason_code` | 是 | 偏离原因枚举 |
| `evidence_path` | 是 | board JSON 中的证据路径，如 `pin_layout.default_bus_pins.i2s.data_out` |
| `evidence_value` | 是 | 证据字段的值 |
| `validator_action` | 是 | `error`、`warning`、`manual_review` |

`reason_code` 枚举：

```text
restricted_gpio
default_bus_conflict
onboard_occupied
not_exposed
user_requested
fixed_power_tie
insufficient_board_data
```

如果 `reason_code=onboard_occupied`，`evidence_path` 必须指向 `onboard_peripherals[].occupied_pins`，且 `evidence_value` 必须与 `from_gpio` 一致；否则应视为 `pin_decision_invalid` 或进入 `manual_review_required`，不能靠 LLM notes 自行断言某 GPIO 被板载器件占用。

电源/地连接必须按真实 rail 记录：当 `pinout.gpio` 为 `GND`、`3V3`、`5V` 时，`pinout.type` 必须分别为 `gnd`、`power_3v3`、`power_5v`；不要把 `VDD`、`3V3`、`GND` 伪装成普通 MCU GPIO。

`fixed_power_tie` 只表示器件侧某个脚固定接到电源或地。普通供电脚/地脚（如 `VCC`、`VDD`、`VDDIO`、`VIN`、`VBUS`、`GND`）接 `3V3/GND` 是常规供电连接；配置、模式、使能、地址、增益、启动等控制脚（如 `ADDR`、`BOOT`、`CFG`、`CONFIG`、`EN`、`GAIN`、`MODE`、`SEL`）固定接 `3V3/GND/5V` 时，必须使用 `decision_type=fixed_power_tie`、`source=fixed_power`，并建议提供 `review_prompt` 让用户核对模块资料。

V0 不把 `requires_user_review` 当作复杂策略引擎。脚本只校验字段类型、枚举、pinout 对应关系、硬禁用脚、冲突和电源/地类型；条件可用 GPIO、配置脚硬接、默认总线偏离、板卡资料不足等风险统一放入 warnings/notes，并通过整体验收的 `pin_plan_review` 让用户确认或改引脚。

## select-hw draft schema

`select_hw_manifest.py` 只支持新 draft schema，不兼容旧 `update_manifest.py` 输入形状。

```json
{
  "protocol_version": "1.0",
  "session_id": "uuid",
  "source_phase": "analyze",
  "upstream_manifest": {},
  "selected_board": {},
  "hardware_plan": {
    "mcu": {},
    "pinout": [],
    "pin_decisions": [],
    "pin_review": {},
    "bom": [],
    "estimated_total_yuan": 0
  },
  "warnings": [],
  "metadata": {
    "idempotency_key": "select-hw:<session_id>:manifest-validation:v1"
  }
}
```

draft 字段含义：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `protocol_version` | 是 | 当前固定 `"1.0"` |
| `session_id` | 是 | 当前工作流会话 ID |
| `source_phase` | 是 | 固定 `"analyze"` |
| `upstream_manifest` | 是 | 来自 `phase_complete(analyze).payload.manifest_content` |
| `selected_board` | 是 | 从板卡库确认后的板卡对象摘要 |
| `hardware_plan.mcu` | 是 | MCU、固件入口和烧录工具 |
| `hardware_plan.pinout` | 是 | 引脚分配数组 |
| `hardware_plan.pin_decisions` | 是 | 每个引脚选择的结构化决策和证据；脚本必须校验并保留到最终 `manifest_content` |
| `hardware_plan.pin_review` | 是 | 用户 `pin_plan_review` 确认状态；`success` 前必须 `confirmed=true` |
| `hardware_plan.bom` | 是 | BOM 数组 |
| `hardware_plan.estimated_total_yuan` | 建议 | BOM 总价；缺省时脚本从 BOM 计算并给 warning |
| `warnings` | 建议 | 非阻塞风险 |
| `metadata.idempotency_key` | 建议 | manifest 校验动作幂等键 |

## 输出 manifest_content

输出必须保留 analyze 核心字段并新增：

```text
phase = "select-hw"
mcu
hardware_selection
pinout
bom
estimated_total_yuan
final_status = "hardware_selected"
```

`mcu.flash_tool` 枚举：

```text
esptool.py
uf2-drag-drop
dfu-util
teensy-loader
unknown
```

BOM 价格 V0 暂时接受 LLM 常识估算，不接商城数据源。

## phase_complete

`phase_complete.select_hw.json` 与 analyze 保持一致，必须使用完整 envelope。

success 时：

```text
payload.result = "success"
payload.next_phase = "upy-flash-mpy-firmware-plugin"
payload.manifest_content.phase = "select-hw"
```

success 前置条件：

- 板卡选择未跨越上游 MCU/芯片族/固件目标边界；如果发生跨边界更换，必须回到 analyze 或新建对话。
- `pin_plan_review` 已确认，或 `pre_selected_board`/插件 UI 明确提供了已确认的结构化接线。
- `pin_decisions` 中所有 `validator_action=error` 或 `manual_review` 项已经解决。

result 枚举：

| result | 含义 | next_phase | checkpoint |
| --- | --- | --- | --- |
| `success` | MCU/固件/pinout/BOM 全部完成 | `upy-flash-mpy-firmware-plugin` | 不需要 |
| `partial` | 可恢复中断 | `null` | 必填 |
| `failed` | 输入非法或协议输出非法 | `null` | 可选 |

## checkpoint/resume

partial 必须带 checkpoint：

```json
{
  "checkpoint_id": "uuid",
  "resume_phase": "select-hw",
  "resume_step": "board_select",
  "resume_label": "继续选择 MicroPython 开发板",
  "reason": "user_cancelled",
  "state_ref": {
    "artifact": "select_hw_draft.json"
  }
}
```

`resume_step` 枚举：

```text
load_upstream_manifest
board_select
firmware_check
pin_assignment
bom_generation
manifest_validation
phase_complete_validation
```

`reason` 枚举：

```text
user_cancelled
board_change_requires_analyze
missing_pin_layout
firmware_unknown
pin_conflict
pin_plan_review_rejected
script_failed
timeout
permission_denied
```

## retry / timeout / idempotency

- retry 必须沿用同一个 `session_id`。
- 同一个本地动作 retry 时，`idempotency_key` 保持不变。
- `retry_of` 指向原始失败消息的 `msg_id`。
- 每个需要等待外部动作的消息必须定义 `timeout_ms`。
- `on_timeout` 枚举：`retry_once / partial_checkpoint / failed`。

## structured_errors

保留 `errors: string[]`，并支持：

```json
{
  "code": "missing_pin_layout",
  "message": "selected board lacks pin_layout",
  "severity": "error",
  "recoverable": true,
  "retryable": false,
  "source": "select_hw_manifest.py",
  "field": "mcu.board_id"
}
```

`severity` 枚举：

```text
info
warning
error
fatal
```

`code` 建议枚举：

```text
invalid_upstream_manifest
missing_required_field
invalid_enum
board_not_found
firmware_unknown
missing_pin_layout
pin_conflict
i2c_address_conflict
board_definition_not_found
board_definition_invalid
board_change_requires_analyze
restricted_gpio_used
default_bus_pin_deviation
pin_review_required
pin_review_rejected
pin_decision_invalid
onboard_peripheral_pin_used
onboard_peripheral_reused
user_wiring_invalid
occupied_pin_conflict
artifact_missing
absolute_path_in_artifact
permission_denied
script_failed
timeout
phase_complete_invalid
```

## artifact/file manifest

`phase_complete.payload.artifacts` 必须是数组。`file_list.files[].path` 必须是相对 artifact root 的路径。

`artifact.type` 枚举：

```text
table
file_tree
markdown
html
code_diff
file_list
```

`file_list.files[].status` 枚举：

```text
created
updated
unchanged
skipped
error
```

直测正式产物：

```text
select_hw_draft.json
select_hw_validated.json
phase_complete.select_hw.json
pin_assignment_log.md
select_hw_phase_log.md
```

直测时 `phase_complete.payload.artifacts` 的 `file_list` 必须声明以上全部文件，且 `--validate-phase-complete` 必须用 `--expected-artifact` 逐一校验。缺少任意正式产物声明都视为失败。

### 日志模板规则

`pin_assignment_log.md` 必须按以下分组列出 GPIO：

```text
## GPIO 使用汇总

已用 GPIO: GPIO4, GPIO5, GPIO6, GPIO7, GPIO10, GPIO11, GPIO20, GPIO21
未用 GPIO: GPIO0, GPIO1, GPIO2, GPIO3, GPIO8, GPIO9, GPIO12, GPIO13, GPIO18, GPIO19
条件/保留 GPIO: GPIO2, GPIO8, GPIO9 (strapping boot pins)
禁止 GPIO: (none)

## 引脚分配明细
...
```

禁止使用"未用(空闲)"这类含义模糊的名称。`select_hw_phase_log.md` 必须记录完整的 step 时间线、`runtime_context` 参数和路径口径。

## permission prompts

V0 允许低风险动作：

- 读取上游 phase_complete 文件
- 从 `resource_root` 读取 `upy-analyze-plugin/boards`
- 写 `sessions/<session_id>/select_hw_*.json`
- 从 `resource_root` 运行白名单脚本 `upy-select-hw-plugin/scripts/select_hw_manifest.py`

需要单独 permission prompt 的动作：

- 任意非白名单脚本
- 将 `upy-select-hw-plugin`、`upy-analyze-plugin` 或半截 skill/resource 副本写入 `artifact_root`
- 只复制单个 board JSON 作为候选板卡库
- 删除文件
- 访问设备串口
- 烧录固件
- 联网查商城价格

## 脚本校验

必须使用：

```text
upy-select-hw-plugin/scripts/select_hw_manifest.py
```

它是校验器/规范化器，不是默认写盘脚本。

必须支持：

```text
--stdin
--input <path>
--write-path <path>
--validate-manifest-content
--validate-phase-complete
--compare-manifest <path>
--artifact-root <path>
--board-root <path>
--strict-board-pins
--expected-artifact <relative-path>
```

必须校验：

- draft schema 只接受新格式
- 上游 manifest 至少满足 analyze 最低交付字段
- MCU、pinout、BOM 必填字段完整
- 枚举值合法
- pinout 冲突
- `pin_decisions` 字段、枚举、证据和 deviation 合法，并能对应最终 `pinout`
- `pin_review.approval_id=pin_plan_review`；`result=success` 时 `pin_review.confirmed=true`
- phase_complete envelope 合法
- `manifest_content` 与 compare manifest 核心字段一致，且不得丢失 `pin_decisions` / `pin_review`
- file artifact 声明的相对路径真实存在
- `selected_board` 与完整 board JSON 一致
- `pinout` 遵守 board JSON 的 `restricted_gpio`
- `pinout` 遵守 board JSON 的 `onboard_peripherals[].occupied_pins`
- 用户接线、板载器件复用、外接器件自动分配三种来源可区分
- 总线引脚偏离 `pin_layout.default_bus_pins` 时必须有 notes/warnings
- `phase_complete.payload.artifacts` 覆盖本 phase 写出的全部正式产物
- WiFi + `adc2_wifi_conflict` 的数字用途必须生成完整 warning，不能只提示部分 GPIO

格式化输出校验流程：

```text
python upy-select-hw-plugin/scripts/select_hw_manifest.py --input upy-select-hw-plugin/sample/select_hw_draft.json --write-path <artifact-root>/select_hw_validated.json --board-root upy-analyze-plugin/boards
python upy-select-hw-plugin/scripts/select_hw_manifest.py --validate-manifest-content --input <artifact-root>/select_hw_validated.json --board-root upy-analyze-plugin/boards
```

第二条命令用于校验脚本产物仍符合规范化后的 `manifest_content` schema；正式阶段完成仍需再用 `--validate-phase-complete` 校验 `phase_complete.select_hw.json`。

## 本地测试

后续测试必须覆盖：

1. 从 `G:\test\test\sessions\022ad742-3269-42e9-ac20-c14f477ecdf2\phase_complete.analyze.json` 的 `payload.manifest_content` 启动，并把 `G:\test\test` 视为 `artifact_root`。
2. 使用 `resource_root/upy-analyze-plugin/boards` 的完整板卡库匹配 `ESP32-C3` 候选板卡，不在 `G:\test\test` 下创建 `upy-analyze-plugin` 或 `upy-select-hw-plugin` 副本。
3. `mcu_specified` 存在但无 `pre_selected_board` 时触发 `approval_request(board_select)`。
4. `pre_selected_board` 来自插件 UI 时可跳过 board_select。
5. 缺 pin_layout 时换功能类似且有 pin_layout 的已知板卡。
6. `cold-driver` 不阻塞 MCU 推荐和 pinout。
7. 未指定 MCU 时优先推荐 Pico/RP2 与 ESP32 系列。
8. 板卡库无用户指定板卡时发 `approval_request(board_unavailable)`，提供相似板卡、改选已知板卡、手动描述接线、保存 checkpoint 四个选项。
9. `select_hw_manifest.py --write-path` 生成的格式化 manifest 能再次被脚本读取校验。
10. `phase_complete.select_hw.json` 通过脚本校验，且 `--expected-artifact` 覆盖全部直测正式产物。
11. validator 覆盖 board-root、restricted pins、默认总线偏离、用户接线、板载器件复用、ADC2/WiFi 数字用途 warning。
12. `phase_complete.payload.artifacts` 覆盖全部正式产物，日志和 artifact 不出现本机插件安装绝对路径。
13. `pin_plan_review` 的 `approval_response.payload.user_pin_constraints` 能被转换为 `user_wiring` pinout/pin_decisions。
14. 用户指定非法 GPIO 时不得静默自动改脚，必须输出 partial/checkpoint 或校验失败。

## 维护原则

后续以 `upy-select-hw-plugin` 目录内容为准，再反向更新课程文档。
