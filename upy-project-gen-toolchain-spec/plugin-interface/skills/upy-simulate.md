# upy-simulate 接口定义

> 状态：✅ 已定稿
>
> Phase 4.5 — PC 端全流程业务模拟。读取 firmware/ 全部代码为上下文，LLM 自主设计 Mock 组装 + 调度 + 可视化 + 数据场景，生成 test/pc/sim_main.py 并运行验证。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | simulate |
| 上游 Skill | upy-generate（手动触发）或 upy-autofix（verify 模式自动触发） |
| 下游 Skill | upy-deploy（手动）或回到 upy-autofix（FAIL 时） |
| 一句话职责 | PC 端全流程模拟——LLM 读代码 → 自主设计 Mock/调度/场景 → 生成 sim_main.py → 校验 → 运行 → 输出覆盖报告 |

**两种运行模式：**

| 模式 | 触发方 | 用途 |
|------|--------|------|
| `full` | 用户点击 [上位机模拟] 按钮 | 全新生成 sim_main.py，全量读取 firmware/ |
| `verify` | upy-autofix 修复后自动调用 | 仅重读 changed_files 涉及的文件，更新 sim_main.py 后运行 |

**核心约束：**
- 不修改 firmware/ 下任何文件
- 所有新代码写入 test/pc/
- sim_main.py 必须支持 `--plain` 标志（禁用 rich 格式化，输出纯文本给 stream）
- 默认生成 CLI 模式（rich），不生成 GUI 模式

---

## 二、插件输入 → Skill（P→S）

插件发 **1 条消息** 给服务器启动本 skill：

### Full 模式（用户手动触发）

```json
{
  "type": "start_phase",
  "phase": "simulate",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "full",
    "manifest": { /* 完整的 project-manifest.json */ },
    "user_scenario": null,
    "skip_approval": false
  }
}
```

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `mode` | string | 是 | 插件 | `"full"` / `"verify"` |
| `manifest` | object | 是 | upy-generate 输出 | 完整的 project-manifest.json |
| `user_scenario` | string? | 否 | 用户输入 | 用户在插件中输入的自定义场景描述（如"WiFi 断连 5 秒后自动重连"）。null 表示无自定义场景 |
| `skip_approval` | boolean | 否 | 插件 | 默认 false。true 时跳过 Step 5 的 scenario 选择卡片，直接运行默认推荐场景 |

### Verify 模式（upy-autofix 自动调用）

```json
{
  "type": "start_phase",
  "phase": "simulate",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "verify",
    "manifest": { /* ... */ },
    "changed_files": [
      "firmware/tasks/sensor_task.py",
      "firmware/drivers/sht30/mock.py"
    ],
    "skip_approval": true
  }
}
```

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `changed_files` | string[] | mode=verify 时必填 | upy-autofix | autofix 修改过的文件列表。simulate 只需重读这些文件 + sim_main.py，检查签名是否匹配 |

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
Step 1 全量读取上下文
  → file_operation(read) × 15+（full 模式）
  → file_operation(read) × 1~5（verify 模式，仅 changed_files + sim_main.py）
  → status_update "正在读取 firmware/ 代码..."

Step 1B 项目分类
  → status_update "项目类型：传感器监控 + 告警，无网络"

Step 2 LLM 自主设计
  → status_update "正在设计 Mock 组装方案..."
  → status_update "正在设计数据场景..." × N

Step 3 生成代码
  → file_operation(write) × 1~2: sim_main.py + sim_scheduler.py（timer 模式）
  → status_update "已生成 test/pc/sim_main.py"

Step 4 代码校验
  → script_run(flake8) → script_result
  → script_run(pylint) → script_result
  → status_update "✓ flake8 通过" / "✗ flake8: 3 errors"

Step 5 场景选择（条件触发）
  → approval_request: 场景选择卡片（skip_approval=false 时）
  → 或直接跳过（skip_approval=true 时用推荐场景）

Step 6 运行
  → script_run(sim_main.py --plain --ticks N --scenario X)
  → stream 多条（script_stdout，每 tick 输出一行）
  → script_result（运行结束）

Step 7 输出
  → phase_complete: 覆盖报告面板
