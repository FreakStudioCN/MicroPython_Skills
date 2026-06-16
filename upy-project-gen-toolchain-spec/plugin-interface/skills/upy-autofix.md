# upy-autofix 接口定义

> 状态：✅ 已定稿
>
> Phase 6 — 错误库驱动的交互式单点排查。匹配 error_lib → 适配 debug_steps → 逐步自动/人工交替执行 → 定位根因 → 委托上游 skill 修复 → 反哺错误库。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | autofix |
| 上游 Skill | upy-deploy（FAIL 自动触发）或用户手动点击 [调试] 按钮 |
| 下游 Skill | upy-generate / upy-select-hw / upy-analyze（委托修复）；upy-deploy（验证）；upy-simulate（可选 PC 验证） |
| 一句话职责 | 查错误库 → 生成排查计划 → 逐步引导（自动检测 + 人工配合）→ 定位根因 → 修复 → 验证 → 反哺知识库 |

**核心变化：** 从"自动修 3 次放弃"变为"错误库驱动 + 结构化 debug_steps + 逐步自动/人工交替排查"。LLM 只做**匹配+适配参数+步骤调度**，不做步骤生成。

---

## 二、插件输入 → Skill（P→S）

### 启动 autofix

```json
{
  "type": "start_phase",
  "phase": "autofix",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "auto",
    "error_context": { /* deploy phase_complete 携带的 error_context */ },
    "user_symptom": null,
    "user_suspect": null,
    "max_attempts": 3
  }
}
```

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `mode` | string | 是 | 触发方 | `"auto"` — deploy FAIL 自动触发；`"manual"` — 用户点击 [调试] 按钮 |
| `error_context` | object | 是 | deploy phase_complete | 含 traceback / file_path / line_number / repl_output / log_report |
| `user_symptom` | string? | 否 | 用户输入 | 用户补充的观察（"SHT30 模块的 LED 不亮"） |
| `user_suspect` | string? | 否 | 用户输入 | 用户怀疑的原因（"可能是面包板接触不良"） |
| `max_attempts` | number | 否 | 插件设置 | 默认 3 |

### 中途用户介入

```json
{
  "type": "user_intervention",
  "payload": {
    "action": "pause",
    "note": "我刚发现 SDA 杜邦线松了，已重新插紧",
    "resume_action": "retry_current_step"
  }
}
```

| action | 说明 |
|--------|------|
| `pause` | 暂停，用户补充信息后继续 |
| `skip_step` | 跳过当前步骤 |
| `abort` | 终止排查，生成诊断包，进入人工模式 |
| `add_note` | 不暂停，追加观察记录 |

### 用户管理错误库

```json
{
  "type": "error_lib_update",
  "payload": {
    "action": "add",
    "entry": { /* error_lib 条目完整结构 */ }
  }
}
```

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
Phase 0: 用户输入（mode="manual" 时）
  → approval_request #1: 错误现象输入卡片 (debug_symptom_input)

Phase 1: 查库 + 生成排查计划
  → status_update "正在搜索错误库..."
  → file_operation(read) → error_lib.json (项目级)
  → file_operation(read) → error_lib.json (全局级)
  → status_update "✓ 匹配到 2 条类似案例，最高分 95"
  → status_update "正在适配排查步骤..."
  → phase_complete (debug_plan artifact)

Phase 2: 逐步执行排查 (循环)
  对每个 step:
    ├── auto_verify / auto_detect:
    │     → status_update "步骤 N/M: {title}"
    │     → device_command(action="exec", code=...)
    │     → device_result
    │     → approval_request: 结果确认卡片 (debug_step_result)
    │
    ├── user_measure / user_observe:
    │     → status_update "步骤 N/M: {title}"
    │     → approval_request: 引导操作卡片 (debug_user_measure / debug_user_observe)
    │
    └── user_action:
          → status_update "步骤 N/M: {title}"
          → approval_request: 引导操作卡片 (debug_user_action)
          → 用户完成操作 → device_command(action="exec") 自动复测
          → approval_request: 结果确认卡片

  根据 step.on_pass / step.on_fail 跳转:
    → continue → 下一步
    → goto_step N → 跳到步骤 N
    → abort → 跳出循环，展示排查指引
    → resolve → 跳出循环，进入 Phase 3

