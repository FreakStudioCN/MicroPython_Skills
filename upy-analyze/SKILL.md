---
name: upy-analyze-plugin
description: 插件化 V0 analyze 阶段。读取一句话硬件项目需求和插件上下文，完成需求解析、器件确认、驱动搜索、替代推荐或冷门驱动标记，并输出完整 envelope 的 phase_complete + manifest_content。触发：插件 start_phase(analyze)、用户描述“做一个/我想做/帮我写一个”MicroPython 硬件项目、需要生成 project manifest。
---

# upy-analyze

## 职责

把用户的一句话硬件需求转换为可交给 `upy-select-hw` 的 analyze manifest。

只做：

- 解析需求和实现族。
- 生成并确认器件清单。
- 搜索内置运行时能力和具体器件驱动。
- 标记替代推荐或冷门驱动路径。
- 输出 `phase_complete`，其中 `payload.manifest_content` 是下游唯一主交接物。

不做：

- 不选 MCU 和板卡。
- 不分配引脚。
- 不生成业务代码。
- 不烧录设备。
- 不把插件端 UI 或设备日志解析逻辑写进插件。

## 运行模式

## 协议字段说明

先按本文件执行流程。需要构造或排查具体消息字段时，读取 `references/v0-protocol.md`；它定义 envelope、`start_phase`、`approval_request`、`status_update`、`script_run`、manifest、`phase_complete`、checkpoint、structured errors 和 artifacts 的字段含义与枚举。

输出 JSON 时优先使用 `templates/*.json` 和 `mock-messages/analyze/*.json` 的形状，不要自由发挥字段名。

### 正式插件模式

插件通过 `start_phase` 启动：

```json
{
  "protocol_version": "1.0",
  "msg_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "4f6d9d72-9c4a-4f11-90df-3f2ad6e726cc",
  "phase": "analyze",
  "timestamp": "2026-06-21T00:00:00Z",
  "type": "start_phase",
  "payload": {
    "user_description": "做一个温湿度监测仪，超过阈值蜂鸣器报警",
    "pre_selected_board": null,
    "preferences": { "mode": "beginner", "locale": "zh" },
    "existing_hardware": []
  }
}
```

正式模式中：

- `session_id` 必须由插件创建并传入。
- skill/服务器必须继承同一个 `session_id`，不得另建正式 session。
- 所有 S->P 消息必须带完整 envelope。
- 本地文件、脚本、设备动作只能通过协议工具表达。

`start_phase` 字段速查：

| 字段 | 必填 | 来源 | 含义 |
|------|------|------|------|
| `protocol_version` | 是 | 插件 | 固定 `"1.0"` |
| `msg_id` | 是 | 插件 | 当前消息 UUID |
| `session_id` | 是 | 插件 | 当前工作流 session UUID，全流程保持不变 |
| `phase` | 是 | 插件 | 固定 `"analyze"` |
| `timestamp` | 是 | 插件 | ISO 8601 时间戳 |
| `type` | 是 | 插件 | 固定 `"start_phase"` |
| `payload.user_description` | 是 | 用户输入 | 一句话硬件需求 |
| `payload.pre_selected_board` | 否 | 插件 UI | 预选板卡；analyze 只记录，不核验 |
| `payload.preferences.mode` | 否 | 插件设置 | `beginner` 或 `custom`，默认 `beginner` |
| `payload.preferences.locale` | 否 | 插件设置 | 默认 `zh` |
| `payload.existing_hardware` | 否 | 用户资料 | 已有硬件数组，默认 `[]` |

### Claude Code 直测模式

没有真实插件宿主时，可以写调试产物，但这些文件不替代 `phase_complete.payload.manifest_content`。

如果输入缺少 `session_id`，直测模式必须生成 UUID，并强制使用 session 隔离目录：

```text
{test_root}/sessions/{session_id}/
  manifest_draft.json
  manifest_validated.json
  phase_complete.analyze.json
  driver_search_log.md
  analyze_phase_log.md
```

直测模式必须在结束前调用校验脚本：

```bash
python {skill_dir}/scripts/init_manifest.py --input {session_dir}/manifest_draft.json --write-path {session_dir}/manifest_validated.json
python {skill_dir}/scripts/init_manifest.py --validate-phase-complete --input {session_dir}/phase_complete.analyze.json --compare-manifest {session_dir}/manifest_validated.json
```