```

### 消息详情

#### approval_request — 场景选择卡片（条件触发）

**触发条件：** `skip_approval` = false
**不触发：** `skip_approval` = true（直接运行推荐场景）

```
┌──────────────────────────────────────────┐
│  模拟运行                                  │
│                                          │
│  项目类型: 传感器 ×2, 告警, OLED 显示       │
│  已生成 5 个 scenario:                     │
│    normal, temp_rising, temp_dropping,    │
│    intermittent_failure, sensor_death     │
│                                          │
│  推荐: temp_rising --ticks 60             │
│  （覆盖完整告警循环：触发→冷却→恢复）       │
│                                          │
│  ⚠ normal 场景仅验证数据流通，             │
│     不触发任何业务分支。                   │
│                                          │
│  [运行推荐场景]  [运行 normal]             │
│  [切换场景...]   [自定义场景...]           │
│  [暂不运行]                               │
└──────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "sim_scenario_select",
    "header": "模拟运行",
    "question": "PC 模拟脚本已通过语法校验，是否开始运行？",
    "summary": {
      "project_types": ["sensor_monitoring", "alarm_monitoring", "gui_display"],
      "scenarios": [
        { "name": "temp_rising", "description": "温度持续上升 → 跨越高温阈值 → 告警触发", "recommended": true, "min_ticks": 60 },
        { "name": "temp_dropping", "description": "温度持续下降 → 跨越低温阈值", "recommended": false, "min_ticks": 30 },
        { "name": "normal", "description": "数据在正常范围内波动，不触发任何阈值", "recommended": false, "min_ticks": 30 },
        { "name": "intermittent_failure", "description": "SHT30 间歇性故障 → 验证独立容错", "recommended": false, "min_ticks": 30 },
        { "name": "sensor_death", "description": "SHT30 永久故障 → 验证降级行为", "recommended": false, "min_ticks": 30 }
      ],
      "warning": "normal 场景仅验证数据流通，不触发任何业务分支。"
    },
    "items": [],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "运行 temp_rising（推荐）", "value": "run_recommended", "primary": true },
      { "label": "运行 normal 场景", "value": "run_normal" },
      { "label": "切换场景运行", "value": "custom_scenario" },
      { "label": "自定义场景", "value": "custom_user" },
      { "label": "暂不运行", "value": "skip" }
    ]
  }
}
```

**approval_response 处理：**

| action 值 | 服务器行为 |
|-----------|-----------|
| `run_recommended` | 运行推荐 scenario，`--ticks` 用推荐值 |
| `run_normal` | 运行 normal scenario，`--ticks` 默认 30 |
| `custom_scenario` | 用户在 `notes` 中写 scenario 名称（如 `--scenario sensor_death`） |
| `custom_user` | 用户在 `notes` 中写自然语言描述 → LLM 映射到 mock API → 生成新 scenario → 运行 |
| `skip` | 不运行，直接 phase_complete（result="partial"），保留 sim_main.py |

#### status_update 列表

| step_id | level | message | 触发时机 |
|---------|-------|---------|---------|
| read_context | info | 正在读取 firmware/ 代码... (N/15) | Step 1 开始 |
| read_context_done | success | 已读取 15 个文件，共 XXXX 行 | Step 1 完成 |
| classify | info | 正在分析项目类型... | Step 1B 开始 |
| classify_done | success | 项目类型：传感器监控 + 告警，无网络 | Step 1B 完成 |
| design_mock | info | 正在设计 Mock 组装方案... | Step 2 开始 |
| design_scenario | info | 正在设计数据场景... (N/M) | Step 2D |
| scenario_done | success | 已生成 5 个 scenario，覆盖 3/5 维度 | Step 2D 完成 |
| generate_code | info | 正在生成 sim_main.py... | Step 3 |
| write_sim | success | ✓ 已生成 test/pc/sim_main.py (XXX 行) | sim_main.py 写入完成 |
| lint_flake8 | info | 正在校验 flake8... | Step 4 开始 |
| lint_flake8_pass | success | ✓ flake8 通过 | flake8 无错误 |
| lint_flake8_fail | warn | ✗ flake8: N errors → 正在修复 | flake8 有错误 |
| lint_pylint | info | 正在校验 pylint... | pylint 开始 |
| lint_pylint_pass | success | ✓ pylint 通过 | pylint 无错误 |
| lint_pylint_fail | warn | ✗ pylint: N issues → 正在修复 | pylint 有警告/错误 |
| lint_retry | info | 第 N 轮修复... | 修复后重新校验 |
| lint_max_retry | error | 已修复 5 轮仍未通过，请手动检查 | 超过 5 轮 |
| sim_running | info | 正在运行 sim_main.py --scenario temp_rising --ticks 60 | Step 6 开始 |
| sim_tick | info | (通过 stream 实时输出) | 每 tick 输出 |
| sim_done_pass | success | ✓ 模拟通过 — 所有 @Coverage 事件在预期 tick 触发 | PASS |
| sim_done_weak | warn | ⚠ 弱通过 — 3/5 维度已覆盖，2 个未覆盖 | WEAK_PASS |
| sim_done_fail | error | ✗ 模拟失败 — Python Traceback | FAIL |

#### phase_complete

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "simulate",
    "result": "success",
    "summary": "模拟完成：temp_rising 场景 PASS，5/5 @Coverage 事件在预期范围触发",
    "next_phase": "deploy",
    "artifacts": [
      {
        "type": "markdown",
        "title": "覆盖报告",
        "content": "### Simulation Coverage Report\n\n| 维度 | 状态 | 说明 |\n|------|------|------|\n| [sensor] 传感器读取 | ✅ | 60/60 ticks 正常 |\n| [sensor] 传感器故障容错 | ✅ | 触发 → OSError at ticks 3,6,9... |\n| [alarm] 高温告警触发 | ✅ | 触发 → temp ≥ 35.0 at tick 21 |\n| [alarm] 执行器激活 | ✅ | Buzzer ON + LED ON at tick 21 |\n| [alarm] 告警冷却 | ✅ | cooling active ticks 21-50 |\n| [alarm] 低温告警 | ⚠ 未覆盖 | 当前 scenario 不覆盖 |\n| [alarm] 湿度告警 | ⚠ 未覆盖 | 无 scenario 覆盖 80%/20% 湿度阈值 |\n\n**Result: WEAK_PASS**\n\n建议: `python test/pc/sim_main.py --scenario temp_dropping --ticks 30`\n建议: 新增 humidity_high scenario 覆盖 80% 湿度阈值"
      }
    ],
    "warnings": [
      "低温告警阈值未覆盖，建议运行 temp_dropping 场景",
      "湿度告警 80%/20% 阈值未被任何 scenario 覆盖"
    ],
    "errors": []
  }
}
```

