# upy-select-hw-plugin 通用问题与修改方案

本文档整理 `upy-select-hw-plugin` 的通用修改意见。目标是让 `select-hw` 成为可长期维护的硬件选型工作流协议，而不是依赖单个项目、单块板卡或单个元器件案例的临时实现。

## 结论

当前问题不只是“没有读取板卡库”。`SKILL.md` 已经提到复用 `upy-analyze-plugin/boards`，但没有把板卡库完整 JSON 定义为硬件事实源，也没有把 `pin_layout.default_bus_pins`、`restricted_gpio`、`onboard_peripherals` 等字段变成引脚分配和校验的强约束。

因此执行者可能只根据板卡名称或 MCU 常识做引脚分配，而没有严格遵守板卡 JSON 中的默认总线、受限引脚和板载资源定义。

## 发现的问题

### 1. 板卡库只是“参考”，不是“事实源”

现状：

- `SKILL.md` 提到读取 `upy-analyze-plugin/boards`。
- 但没有强制在用户确认板卡后加载 `upy-analyze-plugin/boards/<board_id>.json`。
- `selected_board` 摘要可能被误用为完整板卡事实。

风险：

- 固件、默认总线、受限引脚、板载外设等信息可能被忽略。
- 后续 pinout 可能与真实板卡定义不一致。

解决方案：

- 在“板卡数据”小节增加强约束：确认板卡后必须加载完整 board JSON。
- 完整 board JSON 是 pinout、firmware、BOM 主控条目和 warnings 的事实源。
- 如果 board JSON 不存在，必须进入 `board_unavailable`，不能继续宣称成功。

### 2. 引脚分配没有强制优先使用默认总线

现状：

- `SKILL.md` 只说明根据 `pin_layout` 分配引脚。
- 没有说明 I2C/SPI/UART/I2S 应优先使用 `pin_layout.default_bus_pins`。
- 偏离默认引脚时没有要求说明原因。

风险：

- 会出现“板卡库有默认 I2C，但产物用了其他脚”的情况。
- 下游代码生成阶段可能生成和板卡定义不一致的初始化代码。

解决方案：

- 在“引脚分配规则”中增加：总线类接口默认使用 `pin_layout.default_bus_pins`。
- 偏离默认引脚必须满足两个条件：不命中禁止/高风险引脚；在 `pinout[].notes` 和 warnings 中说明原因。
- 如果默认总线引脚被其他必要功能占用，必须记录冲突决策。

### 3. restricted_gpio 分级语义不明确

现状：

- 当前规则只笼统写“避开 boot/strapping、flash/PSRAM、USB OTG、只读脚”。
- 没有区分禁止使用、默认禁止、可用但需说明、只对特定 pin type 生效等级。

风险：

- strapping 脚可能被当作普通可用 GPIO。
- ADC/WiFi 冲突脚可能被错误地一刀切禁止，或在 ADC 场景漏报。
- USB 串口脚可能影响后续烧录、REPL 或调试。

解决方案：

在 `SKILL.md` 中定义通用风险分级：

| board 字段 | 默认策略 | 校验级别 |
| --- | --- | --- |
| `flash_psram_occupied` | 禁止使用 | error |
| `reserved` / `internal_only` | 禁止使用 | error |
| `usb_serial_pins` | 默认禁止，除非明确不使用 USB 串口 | error 或 warning |
| `strapping` / `boot` | 默认避开；必须使用时需要用户确认或强 warning | warning 或 partial |
| `input_only` | 只能用于输入类 pin type | error |
| `adc_only` | 只能用于 ADC 输入 | error |
| `adc2_wifi_conflict` | 仅在 `type=adc` 且 WiFi 启用时冲突；数字输入输出可用但应说明 | error 或 warning |
| `onboard_peripherals[].occupied_pins` | `always_used=true` 时禁止；否则默认避开或说明释放原因 | error 或 warning |

### 4. 用户传入板卡引脚和板载器件复用规则缺失

现状：

- 用户可能已经传入某块板卡、板载器件或引脚连接信息。
- board JSON 也可能声明 `onboard_peripherals` 及其 `occupied_pins`。
- 当前规则没有明确：板载器件与用户指定器件或系统推荐器件一致时，应复用板卡默认引脚；不一致时，应把板载占用脚排除，给外接器件分配空余引脚。

风险：

