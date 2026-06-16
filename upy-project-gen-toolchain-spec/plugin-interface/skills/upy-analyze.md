# upy-analyze 接口定义

> 状态：✅ 已定稿
>
> Phase 1 — 需求解析 + 驱动搜索。读取用户自然语言和插件上下文，输出 project-manifest.json。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | analyze |
| 上游 Skill | 无（用户输入触发） |
| 下游 Skill | upy-select-hw |
| 一句话职责 | 自然语言 → 意图拆解 → 器件确认 → 驱动搜索 → 输出 manifest |

**核心约束：** 不选型、不生成代码、不分配引脚。MCU 固件核验交给 upy-select-hw。

---

## 二、插件输入 → Skill（P→S）

插件发 **1 条消息** 给服务器启动本 skill：

```json
{
  "type": "start_phase",
  "phase": "analyze",
  "session_id": "uuid-xxx",
  "payload": {
    "user_description": "做一个温湿度监测仪，超过阈值蜂鸣器报警",
    "pre_selected_board": {
      "id": "esp32-devkit-v1",
      "display_name": "ESP32 DevKit V1",
      "mcu": "ESP32-WROOM-32",
      "chip_family": "esp32",
      "firmware_url": "https://micropython.org/download/ESP32_GENERIC/"
    },
    "preferences": {
      "mode": "beginner",
      "locale": "zh"
    },
    "existing_hardware": []
  }
}
```

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `user_description` | string | 是 | 用户输入框 | 自然语言，中英文均可 |
| `pre_selected_board` | object? | 否 | 插件板卡选择器 | 用户提前选了板卡则有值，null 则交给 select-hw 推荐 |
| `pre_selected_board.id` | string | 是 | boards/*.json | 板卡唯一 ID |
| `pre_selected_board.display_name` | string | 是 | 同上 | UI 显示名 |
| `pre_selected_board.mcu` | string | 是 | 同上 | MCU 型号 |
| `pre_selected_board.chip_family` | string | 是 | 同上 | 芯片家族，传给下游 select-hw |
| `pre_selected_board.firmware_url` | string | 是 | 同上 | 固件 URL 已确定 |
| `preferences.mode` | string | 否 | 插件设置 | "beginner" / "custom"，默认 "beginner" |
| `preferences.locale` | string | 否 | 插件设置 | 默认 "zh" |
| `existing_hardware` | string[] | 否 | 用户档案 | 已有硬件列表，补充到器件清单 |

**关于 pre_selected_board：**
- 有值 → 器件确认卡片里显示已选主控（灰色不可改），不追问 MCU
- null → 卡片显示"未选择，将智能推荐"，MCU 交给 select-hw 推荐
- 用户描述里提到板卡型号但未通过插件选 → LLM 提取到 `mcu_specified` 字符串写入 manifest

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
Step 1 意图拆解
  → status_update "正在分析需求..."
  → status_update "提取到 N 个器件: xxx, xxx"

Step 2 交互确认
  → approval_request #1: 器件确认卡片

Step 3 驱动搜索
  → status_update "正在搜索驱动... (1/N)"
  → status_update "✓ SSD1306 → upypi" 或 "⚠ 蜂鸣器 → 无驱动"

Step 3B 替代推荐（条件触发，见下方说明）
  → approval_request #2: 替代器件推荐

Step 4 输出
  → phase_complete: 结果面板
```

### 消息详情

#### approval_request #1 — 器件确认卡片

用户唯一必须交互的卡片。合并了器件清单 + 模式提示 + 板卡状态。

**结构设计（ASCII 示意）：**

```
┌──────────────────────────────────────────┐
│  确认项目方案                              │
│                                          │
│  项目  温湿度监测报警器                     │
│  功能  定时采集温湿度 → 屏幕显示 → 超阈值报警 │
│  主控  ESP32 DevKit V1 (已选择)  ← 如果有   │
│        未选择，将智能推荐  ← 如果没有         │
│                                          │
│  器件清单:                                │
│  ☑ SHT30    I2C温湿度传感器   用户指定      │
│  ☑ SSD1306  I2C OLED显示屏   系统推荐      │
│  ☑ 蜂鸣器   GPIO执行器       系统推荐      │
│  [+ 添加器件]                             │
│                                          │
│  [确认，开始搜索驱动]  [修改器件清单]        │
└──────────────────────────────────────────┘
```

**JSON 结构：**

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "device_confirm",
    "header": "确认项目方案",
    "question": "请确认以下器件是否正确",
    "summary": {
      "project_name": "温湿度监测报警器",
      "description": "定时采集温湿度 → 屏幕显示 → 超过阈值蜂鸣器报警",
      "board": {
        "status": "selected",
        "display_name": "ESP32 DevKit V1",
        "mcu": "ESP32-WROOM-32"
      }
    },
    "items": [
      {
        "id": "d1",
        "name": "SHT30",
        "subtitle": "I2C 温湿度传感器",
        "meta": "用户指定",
        "selected": true
      },
      {
        "id": "d2",
        "name": "SSD1306",
        "subtitle": "I2C OLED显示屏",
        "meta": "系统推荐",
        "selected": true
      },
      {
        "id": "d3",
        "name": "蜂鸣器",
        "subtitle": "GPIO 执行器",
        "meta": "系统推荐",
        "selected": true
      }
    ],
    "allow_add": true,
    "allow_remove": true,
    "multi_select": true,
    "actions": [
      { "label": "确认，开始搜索驱动", "value": "confirm", "primary": true },
      { "label": "修改器件清单", "value": "modify" }
    ]
  }
}
```

**summary.board 字段说明：**

| board.status | 含义 | 卡片表现 |
|-------------|------|---------|
| `"selected"` | 用户提前选了板卡 | 显示主控名+MCU型号，灰色背景不可改 |
| `"none"` | 用户未选板卡 | 卡片不显示主控，在 select-hw 阶段推荐 |

#### approval_request #2 — 替代器件推荐（条件触发）

**触发条件：** 器件 `source = "system_recommended"`（系统推荐）且驱动搜索无结果。

**不触发条件：** `source = "user_specified"`（用户明确指定）且无驱动 → 走冷硬件路径，不弹替代卡片，仅在 phase_complete warnings 中提示。

```
┌──────────────────────────────────────────┐
│  温湿度传感器：推荐替代器件                 │
│                                          │
│  SHT30 未找到 MicroPython 驱动            │
│                                          │
│  同类别（I2C 温湿度传感器）有现成驱动：      │
│  ┌────────────────────────────────────┐  │
│  │ ★ HDC1080   upypi  推荐             │  │
│  │   精度 ±0.2°C  价格 ~¥8              │  │
│  ├────────────────────────────────────┤  │
│  │   AHT20    upypi                    │  │
│  │   超小封装  价格 ~¥5                  │  │
│  └────────────────────────────────────┘  │
│                                          │
│  [用 HDC1080] [用 AHT20] [仍用 SHT30]    │
└──────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "alternative_device",
    "header": "温湿度传感器：推荐替代器件",
    "question": "SHT30 未找到 MicroPython 驱动。推荐以下同类别已有驱动的替代器件：",
    "items": [
      {
        "id": "alt1",
        "name": "HDC1080",
        "subtitle": "精度 ±0.2°C，价格 ~¥8",
        "meta": "upypi ★ 推荐",
        "selected": false
      },
      {
        "id": "alt2",
        "name": "AHT20",
        "subtitle": "超小封装，价格 ~¥5",
        "meta": "upypi",
        "selected": false
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "用 HDC1080（推荐）", "value": "accept_alt1", "primary": true },
      { "label": "用 AHT20", "value": "accept_alt2" },
      { "label": "仍用 SHT30（冷硬件路径）", "value": "cold_driver" }
    ]
  }
}
```

#### status_update 列表

| step_id | level | message | 触发时机 |
|---------|-------|---------|---------|
| intent_extraction | info | 正在分析需求... | Step 1 开始 |
| intent_done | success | 提取到 3 个器件：SHT30, SSD1306, 蜂鸣器 | Step 1 完成 |
| driver_search | info | 正在搜索驱动... (1/3) | Step 3 开始 |
| driver_found | success | ✓ SSD1306 → upypi (ssd1306-driver v1.3.0) | 每个器件驱动找到 |
| driver_fallback | success | ✓ SHT30 → GitHub (fallback) | 驱动来自 GitHub |
| driver_none | warn | ⚠ 蜂鸣器 → 无需驱动（标准 GPIO） | 无驱动 |
| driver_cold | warn | ⚠ SHT30 → 无驱动，将走冷硬件路径 | 用户指定的器件无驱动 |

#### phase_complete

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "analyze",
    "result": "success",
    "summary": "器件分析完成：3 个器件中找到 2 个驱动，1 个无需驱动",
    "next_phase": "select-hw",
    "artifacts": [
      {
        "type": "table",
        "title": "器件驱动状态",
        "headers": ["器件", "类型", "接口", "驱动来源", "状态"],
        "rows": [
          ["SSD1306", "OLED", "I2C", "upypi", "✓ ssd1306-driver v1.3.0"],
          ["SHT30", "温湿度", "I2C", "none", "⚠ 冷硬件路径（用户指定）"],
          ["蜂鸣器", "执行器", "GPIO", "—", "✓ 无需驱动"]
        ]
      }
    ],
    "warnings": [
      "SHT30 是您指定的器件且无现成驱动，将走冷硬件路径。若想改用已有驱动的温湿度传感器，可在下一步手动替换再分析一次"
    ],
    "errors": [],
    "manifest_content": "{完整的 project-manifest.json JSON 文本}"
  }
}
```

---

## 四、SKILL.md 修改点

共 12 处改动，按执行步骤排列：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 前置检查 | `python --version` + `python -c "import requests"` | 删除。依赖检查由服务器环境保证 | 插件用户不可见服务器环境 |
| 2 | Step 1 | 无变化 | 逻辑不变。新增：读 `pre_selected_board` 和 `preferences` | 接收插件上下文 |
| 3 | Step 2A | AskUserQuestion 选小白/自定义 | **删除整节**。改为读 `preferences.mode`，默认 "beginner" | 模式是用户偏好，不应每次问 |
| 4 | Step 2B Q1 | AskUserQuestion 选 MCU | **条件化**：`pre_selected_board` 有值→跳过；null→不在此阶段问，写入 `mcu_specified=null` | MCU 确认延后到 select-hw |
| 5 | Step 2B Q2 | AskUserQuestion 确认器件 | 改为 `approval_request` #1 | 合并为一张卡片 |
| 6 | Step 2C | AskUserQuestion 场景/供电/性能/输出（最多 4 问） | **小白模式：跳过，用默认值。自定义模式：可选第二张卡片**。`preferences.mode="custom"` 时追加一张 approval_request | 简化交互 |
| 7 | 默认值汇总表 | 表格列举 13 项默认值 | 表格改为按 `preferences.mode` 分流：`beginner`→全默认填充；`custom`→等用户确认后填充 | 逻辑调整 |
| 8 | Step 3 驱动搜索 | 静默搜索，无输出 | 每搜完一个器件发 `status_update` | 给插件端进度信号 |
| 9 | Step 3B 替代推荐 | 纯文本输出 to 命令行 | 文本表格 → 结构化 `approval_request` #2（含 device.source 判断是否触发） | 插件端无法渲染命令行文本 |
| 10 | Step 3 器件来源标记 | 无此字段 | devices[i] 新增 `source` 字段，枚举 `"user_specified"` / `"system_recommended"` | 区分用户指定 vs 系统推荐 |
| 11 | Step 4 输出 manifest | `python init_manifest.py --project-dir {dir} --input {json}` 写本地文件 | LLM 生成 manifest JSON → `script_run(init_manifest.py --stdin)` 插件端校验 → LLM 读回校验结果 → 放入 `phase_complete.manifest_content`。init_manifest.py 在插件端执行，非服务器端 | 服务器不执行脚本 |
| 12 | 强约束 | 第 2 条"不得在器件型号不明确时自行假设" | 保持不变 | 核心约束不动 |

---

## 五、校验脚本改动

### init_manifest.py

**路径：** `G:\MicroPython_Skills\upy-analyze\scripts\init_manifest.py`（由 scaffold 复制到 `{project}/.upy/scripts/init_manifest.py`，插件端执行）

**需要改 2 处：**
- 新增 `--stdin`：从 stdin 读取 manifest JSON，校验后 stdout 输出 `{"status":"ok","manifest":{...}}` 或 `{"status":"fail","errors":[...]}`
- 移除文件写入：不再写本地磁盘，校验结果由 LLM 处理后放入 `phase_complete.manifest_content`

**是否必须：是。** 最后一道防线——确保非法枚举值不进下游。init_manifest.py 在插件端执行，服务器 LLM 不可直接运行脚本。

---

## 六、插件端需要实现的 UI 组件

| 组件 | 对应消息 | 关键功能 |
|------|---------|---------|
| 进度时间线 | status_update × 3~8 条 | 已完成(✓) / 进行中(旋转) / 警告(⚠) / 失败(✗) |
| 审批卡片 | approval_request #1 | 器件多选增减 + 板卡状态显示 + "确认"/"修改"按钮 |
| 替代推荐卡片 | approval_request #2（条件出现） | 替代器件单选 + "仍用原器件"选项 |
| 结果面板 | phase_complete | 器件状态表格 + 警告信息 + 下一步预告 |

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发 `status_update` 序列 → 验证时间线逐条渲染
2. 手动发 `approval_request` #1（上面 JSON）→ 验证：
   - 器件可选中/取消
   - "添加器件"按钮弹出输入框
   - 点击"确认"后发出 `approval_response`
3. 手动发 `approval_request` #2（替代器件）→ 验证单选 + 三个按钮
4. 手动发 `phase_complete` → 验证表格 + 警告提示

### Skill 端测试（无插件）

1. 用 mock_plugin.py 模拟插件应答：
   - 手动构造 start_phase 消息发给 LLM（含 user_description + pre_selected_board + preferences）
   - 对 approval_request #1 自动回复 `{"action": "confirm"}`
   - 对 approval_request #2 自动回复 `{"action": "accept_alt1"}`
2. 检查所有发出的消息 JSON 符合 02-protocol.md Schema
3. 检查 manifest JSON 被 init_manifest.py 校验通过
