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
- 输出 `phase_complete(select-hw)`，`next_phase` 固定为 `flash-mpy-firmware`

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

## 相对路径约定

所有文件加载必须以仓库根目录为基准使用相对路径，例如：

```text
upy-analyze-plugin/boards
upy-analyze-plugin/sample/phase_complete.analyze.success.json
upy-select-hw-plugin/scripts/select_hw_manifest.py
upy-select-hw-plugin/sample/phase_complete.select_hw.success.json
```

不要在协议、脚本参数或样例里把 `G:\MicroPython_Skills` 写成业务依赖。测试命令可以在文档里展示绝对路径，但实现要用 `repo_root / relative_path`。

phase log、命令历史和 artifact 描述也必须使用相对路径。不要把本机插件安装目录（例如用户目录下的 skill/plugin 路径）写成业务事实源。

## 长期协议要求

所有正式消息必须使用完整 envelope：

```json
{
  "protocol_version": "1.0",
  "msg_id": "uuid",
  "session_id": "uuid",
  "phase": "select-hw",
  "timestamp": "2026-06-21T00:00:00Z",
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
  -> status_update(pin_assignment_done)

Step 4 BOM 生成
  -> status_update(bom_ready)

Step 5 manifest 校验/规范化
  -> script_run(select_hw_manifest.py --stdin)
  <- script_result

Step 6 阶段完成
  -> phase_complete(result=success, next_phase=flash-mpy-firmware)
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
firmware_check
firmware_ok
pin_assignment
pin_risk_detected
pin_conflict
pin_assignment_done
bom_ready
manifest_validation
```

## approval_request: board_select

`requirements.mcu_specified` 表示 MCU/芯片/模组型号，不等于具体开发板，因此默认必须弹 `board_select`。如果 `pre_selected_board` 已经来自插件 UI，可跳过，但必须记录跳过原因并校验该板卡存在固件和 `pin_layout`。

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

## 板卡数据

V0 复用相对路径：

```text
upy-analyze-plugin/boards
```

不要复制板卡数据，除非后续 select-hw 需要独立扩展 schema。

处理策略：

- `requirements.mcu_specified` 存在时，按 `mcu`、`chip_family`、`firmware.board_name` 匹配候选。
- `pre_selected_board` 已来自插件 UI 时可跳过确认，但仍需校验。
- `selected_board.id` 必须对应 `upy-analyze-plugin/boards/<id>.json`。确认板卡后必须加载完整 board JSON，不允许只凭 MCU 名称或 `selected_board` 摘要分配引脚。
- 完整 board JSON 是 `firmware`、`pin_layout`、`restricted_gpio`、`onboard_peripherals` 的事实源。`selected_board` 只能作为 UI 摘要。
- 未指定 MCU 时，候选池必须优先限制在 Pico/RP2 系列和 ESP32 系列；除非需求明确需要其他系列，不要优先推荐 STM32、Teensy、Pyboard 等板卡。
- 未指定 MCU 的默认排序：Pico/Pico W、ESP32 DevKit、ESP32-S3、ESP32-C3；按需求加分后输出 Top 1 和 Top 2 备选。
- 需要 WiFi/BLE 时加分 ESP32 系列和 Pico W；需要 AI/语音/摄像头时加分 ESP32-S3；低功耗/电池供电加分 ESP32-C3；纯 GPIO 或新手入门加分 Pico/Pico W；极致低价可加分 ESP8266/Pico，但 ESP8266 不应压过 Pico/ESP32，除非预算是唯一主约束。
- 用户指定板卡不存在于板卡库时，优先推荐同系列或功能相似且有 `pin_layout` 的已知板卡；同时发 `approval_request(board_unavailable)`，允许用户改选已知板卡或手动描述接线。
- 缺少 `pin_layout` 时，默认换功能类似且有 `pin_layout` 的已知板卡。
- `cold-driver` 不影响 MCU 推荐、引脚分配或 BOM，只增加 warnings。

## 引脚分配规则

基础规则：