- 同一个板载器件可能被重复当成外接器件，造成 BOM 和 pinout 重复。
- 外接器件可能误用板载器件占用的 GPIO。
- 用户明确提供的接线可能被自动分配覆盖。

解决方案：

- 增加“用户/板卡引脚事实优先级”：
  1. 用户明确传入的接线或插件 UI 选择，优先级最高，但必须通过 board restricted 校验。
  2. 如果 board JSON 的 `onboard_peripherals` 与用户指定器件或系统推荐器件在功能上等价，优先复用板载器件和其默认/占用引脚，不再重复加入外接 BOM。
  3. 如果板载器件与当前项目不相关，或用户指定的是外接器件，则 `onboard_peripherals[].occupied_pins` 应视为已占用资源，外接器件必须使用空余引脚。
  4. 如果用户要求把板载器件占用脚释放出来，必须确认 `always_used=false`，并在 notes/warnings 中说明释放原因。

- 增加器件匹配逻辑：
  - 按 `type`、`interface`、`name` 别名、功能标签匹配板载器件与需求器件。
  - 匹配成功时，`pinout[].source` 建议标记为 `onboard_peripheral`。
  - 外接器件的 `pinout[].source` 建议标记为 `external_device` 或 `user_wiring`。

### 5. validator 没有板卡语义校验

现状：

- `select_hw_manifest.py` 校验字段完整性、枚举值、GPIO 重复、电源/GND、I2C 地址冲突。
- 它不加载 board JSON，也不校验 `default_bus_pins`、`restricted_gpio`、`onboard_peripherals`。

风险：

- schema 合法但硬件不可用的方案会通过。
- session 产物可能显示 `status: ok`，但实际接线风险很高。

解决方案：

- 增加 `--board-root <path>` 参数，默认相对路径为 `upy-analyze-plugin/boards`。
- 根据 `hardware_plan.mcu.board_id` 加载 board JSON。
- 新增校验：
  - board 文件存在。
  - `selected_board.firmware` 与 board JSON 一致。
  - board JSON 存在 `pin_layout`。
  - 用户传入接线不会覆盖禁止引脚。
  - 板载器件匹配成功时，必须复用 board JSON 中声明的占用/默认引脚。
  - 外接器件不能占用无关板载器件的 `occupied_pins`。
  - pinout 不使用禁止引脚。
  - pinout 命中高风险引脚时生成 structured warning/error。
  - 总线引脚偏离 `default_bus_pins` 时必须有 `notes`。

### 6. artifact/file manifest 不完整

现状：

- `SKILL.md` 的直测建议产物包含 `select_hw_draft.json`、`select_hw_validated.json`、`phase_complete.select_hw.json`、`pin_assignment_log.md`。
- 如果实际还生成 phase log 或其他产物，`phase_complete.payload.artifacts[].files` 可能没有完整声明。

风险：

- 下游 phase 或调试工具无法完整发现产物。
- `phase_complete` 与 session 目录实际文件不一致。

解决方案：

- 在 `SKILL.md` 中要求：`phase_complete.payload.artifacts` 必须覆盖本 phase 写出的全部正式产物。
- 直测建议产物应包含：
  - `select_hw_draft.json`
  - `select_hw_validated.json`
  - `phase_complete.select_hw.json`
  - `pin_assignment_log.md`
  - `select_hw_phase_log.md`

### 7. 日志路径约定不够严格

现状：

- `SKILL.md` 要求协议和样例使用相对路径。
- 但没有明确要求 phase log、命令历史、artifact 描述也使用相对路径。

风险：

- 日志中可能写入本机绝对路径，如插件安装目录、用户目录等。
- 同一 session 迁移到其他机器后可读性和可复现性下降。

解决方案：

- 在“相对路径约定”中补充：日志、命令历史、artifact 描述也必须使用相对路径。
- 允许测试报告中说明“本机执行路径”，但不能作为业务事实源。
- 推荐统一记录：
  - `upy-analyze-plugin/boards`
  - `upy-select-hw-plugin/scripts/select_hw_manifest.py`
  - `sessions/<session_id>/<artifact>`

### 8. session 产物修正不应手工局部 patch

现状：

- 如果只局部修改某个 JSON 或日志，很容易造成 draft、validated、phase_complete、log 之间不一致。

风险：

- `compare-manifest` 可能失效。
- 用户看到的日志和机器读取的 manifest 不一致。

解决方案：