Phase 3: 修复 + 验证 + 记录
  → status_update "根因定位: {root_cause}"
  → (如需改代码) 委托 upy-generate / upy-select-hw
  → deploy(mode="incremental")
  → status_update "✓ 修复验证通过"
  → file_operation(write) → error_lib.json (更新统计)
  → phase_complete (result="success")

Phase 4: 3 次排查未解决
  → status_update "自动排查未定位根因，正在生成诊断包..."
  → file_operation(write) → diagnostic_bundle.json
  → phase_complete (result="failed", artifact=diagnostic_bundle)
  → approval_request: 诊断包导出卡片 (debug_bundle_export)
```

### 关键 approval_request 卡片

#### 卡片 #1 — 错误现象输入（debug_symptom_input）

```
┌──────────────────────────────────────────┐
│  🔍 调试助手                               │
│                                          │
│  检测到部署失败：                           │
│  ┌────────────────────────────────────┐  │
│  │ OSError: [Errno 19] ENODEV         │  │
│  │ I2C scan: []                       │  │
│  │ at firmware/tasks/sensor_task.py:23 │  │
│  └────────────────────────────────────┘  │
│                                          │
│  请补充你观察到的现象：                     │
│  ┌────────────────────────────────────┐  │
│  │ (placeholder: 模块LED亮吗？接线检过?)│  │
│  └────────────────────────────────────┘  │
│                                          │
│  你怀疑的原因（可选）：                     │
│  ┌────────────────────────────────────┐  │
│  │ (placeholder: 供电/接线/模块损坏...) │  │
│  └────────────────────────────────────┘  │
│                                          │
│  [开始排查]  [跳过，自动修复]              │
└──────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "debug_symptom_input",
    "header": "调试助手",
    "question": "请补充观察到的错误现象，帮助快速定位问题",
    "summary": {
      "error_preview": "OSError: [Errno 19] ENODEV\nI2C scan: []\nat firmware/tasks/sensor_task.py:23",
      "error_type": "OSError_19",
      "affected_device": "SHT30"
    },
    "items": [],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "开始排查", "value": "start_debug", "primary": true },
      { "label": "跳过，自动修复", "value": "skip_to_autofix" }
    ]
  }
}
```

#### 卡片 #2 — 引导操作（debug_user_measure）

```
┌──────────────────────────────────────────┐
│  步骤 3/6: 测量 I2C 总线电压               │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  📐 操作指引                        │  │
│  │                                    │  │
│  │  工具: 万用表（直流电压档 DCV）       │  │
│  │                                    │  │
│  │  1. 红表笔接 SDA 引脚 (GPIO21)       │  │
│  │  2. 黑表笔接 GND                    │  │
│  │  3. 记录电压值                      │  │
│  │  4. 同样方法测 SCL 引脚 (GPIO22)     │  │
│  │                                    │  │
│  │  正常值: 3.3V ± 0.3V                │  │
│  │  可接受: 3.0V ~ 3.6V                │  │
│  │  异常: < 3.0V 或 > 3.6V             │  │
│  │                                    │  │
│  │  [I2C 总线电压测量示意图]             │  │
│  └────────────────────────────────────┘  │
│                                          │
│  SDA 引脚电压 (GPIO21):                   │
│  [~3.3V 正常]  [< 3.0V 偏低]  [~0V 无电压] │
│                                          │
│  SCL 引脚电压 (GPIO22):                   │
│  [~3.3V 正常]  [< 3.0V 偏低]  [~0V 无电压] │
│                                          │
│  [无法测量，跳过]                          │
└──────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "debug_user_measure",
    "header": "步骤 3/6: 测量 I2C 总线电压",
    "question": "请用万用表测量 I2C 总线电压并选择结果",
    "summary": {
      "step_id": 3,
      "step_type": "user_measure",
      "expected_normal": "SDA 和 SCL 均为 3.3V 左右（有上拉电阻）",
      "expected_abnormal": "任一引脚电压 < 3.0V（上拉缺失）或 ~0V（无上拉）"
    },
    "guidance": {
      "tool": "万用表（直流电压档 DCV）",
      "steps": [
        "红表笔接 SDA 引脚 (GPIO21)，黑表笔接 GND，记录电压",
        "红表笔接 SCL 引脚 (GPIO22)，黑表笔接 GND，记录电压"
      ],
      "normal_range": { "min": 3.0, "max": 3.6, "unit": "V" },
      "diagram_ref": "i2c_bus_voltage_measure"
    },
    "items": [
      {
        "id": "sda_normal",
        "name": "SDA: ~3.3V 正常",
        "subtitle": "GPIO21 电压在正常范围",
        "meta": "",
        "selected": false
      },
      {
        "id": "sda_low",
        "name": "SDA: < 3.0V 偏低",
        "subtitle": "GPIO21 电压异常",
        "meta": "",
        "selected": false
      },
      {
        "id": "sda_zero",
        "name": "SDA: ~0V 无电压",
        "subtitle": "GPIO21 可能悬空或短路",
        "meta": "",
        "selected": false
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": true,
    "actions": [
      { "label": "确认", "value": "confirm", "primary": true },
      { "label": "无法测量，跳过", "value": "skip" }
    ]
  }
}
```

#### 卡片 #3 — 结果确认（debug_step_result）

```
┌──────────────────────────────────────────┐
│  步骤 2/6: I2C 总线扫描 (自动执行)          │
│                                          │
│  预期现象:                                │
│  ✓ I2C.scan() 应返回 [0x3C, 0x44]        │
│    (SSD1306 @ 0x3C, SHT30 @ 0x44)       │
│                                          │
│  实际输出:                                │
│  ┌────────────────────────────────────┐  │
│  │ []                                 │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ❌ 未检测到任何 I2C 设备                  │
│                                          │
│  是否看到以上输出？                        │
│  [是，输出为 []]  [不确定]                 │
│                                          │
│  补充观察（可选）：                        │
│  ┌────────────────────────────────────┐  │
│  │ (placeholder)                     │  │
│  └────────────────────────────────────┘  │
│                                          │
│  → 下一步: 测量 I2C 总线电压               │
└──────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "debug_step_result",
    "header": "步骤 2/6: I2C 总线扫描",
    "question": "是否看到预期输出？",
    "summary": {
      "step_id": 2,
      "step_type": "auto_detect",
      "expected_normal": "I2C.scan() 应返回 [0x3C, 0x44]",
      "actual_output": "[]",
      "verdict": "fail",
      "next_step": "测量 I2C 总线电压"
    },
    "items": [],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "是，输出如上", "value": "confirm_output", "primary": true },
      { "label": "不确定", "value": "unsure" },
      { "label": "补充观察...", "value": "add_note" }
    ]
  }
}
```

### status_update 列表

| step_id | level | message | 触发时机 |
|---------|-------|---------|---------|
| search_lib | info | 正在搜索错误库... | Phase 1 开始 |
| lib_match | success | ✓ 匹配到 N 条案例，最高分 XX | 匹配成功 |
| lib_no_match | warn | ⚠ 错误库无匹配，将从头分析 | 无匹配 |
| adapt_steps | info | 正在适配排查步骤... | 填充模板参数 |
| plan_ready | success | ✓ 排查计划：M 步，预计 X 分钟 | Phase 2 开始前 |
| step_start | info | 步骤 N/M: {title} | 每步开始 |
| step_auto_exec | info | 正在执行自动检测... | auto_verify/auto_detect |
| step_auto_pass | success | ✓ {title} — 正常 | 自动步骤通过 |
| step_auto_fail | warn | ⚠ {title} — 异常 | 自动步骤失败 |
| step_user_wait | info | ⏳ 等待用户操作... | user_measure/action |
| step_user_done | success | ✓ 用户反馈已收到 | 用户操作完成 |
| step_skip | info | ⛔ 跳过步骤 N | 用户跳过 |
| root_cause_found | success | ✓ 根因定位: {description} | Phase 3 开始 |
| fix_delegate | info | 正在委托 {skill} 修复... | 委托上游 skill |
| fix_verify | info | 正在验证修复结果... | deploy 阶段 |
| fix_done | success | ✓ 修复验证通过 | 验证通过 |
| lib_update | info | 正在更新错误库... | 写入 error_lib |
| bundle_gen | info | 正在生成诊断包... | Phase 4 |
| bundle_done | success | ✓ 诊断包已生成 | 诊断包完成 |

### phase_complete

**PASS：**

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "autofix",
    "result": "success",
    "summary": "根因定位：SDA/SCL 缺少上拉电阻。已添加 4.7kΩ 上拉，I2C 扫描正常。",
    "next_phase": null,
    "artifacts": [
      {
        "type": "table",
        "title": "排查过程",
        "headers": ["步骤", "类型", "标题", "结果"],
        "rows": [
          ["1/6", "自动", "确认 MCU 基本功能", "✓ MCU_OK"],
          ["2/6", "自动", "I2C 总线扫描", "✗ []"],
          ["3/6", "用户测量", "测量 I2C 总线电压", "✓ SDA:0.2V SCL:0.1V — 异常"],
          ["4/6", "用户操作", "添加 4.7kΩ 上拉电阻", "✓ 完成 → 复测 SCAN:[0x3C,0x44]"]
        ]
      },
      {
        "type": "markdown",
        "title": "根因分析",
        "content": "### 根因\n\nSDA/SCL 引脚缺少外部上拉电阻。ESP32 内部上拉 ~45kΩ 太弱，I2C 需要 4.7kΩ 外部上拉到 3.3V。\n\n症状：I2C.scan() 返回空。\n\n修复：SDA(GPIO21)→4.7kΩ→3.3V，SCL(GPIO22)→4.7kΩ→3.3V。\n\n来源：错误库 err_sht30_i2c_19（已验证，13 次成功）"
      }
    ],
    "warnings": [],
    "errors": [],
    "error_lib_updated": true,
    "matched_entry_id": "err_sht30_i2c_19"
  }
}
```

