# upy-select-hw 接口定义

> 状态：✅ 已定稿
>
> Phase 2 — MCU 选型 + 固件核验 + 引脚分配 + BOM 生成。输入 project-manifest.json，输出完整硬件方案。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | select-hw |
| 上游 Skill | upy-analyze（自动进入） 或 任意 phase 的增量触发（用户加器件） |
| 下游 Skill | upy-scaffold |
| 一句话职责 | 从 boards/ 数据库匹配最佳 MCU → 验固件 → 分引脚 → 算 BOM 价格 |

**核心约束：** 不写代码、不搜驱动、不生成文件。只输出硬件方案 JSON。

**两种运行模式：**

| 模式 | 触发 | 行为 |
|------|------|------|
| `full` | upy-analyze 完成 | 全新选型 + 全量引脚分配 |
| `incremental` | 用户在后续 phase 新增器件 | 只分配新增器件的引脚，不动已有引脚 |

---

## 二、插件输入 → Skill（P→S）

插件发 **1 条消息** 启动本 skill：

```json
{
  "type": "start_phase",
  "phase": "select-hw",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "full",
    "manifest": { "...完整的 project-manifest.json..." },
    "pre_selected_board": {
      "id": "esp32-devkit-v1",
      "display_name": "ESP32 DevKit V1",
      "mcu": "ESP32-WROOM-32",
      "chip_family": "esp32",
      "firmware_url": "https://micropython.org/download/ESP32_GENERIC/"
    },
    "previous_pinout": [],
    "new_devices": []
  }
}
```

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `mode` | string | 是 | 服务器判断 | `"full"` 全量选型 / `"incremental"` 增量分配 |
| `manifest` | object | 是 | 上游 phase_complete | 完整的 project-manifest.json 内容 |
| `pre_selected_board` | object? | 否 | 插件板卡选择器 | 用户提前选了板卡则有值，null 则 LLM 推荐 |
| `previous_pinout` | array | incremental 必填 | 当前 manifest 的 pinout | 已有引脚分配，增量模式不修改 |
| `new_devices` | array | incremental 必填 | 用户新增的器件列表 | 只给这些器件分配引脚 |

**mode 判断逻辑（服务器端）：**
- `manifest.phase === "analyze"` 且首次进入 → `full`
- 用户在后续 phase 点了 "添加器件" → 启动微型管线，select-hw 收到 `incremental`

**pre_selected_board 的行为：**
- 有值 → 跳过 MCU 选型、跳过固件核验（firmware_url 已确定），直接进入引脚分配
- null → Step 1 执行 MCU 推荐 + 固件核验

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
full 模式：
  Step 1 MCU选型
    → status_update "正在加载板卡数据库..."
    → status_update "正在匹配最佳主控..."
    → approval_request #1: MCU 推荐卡片（仅 pre_selected_board=null 时触发）
  
  Step 2 引脚分配
    → status_update "正在从 boards/{id}.json 读取引脚约束..."
    → status_update "正在分配引脚... (1/N)"
    → script_run: pin-validator.py 校验引脚方案
  
  Step 3 BOM
    → status_update "正在生成物料清单..."
  
  Step 4 输出
    → phase_complete: 结果面板

incremental 模式：
    → status_update "正在为新增器件分配引脚..."
    → script_run: pin-validator.py 增量校验
    → phase_complete（跳过 MCU 选型和 BOM 重算）