任一校验失败，不得宣称 analyze 成功。

## V0 协议硬规则

### 完整 envelope

所有正式协议消息必须包含：

```json
{
  "protocol_version": "1.0",
  "msg_id": "uuid",
  "session_id": "uuid",
  "phase": "analyze",
  "timestamp": "2026-06-21T00:00:00Z",
  "type": "phase_complete",
  "payload": {}
}
```

要求：

- `protocol_version` 固定为 `"1.0"`。
- `msg_id` 使用 UUID 字符串。
- `session_id` 使用 UUID 字符串。
- 顶层 `phase` 和 `payload.phase` 都保留，且必须一致。

envelope 字段速查：

| 字段 | 必填 | 谁生成 | 规则 |
|------|------|--------|------|
| `protocol_version` | 是 | 发送方 | 固定 `"1.0"` |
| `msg_id` | 是 | 发送方 | 每条消息一个新 UUID |
| `session_id` | 是 | 插件 | 同一工作流不变 |
| `phase` | 是 | 发送方 | analyze 阶段固定 `"analyze"` |
| `timestamp` | 是 | 发送方 | ISO 8601，UTC 优先 |
| `type` | 是 | 发送方 | 消息类型 |
| `payload` | 是 | 发送方 | 类型专属对象 |

### result 枚举

`phase_complete.payload.result` 只允许：

| result | 含义 | next_phase | checkpoint |
|--------|------|------------|------------|
| `success` | analyze 完整成功，可进入下游 | `select-hw` | 不需要 |
| `partial` | 用户取消、中断、超时、缺输入或只完成部分搜索 | `null` | 必须有 |
| `failed` | 无法产生可用 manifest，或协议/格式校验失败 | `null` | 可选 |

`partial` 必须包含：

```json
{
  "checkpoint_id": "uuid",
  "resume_phase": "analyze",
  "resume_step": "driver_search",
  "resume_label": "继续 analyze 驱动搜索",
  "reason": "user_cancelled"
}
```

V0 只定义 checkpoint/resume 结构，不实现完整 resume runtime。

### errors 与 structured_errors

保留 `errors: string[]` 给人类阅读，同时输出 `structured_errors: object[]` 给插件 UI 和 orchestration：

```json
{
  "code": "manifest_validation_failed",
  "message": "devices[0].driver.source invalid",
  "severity": "error",
  "recoverable": true,
  "retryable": true,
  "source": "init_manifest.py"
}
```

`severity` 只允许 `info / warning / error / fatal`。

### artifact 统一模型

`artifacts` 必须是数组。调试文件路径使用 `file_list` artifact，不得写成对象映射。

`artifact.files[].status` 只允许：

```text
created / updated / unchanged / skipped / error
```

推荐 file item：

```json
{
  "path": "manifest_validated.json",
  "status": "created",
  "kind": "manifest",
  "mime_type": "application/json",
  "description": "校验规范化后的 analyze manifest"
}
```

`artifact_id` 不强制。`kind` 和 `description` 推荐填写；缺失时校验脚本可给 warning。

## 权限策略

采用“首次 session 弹一次总权限，后续沿用”的长流程策略。

analyze 阶段授权后允许：

- 写项目分析产物。
- 运行白名单脚本 `scripts/init_manifest.py`。
- 访问驱动搜索源，如 upypi、awesome-micropython、GitHub。

仍需单独确认的高风险动作：

- 删除文件。
- 烧录设备。
- 执行任意 shell。
- 上传或发布到 upypi。

## 取消、重试、超时

V0 先写进协议和 skill 说明，不实现完整 runtime：

- 用户取消 approval：输出 `result="partial"`，`next_phase=null`，写 checkpoint。
- 驱动搜索超时：优先降级为 warning；核心信息不可判断时才 failed。
- manifest 校验失败：允许修正后重试；重试沿用同一个 `session_id`。
- 重试行为记录在日志或 payload 元数据中。

## 执行步骤

### Step 1: 读取输入上下文

读取 `start_phase.payload`：

| 字段 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `user_description` | 是 | 无 | 用户一句话需求 |
| `pre_selected_board` | 否 | `null` | 插件预选板卡，analyze 只记录，不核验 |
| `preferences.mode` | 否 | `beginner` | `beginner` 或 `custom` |
| `preferences.locale` | 否 | `zh` | 默认中文 |
| `existing_hardware` | 否 | `[]` | 用户已有硬件 |