**FAIL（3 次排查未解决）：**

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "autofix",
    "result": "failed",
    "summary": "3 轮排查未定位根因。已生成诊断包供人工分析。",
    "next_phase": null,
    "artifacts": [
      {
        "type": "table",
        "title": "排查过程",
        "headers": ["轮次", "步骤", "类型", "标题", "结果"],
        "rows": [
          ["1", "1/6", "自动", "MCU 基本功能", "✓"],
          ["1", "2/6", "自动", "I2C 扫描", "✗ []"],
          ["1", "3/6", "用户测量", "总线电压", "✓ 正常 3.3V"],
          ["1", "4/6", "用户操作", "添加上拉", "✗ 仍为空"],
          ["1", "5/6", "用户测量", "SHT30 供电", "✓ 正常 3.3V"],
          ["1", "6/6", "用户操作", "替换传感器", "✗ 仍为空"],
          ["2", "1/1", "自动", "降低 I2C 频率", "✗ 仍为空"],
          ["3", "1/2", "自动", "尝试 SoftI2C", "✗ 仍为空"],
          ["3", "2/2", "自动", "板载 LED", "✓"]
        ]
      },
      {
        "type": "markdown",
        "title": "LLM 分析",
        "content": "### 已排除\n\n- I2C 频率 (100kHz/400kHz 均失败)\n- 引脚配置 (SoftI2C 也失败)\n- MCU 供电/复位 (板载 LED 正常)\n- I2C 总线电压 (正常 3.3V)\n- 上拉电阻 (已添加)\n- 传感器供电 (正常 3.3V)\n- 传感器模块 (替换后仍失败)\n\n### 仍怀疑\n\n- MCU I2C 外设硬件损坏（小概率）\n- 面包板内部短路（需万用表通断档逐一排查）\n\n### 知识盲区\n\n无法远程区分 'I2C 外设损坏' 和 '面包板隐性短路'。建议换一块 MCU 模块交叉验证。"
      }
    ],
    "warnings": ["排查步骤耗尽，未定位根因"],
    "errors": ["自动排查未解决"],
    "diagnostic_bundle_path": ".upy/diagnostic_bundles/bundle_20260617T103000.json",
    "error_lib_updated": true
  }
}
```

---

## 四、SKILL.md 修改点

共 14 处改动：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 角色定位 | 编排协调层，triage.py 采集 + LLM 研判 + 委托修复 | **错误库驱动的交互式单点排查**。LLM 匹配 error_lib → 适配 debug_steps → 逐步执行 → 用户配合 | 从"自动修 3 次"变为"引导式排查" |
| 2 | 前置条件 | triage.py + deploy_logs/ | 新增 `error_lib.json`（项目级 `.upy/` + 全局级 `~/.upy/`） | 查库是第一步 |
| 3 | Step 1 | `python triage.py --log-dir ... --port COM3` | **删除**。日志解析由 LLM 从 error_context 直接读。I2C 扫描移入 debug_steps 的 auto_detect 步骤 | 服务端不跑本地脚本 |
| 4 | Step 2 研判 | 7 种错误分类 → 分流到不同 skill | **Phase 1: 查库匹配**。提取签名(error_type+keywords+device) → file_operation(read) error_lib.json → 匹配打分 → 取最高分条目 → 填充模板参数 `{I2C_SCL}` `{I2C_SDA}` 等 → 生成 debug_plan | 错误库驱动，LLM 不做步骤生成 |
| 5 | Step 2.5 硬件信号验证 | LLM 生成 sanity_config.json → `python hardware_sanity.py` → ask_user | **合并到 Phase 2 debug_steps 执行循环**。auto_verify/auto_detect → device_command。user_measure/user_observe → approval_request | 统一为 6 种步骤类型 |
| 6 | Step 2.5 用户反馈 | hardware_sanity.py 设 `_pending_question` → LLM 调 AskUserQuestion | **改为 approval_request 卡片**。user_feedback 模式的结果直接映射到 debug_step_result / debug_user_measure 卡片 | 插件端统一渲染审批卡片 |
| 7 | Step 3 委托 | `Skill("upy-generate")` / `Skill("upy-select-hw")` | **服务端内部调用** + phase 切换。LLM 以 mode="fix" + error_context 启动 generate，phase 字段切换通知插件 | 同进程调用，phase 让插件感知进度 |
| 8 | Step 4 验证 | `Skill("upy-simulate")` → `Skill("upy-deploy")` | deploy(mode="incremental", changed_files)。每次验证前发 approval_request 展示"预期正常现象"，运行后发结果确认卡片 | 用户参与验证 |
| 9 | Step 5 硬件排查指引 | 纯文本中文指引 | **整合到 debug_steps 的 fail_guidance 字段**。abort 时展示结构化引导卡片（含接线图引用） | 非纯文本，含图表 |
| 10 | Step 6 3 次失败 | git rollback + 纯文本卡点报告 | **生成 diagnostic_bundle.json**（结构化 JSON，含所有尝试+代码快照+LLM 分析+知识盲区）。**不自动回滚**，保留现场供人工分析 | 给人+LLM 联合分析，非简单放弃 |
| 11 | Step 7 错误记录 | `logs/error_report.json` 追加 | **写入 error_lib.json**。成功→更新 success_count + avg_steps_to_resolve。失败→追加 suspected 条目。人工解决后→写入 verified 条目 | 统一为 error_lib |
| 12 | **新增** Phase 0 | 无 | `approval_request` 错误现象输入卡片：REPL 输出预填 + 用户补充观察 + 怀疑原因。mode="manual" 时展示 | 用户参与入口 |
| 13 | **新增** 错误库自进化 | 无 | 排查结束→更新条目统计。LLM 追加的新步骤→追加到条目 debug_steps。3 次全败后人工输入根因→创建 verified 条目 | 知识积累 |
| 14 | **新增** 适配参数提取 | 无 | LLM 从 board.py + manifest 提取实际引脚号/地址，填充 debug_steps 模板中的 `{I2C_SCL}`, `{SHT30_ADDR}` 等变量 | 通用模板→项目特定化 |

---

## 五、校验脚本

### validate_error_lib.py（新增）

**路径：** `G:\MicroPython_Skills\upy-autofix\scripts\validate_error_lib.py`

校验 error_lib.json 结构完整性。在 LLM 写入 error_lib 后自动运行。

| 检查项 | 说明 |
|--------|------|
| JSON 语法 | 可解析 |
| 必填字段 | 每个 entry 含 id / signature / classification / debug_steps / metadata |
| debug_steps 完整性 | 每个 step 含 step_id / type / title / expected_normal / on_pass / on_fail |
| step.type 枚举 | `auto_verify` / `auto_detect` / `user_measure` / `user_observe` / `user_action` / `info_only` |
| on_pass/on_fail 枚举 | `continue` / `goto_step` / `abort` / `retry_step` / `resolve` |
| goto_step/retry_step 目标存在 | `on_pass_target` / `on_fail_target` / `retry_step_id` 指向的 step_id 必须存在 |
| step_id 唯一 | 同 entry 内无重复 |
| certainty 枚举 | `verified` / `suspected` / `speculative` |
| source 枚举 | `manual` / `auto` |

stdout:
```json
{ "status": "pass", "errors": [], "warnings": [] }
```

### validate_diagnostic_bundle.py（新增）

**路径：** `G:\MicroPython_Skills\upy-autofix\scripts\validate_diagnostic_bundle.py`

校验诊断包结构完整性。

| 检查项 | 说明 |
|--------|------|
| JSON 语法 | 可解析 |
| 必填顶层字段 | bundle_id / project / error_summary / attempts / llm_analysis |
| attempts 连续 | attempt_number 从 1 递增 |
| error_summary.across_attempts | 与 attempts 数量一致 |
| code_snapshot 文件存在 | 引用的文件路径在项目目录中存在 |

### triage.py（重构）

**路径：** `G:\MicroPython_Skills\upy-autofix\scripts\triage.py`

| 改动 | 内容 |
|------|------|
| 移除 `--port` / `--sda` / `--scl` | 不再调 mpremote |
| 新增 `--input` | 从 stdin 读取日志文本（服务端通过 file_operation 读取后 pipe），替代 `--log-dir` |
| 保留 `parse_errors()` | 正则匹配逻辑不变 |
| 保留 `--snapshot` / `--rollback` | git 操作不变 |
| 新增 `--validate-lib` | 调 validate_error_lib.py 校验 error_lib.json |

### hardware_sanity.py（轻度修改）

**路径：** `G:\MicroPython_Skills\upy-autofix\scripts\hardware_sanity.py`

| 改动 | 内容 |
|------|------|
| `_pending_question` 字段扩展 | 新增 `expected_behavior` + `abnormal_options[]` 字段，供 LLM 生成 approval_request |
| 新增 `--stdin-config` | 从 stdin 读取配置 JSON，避免服务端写文件到磁盘 |

---

## 六、模板文件

### error_lib.json

**路径：** `G:\MicroPython_Skills\upy-autofix\templates\error_lib.json`

空模板，由 `init_scaffold.py` 拷贝到 `{project}/.upy/error_lib.json`。

```json
{
  "$schema": "https://upy-toolchain/error_lib/v1",
  "version": "1.0",
  "updated_at": "",
  "entries": []
}
```

**数据库构建机制** — 详见 [error_lib.json 构建规范](#八error_libjson-构建规范)。

### diagnostic_bundle_schema.json

**路径：** `G:\MicroPython_Skills\upy-autofix\templates\diagnostic_bundle_schema.json`

诊断包 schema，供 validate_diagnostic_bundle.py 引用。autofix 3 次排查失败时由 LLM 动态生成。

---

## 七、插件端 UI 组件

| 组件 | 对应消息 | 说明 |
|------|---------|------|
| [调试] 按钮 | 触发 start_phase(mode="manual") | deploy FAIL 后出现在结果面板 |
| 错误现象输入卡片 | approval_request `debug_symptom_input` | REPL 输出预填 + 用户补充 |
| 排查计划面板 | phase_complete artifact `debug_plan` | 步骤列表 + 匹配来源 + 预计时间 |
| 引导操作卡片 | approval_request `debug_user_measure` / `debug_user_action` | 含操作步骤/接线图/正常范围 |
| 结果确认卡片 | approval_request `debug_step_result` | "是否看到预期现象？" |
| 诊断包导出卡片 | approval_request `debug_bundle_export` | 3 次排查失败后 |
| 错误库管理面板 | error_lib_update | 浏览/添加/编辑/删除条目 |

---

## 八、error_lib.json 构建规范

### 文件层级

```
项目级: {project_dir}/.upy/error_lib.json    ← 当前项目特有，由 init_scaffold 从模板创建
全局级: ~/.upy/error_lib.json                 ← 跨项目共享，由插件管理同步
```

### 查库优先级

```
1. 先查项目级 → 匹配到（score ≥ 40）→ 直接使用
2. 项目级无匹配 → 查全局级 → 匹配到 → 使用
3. 两级都匹配 → 合并结果，按 score 排序，去重（同 id 取 score 高的）
4. 两级都无匹配 → LLM 从零生成 debug_steps（兜底）
```

### 数据来源

| 来源 | 写入位置 | 触发条件 | certainty |
|------|---------|---------|-----------|
| 用户手动上传（插件 [上传案例] 按钮） | 全局级 | 用户主动操作 | `verified` |
| autofix 排查成功（沿用已有条目） | 项目级 | success_count++ / avg_steps 更新 | 不变 |
| autofix 排查成功（LLM 自定义新步骤） | 项目级 | 新步骤追加到条目 debug_steps 末尾 | 不变 |
| autofix 排查成功（全新问题） | 项目级 | 创建新条目 | `suspected` |
| autofix 3 次全败 + 人工解决 | 全局级 | 人工输入根因后创建 | `verified` |

### 提升到全局级

当项目级条目同时满足以下条件，LLM 建议提升：

```
success_count ≥ 3  AND  certainty = "verified"  AND  source = "auto"
```

→ `approval_request`: "该案例已验证 3 次，是否提升到全局错误库？" → 用户确认 → `error_lib_update(action="promote", entry_id="...")`。

### 条目生命周期

```
用户上传 (manual, verified)
  → 被 autofix 匹配使用 → success_count++