```

### 消息详情

#### approval_request #1 — MCU 推荐卡片（条件触发）

**触发条件：** `pre_selected_board` 为 null 且 mode=`full`。

**不触发：** 用户提前选了板卡 → 跳过此卡片，直接进入引脚分配。

```
┌──────────────────────────────────────────┐
│  硬件选型推荐                              │
│                                          │
│  你的需求：温湿度监测 + 屏幕显示 + 蜂鸣器报警  │
│                                          │
│  ★ 推荐：ESP32 DevKit V1                  │
│    理由：WiFi+BLE、GPIO充足(26个)、生态最全  │
│    价格：~¥25                             │
│    固件：ESP32_GENERIC (v1.24.1)          │
│                                          │
│  备选方案：                                │
│  ┌────────────────────────────────────┐  │
│  │ ○ Raspberry Pi Pico W              │  │
│  │   WiFi、USB拖拽烧录、¥15            │  │
│  ├────────────────────────────────────┤  │
│  │ ○ ESP32-S3-DevKitC-1               │  │
│  │   WiFi+BLE+AI、PSRAM、¥35          │  │
│  └────────────────────────────────────┘  │
│                                          │
│  [使用推荐 ESP32] [选 Pico W] [选 S3]     │
└──────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "mcu_select",
    "header": "硬件选型推荐",
    "question": "根据你的需求，推荐以下主控方案",
    "summary": {
      "project_name": "温湿度监测报警器",
      "description": "温湿度监测 + OLED显示 + 蜂鸣器报警，共3个器件"
    },
    "items": [
      {
        "id": "board_1",
        "name": "ESP32 DevKit V1",
        "subtitle": "WiFi+BLE | GPIO×26 | I2C×2 | SPI×2 | ¥25",
        "meta": "★ 推荐",
        "selected": true
      },
      {
        "id": "board_2",
        "name": "Raspberry Pi Pico W",
        "subtitle": "WiFi | GPIO×26 | I2C×2 | SPI×2 | ¥15",
        "meta": "备选",
        "selected": false
      },
      {
        "id": "board_3",
        "name": "ESP32-S3-DevKitC-1",
        "subtitle": "WiFi+BLE+AI | GPIO×45 | I2C×2 | SPI×3 | ¥35",
        "meta": "备选",
        "selected": false
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "使用推荐 ESP32", "value": "confirm", "primary": true },
      { "label": "选 Pico W", "value": "select_board_2" },
      { "label": "选 S3", "value": "select_board_3" }
    ]
  }
}
```

**MCU 推荐算法（服务器端 LLM 执行）：**

1. 加载所有 `boards/*.json`（除 _template.json 和 matching-rules.json）
2. 加载 `boards/matching-rules.json`，根据 manifest.requirements 触发规则
3. 对每块板卡：boost 规则匹配 chip_family → +1 分；exclude 规则匹配 → 排除
4. `beginner_friendly=true` 在 mode=beginner 时额外 +1
5. 得分 Top 1 作为推荐，Top 2~3 作为备选
6. 排除的板卡不一定是板卡不行，可能是不适合当前场景

#### status_update 列表

| step_id | message | level | 触发时机 |
|---------|---------|-------|---------|
| load_boards | 正在加载板卡数据库... | info | full 模式 Step 1 开始 |
| match_mcu | 正在匹配最佳主控（考虑 WiFi/GPIO/I2C/预算...） | info | full 模式 MCU 打分中 |
| mcu_done | ✓ 推荐 ESP32 DevKit V1（WiFi+BLE, GPIO×26, ¥25） | success | full 模式 MCU 选定 |
| mcu_skipped | ✓ 主控已由用户选择：ESP32 DevKit V1 | success | pre_selected_board 有值时 |
| load_pin_layout | 正在从 boards/{id}.json 读取引脚约束... | info | Step 2 开始 |
| assign_pins | 正在分配引脚... (1/3) | info | 每个器件分配时 |
| pin_assigned | ✓ SHT30 → I2C0 (SDA=21, SCL=22, addr=0x44) | success | 单个器件分配完成 |
| pin_conflict | ⚠ SHT30 与 SSD1306 共享 I2C0 总线，地址不冲突 ✓ | warn | I2C 共享总线提示 |
| validate_pins | 正在校验引脚方案... | info | pin-validator.py 运行前 |
| validate_ok | ✓ 引脚方案校验通过（无冲突、无禁区） | success | 校验通过 |
| validate_fail | ✗ 引脚校验失败：GPIO12 被 strapping 和 LED 同时占用 | error | 校验失败（触发重分配） |
| bom_gen | 正在生成物料清单... | info | Step 3 |
| bom_done | ✓ BOM 共 6 项，预估 ¥52（预算内） | success | BOM 完成 |
| incremental_start | 正在为新增器件 DHT22 分配引脚... | info | incremental 模式 |
| incremental_done | ✓ DHT22 → GPIO14（空闲），未影响已有 6 个引脚 | success | incremental 完成 |

#### script_run — pin-validator.py

**这是新增的校验脚本。** 路径：`G:\MicroPython_Skills\upy-select-hw\scripts\pin-validator.py`

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "pv_001",
    "interpreter": "python",
    "script": "pin-validator.py",
    "args": ["--board", "boards/esp32-devkit-v1.json", "--pinout", "{pinout_json_stdin}"],
    "cwd": "{skill_dir}",
    "timeout_ms": 5000
  }
}
```

**脚本职责（确定性校验，LLM 做不到的）：**

| 校验项 | 说明 |
|--------|------|
| GPIO 重叠检测 | 同一 GPIO 不能分配给两个非共享器件 |
| restricted_gpio 违规 | 分配的 GPIO 不能出现在 restricted_gpio 的各类别中（strapping/flash/input_only 等，除非 LLM 明确说明了理由） |
| I2C 地址冲突 | 同一 I2C 总线上不能有两个相同地址的器件 |
| 总线数量超限 | 分配的 I2C/SPI/UART 数量不能超过 specs 中的硬件数量（超了需标注 SoftI2C/SoftSPI） |
| fixed 模型合规 | RP2040 等 fixed 模型，引脚必须在 pin_options 的可选列表中，且 SDA/SCL 成对 |
| onboard_occupied 冲突 | 分配的 GPIO 不能与 onboard_peripherals 中 always_used=true 的引脚冲突 |

**校验失败时：** 脚本返回非 0 退出码 + 错误详情 JSON。LLM 读取错误后重新分配，最多重试 3 次。

#### phase_complete

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "select-hw",
    "result": "success",
    "summary": "硬件方案确定：ESP32 DevKit V1，6/26 GPIO 已分配，BOM 预估 ¥52",
    "next_phase": "scaffold",
    "artifacts": [
      {
        "type": "table",
        "title": "引脚分配表",
        "headers": ["器件", "引脚功能", "GPIO", "物理脚", "类型", "备注"],
        "rows": [
          ["SHT30", "I2C SDA", "21", "—", "i2c_data", "共享 I2C0"],
          ["SHT30", "I2C SCL", "22", "—", "i2c_clock", "共享 I2C0"],
          ["SSD1306", "I2C SDA", "21", "—", "i2c_data", "共享 I2C0 (0x3C)"],
          ["SSD1306", "I2C SCL", "22", "—", "i2c_clock", "共享 I2C0 (0x3C)"],
          ["蜂鸣器", "GPIO OUT", "4", "—", "gpio_out", "PWM 驱动"],
          ["电源", "3V3", "3V3", "—", "power_3v3", "供 I2C 器件"],
          ["电源", "GND", "GND", "—", "gnd", ""]
        ]
      },
      {
        "type": "table",
        "title": "物料清单 (BOM)",
        "headers": ["#", "名称", "型号", "数量", "单价", "备注"],
        "rows": [
          ["1", "主控", "ESP32 DevKit V1", "1", "¥25", "含 USB 线"],
          ["2", "温湿度传感器", "SHT30", "1", "¥8", "I2C"],
          ["3", "OLED显示屏", "SSD1306 0.96\"", "1", "¥12", "I2C"],
          ["4", "蜂鸣器模块", "有源蜂鸣器", "1", "¥2", "GPIO"],
          ["-", "面包板", "830孔", "1", "¥8", "可选"],
          ["-", "杜邦线", "公母各20根", "1", "¥5", ""]
        ]
      }
    ],
    "warnings": [
      "蜂鸣器占用了 strapping GPIO4，启动时可能短暂鸣响（不影响功能）"
    ],
    "errors": [],
    "manifest_content": "{完整的更新后 project-manifest.json JSON 文本}"
  }
}
```

**manifest_content 新增/更新字段：**
- `phase`: `"select-hw"`
- `mcu`: `{model, board, chip_family, firmware_url, flash_tool}`
- `pinout`: `[{device, pin_name, gpio, physical_pin, type, side, pos, bus, i2c_addr, notes}]`
- `bom`: `[{name, model, quantity, unit_price_yuan, notes}]`

---

## 四、SKILL.md 修改点

共 10 处改动，按执行步骤排列：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 前置检查 | `python --version` | 删除。依赖检查由服务器环境保证 | 插件用户不可见服务器环境 |
| 2 | Step 1 情况A | 查内置 `KNOWN_FIRMWARE` 表 + WebSearch 未知型号 | `pre_selected_board` 有值 → 跳过整个 Step 1。null 但有 `mcu_specified` → 读 boards/*.json 找匹配 chip_family + 已内置 firmware_url，不再 WebSearch | 板卡数据库已有固件信息，WebSearch 不稳定且慢 |
| 3 | Step 1 情况B | LLM 自由推荐，打分逻辑写死在 SKILL.md 里 | 改为读 `matching-rules.json` 打分 + 过滤 `beginner_friendly` | 规则集中管理，插件端加新板卡不需要改 SKILL.md |
| 4 | Step 1 情况B | 纯文本输出推荐 | 改为 `approval_request` #1（MCU 推荐卡片），含 1 个推荐 + 2 个备选 | 插件端不能渲染命令行文本 |
| 5 | Step 2A 获取引脚图 | 要求用户上传引脚图 → WebSearch | **整节删除**。改为读 `boards/{id}.json` 的 `pin_layout` + `onboard_peripherals` | 板上数据库已有完整引脚约束，不需要用户上传图片 |
| 6 | Step 2B 多模态识别 | LLM 从图片提取引脚信息 | **整节删除**。数据结构化读取替代多模态识别 | 结构数据比图片识别准 100% |
| 7 | Step 2C 分配引脚 | LLM 凭训练数据分配，不考虑板上已有外设 | 读 `pin_layout.restricted_gpio`（避开禁区）+ `onboard_peripherals`（避开板载外设占用的脚）。flexible 模型优先用 `default_bus_pins`，fixed 模型从 `pin_options` 里选 | 基于结构化数据，避免分配到已被板载外设占用的引脚 |
| 8 | Step 2C 冲突检测 | LLM 手动检查（不可靠） | LLM 分配完后调用 `pin-validator.py` 做确定性校验。失败 → 读错误详情 → 重新分配（最多 3 次） | LLM 做枚举验证不可靠，脚本是最后一道防线 |
| 9 | 新增 incremental 模式 | 无此模式 | 新增 mode 判断：`incremental` 时只给 `new_devices` 分引脚，不动 `previous_pinout`，不重跑 MCU 选型，不重算完整 BOM（追加行） | 支持用户在 deploy 阶段加器件 |
| 10 | Step 4 更新 manifest | `python update_manifest.py --project-dir {dir} --input {json}` 写本地文件 | LLM 生成更新后的 manifest JSON → 经 `update_manifest.py` 校验（stdin/stdout）→ 放入 `phase_complete.manifest_content` | 服务器端不写本地磁盘 |

---

## 五、校验脚本改动

### update_manifest.py（现有，需修改）

**路径：** `G:\MicroPython_Skills\upy-select-hw\scripts\update_manifest.py`

| 改动 | 内容 |
|------|------|
| 输出方式 | `--project-dir` 改为可选。不传则从 stdin 读现有 manifest + LLM 输出，校验后合并输出到 stdout |
| 新增 I2C 地址冲突检测 | 已有（merge_manifest 中），保持不变 |
| 新增 restricted_gpio 违规检测 | 读 boards JSON 的 restricted_gpio，检查每个分配的 GPIO 是否在禁区 |
| 新增 onboard_occupied 冲突检测 | 读 boards JSON 的 onboard_peripherals（always_used=true），检查是否有冲突 |
| 支持 incremental 模式 | 用 `--mode incremental --previous-pinout {json}` 只校验新增引脚 |

### pin-validator.py（新增脚本）

**路径：** `G:\MicroPython_Skills\upy-select-hw\scripts\pin-validator.py`

```python
#!/usr/bin/env python3
"""
引脚分配确定性校验器。

校验项：
  1. GPIO 重叠（非共享引脚不能重复分配）
  2. restricted_gpio 违规（不能分配禁区引脚）
  3. I2C 地址冲突（同一总线地址不能重复）
  4. 总线数量超限（I2C/SPI/UART 分配数 vs specs 硬件数）
  5. fixed 模型引脚合规（RP2040等，引脚在 pin_options 内且成对）
  6. onboard_occupied 冲突（不能占用 always_used=true 的板载外设引脚）

用法：
  python pin-validator.py --board boards/esp32-devkit-v1.json --pinout pinout.json
  python pin-validator.py --board boards/esp32-devkit-v1.json --pinout - < pinout.json
  python pin-validator.py --board boards/esp32-devkit-v1.json --pinout - --mode incremental --previous-pinout prev.json
  
退出码：0=通过，1=校验失败（stdout 输出错误 JSON），2=输入格式错误
"""
```

**是否必须：是。** LLM 的枚举验证不可靠，引脚冲突在硬件上是灾难性的（短路/烧板）。

---

## 六、插件端需要实现的 UI 组件

| 组件 | 对应消息 | 关键功能 |
|------|---------|---------|
| 进度时间线 | status_update × 4~8 条 | 复用 analye 的时间线组件 |
| MCU 推荐卡片 | approval_request #1（条件出现） | 单选 + 推荐理由 + 规格摘要 + 备选方案 |
| 引脚分配表 | phase_complete artifact[0] | 表格：器件/功能/GPIO/类型/备注，I2C 共享行高亮 |
| BOM 表 | phase_complete artifact[1] | 表格：名称/型号/数量/单价/备注，总价高亮 |
| 警告提示 | phase_complete.warnings | 黄色警告条，如 strapping 脚警告 |

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发 `approval_request` #1（MCU 推荐卡片）→ 验证：
   - 3 个板卡选项渲染正确（规格摘要、价格、理由）
   - 单选 + 三个按钮的行为
2. 手动发 `phase_complete`（含 pinout table + BOM table）→ 验证：
   - 引脚表 I2C 共享行高亮
   - BOM 总价计算显示

### Skill 端测试（无插件）

1. **full 模式 + 无预设板卡：**
   - mock_plugin 发送 start_phase（mode=full, pre_selected_board=null, manifest=温湿度项目）
   - 对 approval_request #1 自动回复 `{"action": "confirm"}`
   - 检查所有消息 JSON 符合 02-protocol.md Schema
   - 检查 manifest 被 update_manifest.py 校验通过
2. **full 模式 + 有预设板卡：**
   - mock_plugin 发送 start_phase（mode=full, pre_selected_board=esp32-devkit-v1）
   - 确认跳过 approval_request #1
   - 确认引脚分配使用了 boards/esp32-devkit-v1.json 的 pin_layout
3. **incremental 模式：**
   - mock_plugin 发送 start_phase（mode=incremental, previous_pinout=[已有6个引脚], new_devices=[DHT22]）
   - 确认只分配了 DHT22 的引脚
   - 确认已有 6 个引脚未变
4. **pin-validator 校验失败 + 重试：**
   - LLM 故意分配 GPIO12（strapping）给 LED
   - pin-validator.py 返回错误
   - LLM 读取错误，改分配 GPIO13
   - pin-validator.py 再次校验通过