如果字段缺失，按默认值补齐；如果 `user_description` 缺失或为空，输出 `phase_complete(result="failed")`，不得继续猜测需求。

发送：

```json
{
  "type": "status_update",
  "payload": {
    "level": "info",
    "message": "正在分析需求，先拆实现族和器件清单。",
    "step_id": "intent_extraction",
    "step_status": "running"
  }
}
```

### Step 2: 意图拆解和器件确认

从自然语言中提取：

- 项目名。
- 功能链路。
- 实现族。
- 器件清单。
- 接口类型。
- 用户指定器件 vs 系统推荐器件。

大类器件必须先拆实现族。例如土壤类必须区分 `ADC / RS485 Modbus / I2C/SPI / 组合方案`。

只保留一个必经确认点：`approval_request(device_confirm)`。

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "device_confirm",
    "header": "确认项目方案",
    "question": "请确认器件方案；像土壤类器件，可在这里改成 ADC / RS485 Modbus / I2C 方案。",
    "summary": {
      "project_name": "温湿度监测报警器",
      "description": "定时采集温湿度，超过阈值蜂鸣器报警",
      "board": { "status": "none" }
    },
    "items": [],
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

`approval_request` 发出后必须等待用户响应，不得继续假装已确认。

### Step 3: 补充需求

`beginner` 默认补齐 requirements。`custom` 或信息明显不足时，最多发一张 `approval_request(requirement_supplement)`。

默认值：

| 字段 | 默认 |
|------|------|
| `scene` | `indoor` |
| `power` | `usb` |
| `network` | `none` |
| `sample_rate` | `normal_1hz` |
| `precision` | `normal` |
| `response_time` | `1s` |
| `temp_range` | `normal_0_40` |
| `size_constraint` | `none` |
| `budget_yuan` | `medium_50` |
| `experience` | `beginner` |
| `output` | `["serial"]` |
| `existing_hardware` | `[]` |
| `special_requirements` | `["none"]` |
| `mcu_specified` | `null` |

语音、云端、音频输出等 schema 不能完整表达的内容，记录在 `description`、`special_requirements`、device notes 和 warnings 中，不因 output 枚举不足直接失败。

### Step 4: 驱动搜索

对每个确认后的器件，分两层判断：

1. 底层运行时能力：
   - `machine.ADC`
   - `machine.Pin`
   - `machine.I2C`
   - `machine.SPI`
   - `machine.UART`
   - `machine.I2S`
   - `network`
   - `bluetooth`

2. 具体器件驱动：
   - `upypi`
   - `awesome-micropython`
   - `github`
   - 其他可信 MicroPython 来源

注意：

- `builtin_runtime` 只表示底层 API 可用，不等于具体 I2C/SPI/UART 器件驱动已找到。
- I2C/SPI/UART 具体器件仍应优先查 `upypi`。
- `micropython_lib` 只用于官方生态通用库/中间件，不作为普通传感器驱动默认来源。
- `driver.source="none"` 只在不是明显内置运行时能力，且所有驱动源都无结果时使用。

每个器件搜索过程发送 `status_update`。

系统推荐器件无驱动时，可推荐最多 2 个同类替代器件，使用 `approval_request(alternative_device)`。用户指定器件无驱动，或用户拒绝替代时，标记 `driver.source="cold-driver"`，由后续 `upy-gen-driver` 处理。

### Step 5: 构建 manifest_draft

生成 manifest 草稿，必须包含：

- `project_name`
- `requirements`
- `devices`

每个 device 必须包含：

- `name`
- `type`
- `interface`
- `source`: `user_specified` 或 `system_recommended`
- `quantity`
- `driver.source`

有效 `driver.source`：

```text
builtin_runtime / micropython_lib / upypi / awesome-micropython / github / local / cold-driver / none
```

### Step 6: 强制校验 manifest

必须调用：

```bash
python {skill_dir}/scripts/init_manifest.py --input manifest_draft.json --write-path manifest_validated.json
```

校验失败：

- 修正草稿后可重试。
- 仍失败则输出 `phase_complete(result="failed")`。
- 不得继续输出 `success`。

### Step 7: 输出 phase_complete