**result 取值：**

| result | 条件 |
|--------|------|
| `success` | 运行通过（PASS），所有 @Coverage 事件触发 |
| `partial` | 弱通过（WEAK_PASS），部分维度未覆盖；或用户选择"暂不运行" |
| `failed` | 运行失败（FAIL），有 Traceback 或超过 5 轮修复 |

---

## 四、SKILL.md 修改点

共 6 处改动：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | Step 1 全量读取 | LLM 直接调用 Read 工具读文件 | 通过 `file_operation(read)` 逐文件读取（服务器通过插件读本地文件） | 服务器端无本地文件系统访问权 |
| 2 | Step 4 校验 | `Bash: python -m flake8 ...` + `python -m pylint ...` | `script_run(flake8)` + `script_run(pylint)`，解析 script_result.stdout/stderr | 脚本执行统一走插件 |
| 3 | Step 5 询问用户 | `AskUserQuestion(...)` (CLI 问答) | `approval_request` 场景选择卡片 | 插件端渲染审批卡片，非命令行交互 |
| 4 | Step 6 运行 | `Bash: python test/pc/sim_main.py --ticks N ...` | `script_run(sim_main.py --plain --ticks N ...)`，每 tick 输出经 `stream` 实时推送 | `--plain` 禁用 rich 格式化使输出可管道化；stream 让插件端实时展示 |
| 5 | sim_main.py 生成约束 | 无 `--plain` 要求 | LLM 必须在 sim_main.py 中支持 `--plain` 标志：当 `--plain` 时禁用 rich Live/Table/Panel，改用 `print()` 逐行输出 JSON 格式（`{"tick": N, ...}`） | 通过 script_run 运行时无 TTY，rich Live 会产生 ANSI 乱码 |
| 6 | 新增 verify 模式 | 无此模式 | 新增 `mode=verify` 入口：仅读取 changed_files + sim_main.py，检测签名变化 → 更新 sim_main.py → 直接运行推荐场景（skip_approval=true） | autofix→simulate 快速验证闭环 |