autofix 自动创建 (auto, suspected)
  → 被后续排查验证成功 1 次 → suspected → success_count=1
  → 成功 3 次 → LLM 建议提升 → 用户确认 → verified + 移至全局级

verified 条目失败 1 次
  → fail_count++ → 仍为 verified（偶发）
  → 连续失败 3 次 → 降级为 suspected → LLM 审查 debug_steps
```

### 匹配打分算法

```
score = (regex_match ? 50 : 0)
      + (keyword_intersection / total_keywords * 30)
      + (match_device_models 交集非空 ? 10 : 0)
      + (match_bus_types 交集非空 ? 10 : 0)
      + certainty_bonus (verified=20, suspected=10, speculative=0)
      + min(success_count, 20)
```

- score ≥ 80 → 高置信度，直接执行，不展示排查计划卡（减少交互）
- score 40~79 → 中置信度，展示排查计划卡供用户确认
- score < 40 → 低置信度/无匹配，LLM 从零生成 debug_steps + 展示计划卡

### 模板参数填充

debug_steps 中 `{VAR}` 形式的占位符由 LLM 从项目上下文自动填充：

| 模板变量 | 来源 | 示例 |
|---------|------|------|
| `{I2C_SCL}` | firmware/board.py → I2C_SCL | `22` |
| `{I2C_SDA}` | firmware/board.py → I2C_SDA | `21` |
| `{I2C_BUS_ID}` | firmware/board.py | `0` |
| `{SHT30_ADDR}` | project-manifest.json → devices[].address | `0x44` |
| `{MCU_LED_PIN}` | boards/*.json → onboard_led | `2` |
| `{ALL_I2C_ADDRS}` | project-manifest.json → devices[].address 拼接 | `[0x3C, 0x44]` |
| `{DRIVER_MODULE}` | project-manifest.json → devices[].driver.module | `sht30` |
| `{DRIVER_CLASS}` | project-manifest.json → devices[].driver.class | `SHT30` |

---

## 九、独立测试场景

### 插件端测试（无服务器）

1. 手动发 approval_request `debug_symptom_input` → 验证错误现象输入卡片交互
2. 手动发 phase_complete (debug_plan artifact) → 验证排查计划面板渲染
3. 手动发 approval_request `debug_user_measure` → 验证引导操作卡片（接线图/正常范围/选项）
4. 手动发 approval_request `debug_step_result` → 验证结果确认卡片
5. 模拟完整排查序列：device_command → device_result → approval_request 确认 → 下一步
6. 手动发 phase_complete (FAIL + diagnostic_bundle_path) → 验证诊断包导出卡片

### Skill 端测试（无插件）

1. 准备 error_lib.json（含 3 条测试条目），构造 start_phase(mode="auto", error_context=OSError_19)
2. 验证匹配打分：确认 err_sht30_i2c_19 得分最高
3. 验证参数填充：检查 debug_steps 中的 `{I2C_SDA}` 被替换为实际值
4. mock 用户对每个 approval_request 的应答，验证 on_pass/on_fail 跳转逻辑
5. 验证 PASS 路径：排查到 root_cause → 委托 generate → deploy → error_lib 更新
6. 验证 FAIL 路径：步骤耗尽 → 生成 diagnostic_bundle → phase_complete(failed)
7. 运行 validate_error_lib.py 确认 LLM 写入的条目结构合法