- 修改 pinout 或 board 选择后，应按固定顺序重建产物：
  1. 更新 `select_hw_draft.json`
  2. 用 validator 生成 `select_hw_validated.json`
  3. 由 validated manifest 生成 `phase_complete.select_hw.json`
  4. 更新 `pin_assignment_log.md`
  5. 更新 `select_hw_phase_log.md`
  6. 重新跑 phase_complete 校验

## SKILL.md 建议修改位置

### “标准消息序列”

建议在 `board_select` 之后增加一个显式步骤：

```text
Step 1B 加载完整板卡定义
  -> status_update(board_definition_loaded)
  从 upy-analyze-plugin/boards/<selected_board.id>.json 加载完整 board JSON
  若不存在或缺 pin_layout:
    -> approval_request(board_unavailable 或 board_select)
```

### “status_update 枚举”

建议增加：

```text
board_definition_loaded
board_definition_invalid
pin_risk_detected
```

### “板卡数据”

建议加入这些强约束：

- `selected_board.id` 必须对应 `upy-analyze-plugin/boards/<id>.json`。
- 完整 board JSON 是 `firmware`、`pin_layout`、`restricted_gpio`、`onboard_peripherals` 的事实源。
- 不允许只凭 MCU 名称或 board 摘要分配引脚。
- 缺失 board JSON 或 `pin_layout` 时不能成功完成 phase。

### “引脚分配规则”

建议加入这些强约束：

- 总线接口优先使用 `pin_layout.default_bus_pins`。
- 如果 board JSON 有 `pin_options`，只能在 pin_options 允许范围内重映射。
- 如果 board JSON 是 flexible matrix，仍需避开 `restricted_gpio`。
- 偏离默认总线必须说明原因。
- 命中高风险引脚必须进入 warnings 或 partial，不要写成“安全”。
- 用户传入接线时，优先保留用户接线，但必须通过 board JSON 的 restricted/occupied 校验。
- 板载器件与需求器件一致时，复用板载默认引脚，不重复分配外接 GPIO，也不重复加入 BOM。
- 板载器件与需求器件不一致时，板载占用脚视为空间资源已占用，推荐器件/用户外接器件只能使用空余引脚。

### “脚本校验”

建议加入：

```text
--board-root <path>
--strict-board-pins
```

并要求校验：

- board JSON 存在。
- selected_board 与 board JSON 一致。
- pinout 遵守 `restricted_gpio`。
- pinout 遵守 `onboard_peripherals[].occupied_pins`。
- 用户接线、板载器件复用、外接器件自动分配三种来源必须可区分。
- pinout 偏离默认总线时有 notes。
- `phase_complete.payload.artifacts` 覆盖全部正式产物。

## validator 修改建议

建议新增通用函数：

- `load_board_definition(board_root, board_id)`
- `validate_selected_board_against_definition(selected_board, board_definition)`
- `match_onboard_peripherals(devices, board_definition)`
- `validate_pinout_against_board(pinout, board_definition, requirements)`
- `validate_user_wiring_against_board(user_wiring, board_definition)`
- `validate_artifact_completeness(artifacts, expected_files)`

建议新增 structured error/warning code：

```text
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
```

## 通用验收标准

修改完成后，至少应满足：

1. 任意已知 board 都会加载完整 board JSON 后再分配引脚。
2. 默认总线优先规则可在测试中复现。
3. 使用 flash/PSRAM 占用脚会失败。
4. 使用 strapping/boot 脚不会静默成功，至少产生结构化 warning，必要时 partial。
5. ADC2/WiFi 冲突只对 ADC 场景生效，不误伤普通数字输入输出。
6. 用户传入接线会被保留并校验，非法接线不会静默通过。
7. 板载器件与需求一致时复用板载引脚，且不重复加入外接 BOM。
8. 板载器件与需求不一致时，外接器件只使用空余引脚。
9. phase_complete 的 file_list 覆盖所有正式产物。
10. 日志和 artifact 中不出现本机插件安装绝对路径。
11. draft、validated、phase_complete、logs 之间内容一致。

## 建议实施顺序

1. 先修改 `SKILL.md`，把板卡库事实源、默认总线、restricted_gpio、artifact 完整性写成通用强约束。
2. 再增强 `select_hw_manifest.py`，增加 board-root 语义校验。
3. 更新 sample 和 smoke tests，覆盖默认总线、restricted pins、unknown board、用户传入接线、板载器件复用、artifact completeness、relative paths。
4. 最后再重生成已有 session 产物，避免手工局部 patch。