### sim_main.py `--plain` 输出格式规范

当 `--plain` 时，每 tick 输出一行 JSON：

```json
{"tick": 1, "temp": 25.1, "hum": 61.2, "alarm": false, "buzzer": false, "led": false, "display": "T:25.1 H:61.2\nOK"}
{"tick": 2, "temp": 25.3, "hum": 60.8, "alarm": false, "buzzer": false, "led": false, "display": "T:25.3 H:60.8\nOK"}
...
{"tick": 21, "temp": 35.2, "hum": 58.1, "alarm": true, "buzzer": true, "led": true, "display": "T:35.2 H:58.1\nALARM!"}
```

字段由 LLM 根据项目自行决定，但必须包含 `tick`。`display` 字段可选（有 display 器件时）。

---

## 五、校验脚本改动

无需新增校验脚本。sim_main.py 本身经过 flake8 + pylint 两道校验，等价于校验。

### 对 upy-generate 模板的影响

upy-generate 的 scaffold 模板中，`sim_main.py` 不是模板文件（由 upy-simulate 动态生成），无影响。但 `firmware/main.py` 模板中的调度回调应预留接口，不涉及本次修改。

---

## 六、插件端需要实现的 UI 组件

| 组件 | 对应消息 | 关键功能 |
|------|---------|---------|
| 进度时间线 | status_update × N | 文件读取 → 分类 → 设计 → 生成 → 校验 → 运行 六阶段进度 |
| 场景选择卡片 | approval_request | 场景列表 + 推荐标记 + "运行推荐"/"自定义"/"暂不运行"按钮 |
| 终端输出面板 | stream（script_stdout） | 实时显示每 tick 的 JSON 行，可切换为表格视图 |
| 覆盖报告面板 | phase_complete（markdown artifact） | 渲染覆盖率表格，PASS/WEAK_PASS/FAIL 状态标记 |
| [上位机模拟] 按钮 | 触发 start_phase(mode="full") | 在 upy-generate 完成后启用 |
| [重新模拟] 按钮 | 触发 start_phase(mode="full") | 模拟完成后替换"上位机模拟"按钮，可重新运行 |

### 终端输出面板说明

插件收到 `stream` 消息（`stream_type: "script_stdout"`）后实时渲染。当 `--plain` 时每行是 JSON，插件可解析为结构化数据：
- **默认视图**：原始文本滚动（类似终端）
- **表格视图**：解析 JSON 行，渲染为动态表格（每行一个 tick，列 = JSON key）
- 用户可在两种视图间切换

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发 `status_update` 序列 → 验证六阶段时间线渲染
2. 手动发 `approval_request`（场景选择卡片）→ 验证：
   - 推荐 scenario 高亮显示
   - 点击"运行推荐"发出 `approval_response(action="run_recommended")`
   - 点击"暂不运行"发出 `approval_response(action="skip")`
3. 手动发 `stream` 序列（模拟 `--plain` 每 tick JSON 行）→ 验证终端面板实时更新 + 表格视图切换
4. 手动发 `phase_complete`（markdown 覆盖报告）→ 验证覆盖率表格 + PASS/WEAK_PASS/FAIL 标记渲染

### Skill 端测试（无插件）

1. 用 mock_plugin.py 模拟插件应答：
   - 手动构造 start_phase（mode="full", manifest, skip_approval=true）
   - 对 file_operation(read) 自动返回文件内容（需准备一个完整的 firmware/ 目录）
   - 对 script_run(flake8/pylint) 自动返回 `{"exit_code": 0, "stdout": ""}`
   - 对 script_run(sim_main.py) 自动返回模拟输出
2. 检查 sim_main.py 头部含有 `@ProjectTypes` + `@CoverageReport` 注释
3. 检查 sim_main.py 处理 `--plain` 标志正确
4. 检查所有发出的消息 JSON 符合 02-protocol.md Schema
5. Verify 模式：构造 start_phase（mode="verify", changed_files=["firmware/tasks/sensor.py"]）→ 验证仅读取 changed_files + sim_main.py