- I2C 器件默认共享一条 I2C 总线并优先使用 `pin_layout.default_bus_pins`；若 `i2c_addr` 冲突，改用第二条 I2C 或输出 partial。
- SPI 器件共享 MOSI/MISO/SCK，每个器件独立 CS，并优先使用 `pin_layout.default_bus_pins`。
- UART 避开 REPL/USB 串口。
- I2S 需要分配 BCK/WS/DIN/DOUT；麦克风和功放可共享 BCK/WS，但数据方向不同。
- ADC 只能用 ADC-capable pin。
- GPIO 避开 boot/strapping、flash/PSRAM、USB OTG、只读脚。
- 电源与 GND 必须进入 `pinout`。
- 如果 board JSON 有 `pin_options`，重映射只能在 `pin_options` 允许范围内进行；如果是 flexible matrix，也必须避开 `restricted_gpio`。
- 偏离 `pin_layout.default_bus_pins` 必须在 `pinout[].notes` 和 warnings 中说明原因。
- 用户传入接线时，优先保留用户接线，但必须通过 board JSON 的 restricted/occupied 校验；非法用户接线不能静默成功。
- 板载器件与用户指定器件或系统推荐器件一致时，复用 `onboard_peripherals` 声明的板载默认/占用引脚，不重复分配外接 GPIO，也不重复加入 BOM。
- 板载器件与当前需求不一致时，`onboard_peripherals[].occupied_pins` 视为已占用资源，外接器件只能使用空余引脚。
- 如果用户要求释放板载器件占用脚，必须确认 `always_used=false`，并在 notes/warnings 中说明释放原因。
- `pin_assignment_log.md` 和 phase log 中的 GPIO 汇总必须从完整 board JSON 与最终 `pinout` 计算，不允许手写静态列表。至少包含 `used_gpio`、`unused_safe_gpio`、`restricted_or_occupied_gpio` 三组；`unused_safe_gpio` 不能包含已使用 GPIO、`restricted_gpio` 或未释放的 `onboard_peripherals[].occupied_pins`。
- 如果启用 WiFi 且使用了 `adc2_wifi_conflict` 中的 GPIO，必须完整列出所有相关 GPIO。只有 `pinout[].type=adc` 时是冲突；作为 I2C/I2S/GPIO 等数字信号使用时允许，但必须在 warnings 或 notes 中说明“WiFi 只影响 ADC 读数，不影响数字用途”。
- 使用板卡默认 UART/REPL/USB 串口相关引脚做普通 GPIO 时，必须确认该串口不用于调试/通信，或者把该占用写入 warning 并给出可重分配建议。

`restricted_gpio` 分级：

| board 字段 | 默认策略 | 校验级别 |
| --- | --- | --- |
| `flash_psram_occupied` | 禁止使用 | error |
| `reserved` / `internal_only` | 禁止使用 | error |
| `usb_serial_pins` | 默认禁止，除非明确不使用 USB 串口或用户显式接线 | error 或 warning |
| `strapping` / `boot` | 默认避开；必须使用时需要用户确认或强 warning | warning；strict 模式为 error |
| `input_only` | 只能用于输入类 pin type | error |
| `adc_only` | 只能用于 ADC 输入 | error |
| `adc2_wifi_conflict` | 仅在 `type=adc` 且 WiFi 启用时冲突；数字输入输出可用但应说明 | error 或 warning |
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
payload.next_phase = "flash-mpy-firmware"
payload.manifest_content.phase = "select-hw"
```

result 枚举：

| result | 含义 | next_phase | checkpoint |
| --- | --- | --- | --- |
| `success` | MCU/固件/pinout/BOM 全部完成 | `flash-mpy-firmware` | 不需要 |
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
missing_pin_layout
firmware_unknown
pin_conflict
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
restricted_gpio_used
default_bus_pin_deviation
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

## permission prompts

V0 允许低风险动作：

- 读取上游 phase_complete 文件
- 读取 `upy-analyze-plugin/boards`
- 写 `sessions/<session_id>/select_hw_*.json`
- 运行白名单脚本 `upy-select-hw-plugin/scripts/select_hw_manifest.py`

需要单独 permission prompt 的动作：

- 任意非白名单脚本
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
- phase_complete envelope 合法
- `manifest_content` 与 compare manifest 核心字段一致
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

1. 从 `G:\test\test\sessions\022ad742-3269-42e9-ac20-c14f477ecdf2\phase_complete.analyze.json` 的 `payload.manifest_content` 启动。
2. 使用相对路径 `upy-analyze-plugin/boards` 匹配 `ESP32-C3` 候选板卡。
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

## 维护原则

后续以 `upy-select-hw-plugin` 目录内容为准，再反向更新课程文档。