成功时输出完整 envelope：

```json
{
  "protocol_version": "1.0",
  "msg_id": "550e8400-e29b-41d4-a716-446655440001",
  "session_id": "4f6d9d72-9c4a-4f11-90df-3f2ad6e726cc",
  "phase": "analyze",
  "timestamp": "2026-06-21T00:00:00Z",
  "type": "phase_complete",
  "payload": {
    "phase": "analyze",
    "result": "success",
    "summary": "器件分析完成，manifest 已通过校验。",
    "next_phase": "select-hw",
    "manifest_content": {},
    "artifacts": [
      {
        "type": "file_list",
        "title": "Claude Code 直测产物",
        "files": [
          {
            "path": "manifest_draft.json",
            "status": "created",
            "kind": "manifest_draft",
            "mime_type": "application/json",
            "description": "校验前 manifest 草稿"
          },
          {
            "path": "manifest_validated.json",
            "status": "created",
            "kind": "manifest",
            "mime_type": "application/json",
            "description": "校验规范化后的 analyze manifest"
          },
          {
            "path": "phase_complete.analyze.json",
            "status": "created",
            "kind": "phase_complete",
            "mime_type": "application/json",
            "description": "完整 analyze 阶段完成消息"
          },
          {
            "path": "driver_search_log.md",
            "status": "created",
            "kind": "log",
            "mime_type": "text/markdown",
            "description": "驱动搜索记录"
          }
        ]
      }
    ],
    "warnings": [],
    "errors": [],
    "structured_errors": []
  }
}
```

`phase_complete.payload` 字段速查：

| 字段 | 必填 | success | partial | failed |
|------|------|---------|---------|--------|
| `phase` | 是 | `"analyze"` | `"analyze"` | `"analyze"` |
| `result` | 是 | `"success"` | `"partial"` | `"failed"` |
| `summary` | 是 | 成功摘要 | 中断摘要 | 失败摘要 |
| `next_phase` | 是 | `"select-hw"` | `null` | `null` |
| `manifest_content` | 是 | 校验后的 manifest | 当前最佳 manifest 快照 | 尽量给出当前快照 |
| `checkpoint` | 条件 | 不需要 | 必须 | 可选 |
| `artifacts` | 是 | 数组 | 数组 | 数组 |
| `warnings` | 是 | 字符串数组 | 字符串数组 | 字符串数组 |
| `errors` | 是 | 空数组或错误摘要 | 空数组或错误摘要 | 错误摘要 |
| `structured_errors` | 是 | 空数组 | 可选结构化错误 | 必须描述主要失败 |

直测模式建议额外写 `analyze_phase_log.md`，但它不是正式协议必交产物；可以在 `file_list` 中声明。

写出 `phase_complete.analyze.json` 后必须调用：

```bash
python {skill_dir}/scripts/init_manifest.py --validate-phase-complete --input phase_complete.analyze.json --compare-manifest manifest_validated.json
```

校验失败不得宣称完成。

## 交付文件

正式插件模式以消息为准。Claude Code 直测模式在 session 目录下写：

- `manifest_draft.json`
- `manifest_validated.json`
- `phase_complete.analyze.json`
- `driver_search_log.md`
- `analyze_phase_log.md`（建议）

## 模板和 mock

使用本 skill 自带资源：

- `templates/envelope.phase_complete.json`
- `templates/checkpoint.json`
- `templates/structured_error.json`
- `templates/artifact.file_list.json`
- `mock-messages/analyze/*.json`
- `references/v0-protocol.md`

修改模板、枚举或输出格式后，必须更新校验脚本和 smoke 测试。

## 强约束

- 协议格式、必填字段、枚举非法、manifest 核心结构错误必须作为 error。
- 业务语义问题优先 warning，例如 TouchPad 板卡兼容性、语音 output schema 不完整。
- `phase_complete.payload.manifest_content` 是下游唯一主交接物。
- `manifest_validated.json` 与 `phase_complete.payload.manifest_content` 必须核心字段一致，时间字段不参与严格比较。
- `phase_complete.artifacts` 必须是数组。
- `errors` 必须是字符串数组，`structured_errors` 必须是对象数组。
- `partial` 必须 `next_phase=null` 且有 checkpoint。
- `success` 必须 `next_phase="select-hw"` 且有合法 `manifest_content`。

