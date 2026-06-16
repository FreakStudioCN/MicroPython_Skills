# 通信协议

## 协议基础

- 传输：HTTP POST（插件→服务器）、SSE（服务器→插件）
- 格式：JSON
- 编码：UTF-8
- 消息方向：`S→P` = 服务器发给插件，`P→S` = 插件发给服务器

所有消息共享一个外层信封。`type` 字段决定消息类别，`phase` 字段标识当前 pipeline 阶段。

## 消息信封

```json
{
  "msg_id": "uuid",
  "session_id": "uuid",
  "phase": "analyze",
  "timestamp": "2026-06-16T10:30:00Z",
  "type": "approval_request",
  "payload": { ... }
}
```

| 字段 | 类型 | 方向 | 说明 |
|------|------|------|------|
| `msg_id` | string | 双向 | 消息唯一 ID，用于关联请求/响应 |
| `session_id` | string | 双向 | 项目会话 ID，插件首次发送时生成 |
| `phase` | string | 双向 | 当前 pipeline 阶段（analyze/select-hw/scaffold/generate/simulate/deploy/autofix/wiring/diagram/cold-driver） |
| `timestamp` | string | 双向 | ISO 8601 时间戳 |
| `type` | string | 双向 | 消息类型，见下表 |
| `payload` | object | 双向 | 消息载荷，结构由 type 决定 |

---

## 一、S→P 消息（服务器发给插件，共 7 种）

### 1. approval_request — 需要用户审批

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "device_confirm_001",
    "header": "确认项目方案",
    "question": "以下器件是否正确？",
    "summary": {
      "project_name": "温湿度监测报警器",
      "board": { "display_name": "ESP32 DevKit V1", "mcu": "ESP32-WROOM-32" }
    },
    "items": [
      {
        "id": "d1",
        "name": "SHT30",
        "subtitle": "I2C 温湿度传感器",
        "meta": "用户指定",
        "selectable": true,
        "selected": true
      },
      {
        "id": "d2",
        "name": "SSD1306 OLED",
        "subtitle": "I2C 显示屏 (0x3C)",
        "meta": "系统推荐",
        "selectable": true,
        "selected": true
      }
    ],
    "allow_add": true,
    "allow_remove": true,
    "actions": [
      { "label": "确认，开始搜索驱动", "value": "confirm", "primary": true },
      { "label": "修改器件清单", "value": "modify" }
    ],
    "multi_select": true
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `approval_id` | string | 审批 ID，响应时原样返回 |
| `header` | string | 卡片标题 |
| `question` | string | 主问题 |
| `summary` | object | 可选，顶部摘要区。可含 `project_name`、`board`、`description` |
| `items` | array | 可选，选项列表。每项含 `id`/`name`/`subtitle`/`meta`/`selectable`/`selected` |
| `allow_add` | boolean | 是否允许用户添加新项 |
| `allow_remove` | boolean | 是否允许用户删除项 |
| `actions` | array | 操作按钮。`label`=显示文字，`value`=回传值，`primary`=高亮 |
| `multi_select` | boolean | 是否多选 |
| `item_groups` | array | 可选，分组单选/多选。每组含 `group_id`/`group_header`/`multi_select`/`items`，items 结构同顶层 items |
| `file_upload` | object | 可选，启用文件上传。子字段：`enabled`(bool)、`accept`(string[]）、`max_files`(int)、`max_size_mb`(int)、`generate_thumbnails`(bool)、`thumbnail_size`([int,int])、`preprocess`(object，扩展名→预处理脚本) |
| `text_inputs` | array | 可选，文本输入框。每项含 `id`/`label`/`placeholder`/`type`（"text"\|"url"\|"number"） |
| `guidance` | object | 可选，调试指导。含 `tool`(所需工具名)、`steps`(string[]）、`normal_range`(正常范围)、`diagram_ref`(参考图) |

### 2. status_update — 进度更新

```json
{
  "type": "status_update",
  "payload": {
    "level": "info",
    "message": "正在搜索 SSD1306 驱动...",
    "progress": 0.25,
    "progress_label": "1/4",
    "step_id": "search_drivers",
    "step_status": "running",
    "detail": "已搜索 upypi，找到 1 个匹配包"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `level` | string | `info` / `warn` / `error` / `success` |
| `message` | string | 必填，简短描述 |
| `progress` | number | 可选，0.0~1.0 |
| `progress_label` | string | 可选，进度文字如 "2/5" |
| `step_id` | string | 可选，步骤标识，同一步骤的多次更新共享 |
| `step_status` | string | 可选，`pending` / `running` / `done` / `failed` |
| `detail` | string | 可选，补充说明 |

插件渲染为时间线列表：已完成(✓) / 进行中(旋转) / 失败(✗)+详情。

### 3. device_command — 透传 mpremote

```json
{
  "type": "device_command",
  "payload": {
    "cmd_id": "dc_042",
    "action": "exec",
    "code": "import machine; i2c=machine.I2C(0); print(i2c.scan())",
    "timeout_ms": 5000,
    "expect_output": true
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `cmd_id` | string | 命令 ID，响应时原样返回 |
| `action` | string | `devs`(列出可用串口) / `scan`(扫描 I2C 等总线) / `exec`(执行代码) / `cp`(上传文件) / `cp_from`(下载文件) / `mkdir`(创建目录) / `ls`(列出文件) / `rm`(删除文件) / `soft_reset`(软复位) / `stream`(持久会话) / `run`(送入 REPL 执行 .py 文件) |
| `code` | string | action=exec 时必填，要执行的 Python 代码 |
| `src` | string | action=cp 时必填，本地源路径（相对于项目目录） |
| `dst` | string | action=cp/mkdir/rm/ls 时必填，远端路径 |
| `timeout_ms` | number | 超时毫秒，默认 30000 |
| `expect_output` | boolean | 是否等待输出，默认 true |

### 4. file_operation — 文件读写

```json
{
  "type": "file_operation",
  "payload": {
    "op_id": "fo_015",
    "op": "write",
    "path": "firmware/tasks/sensor_task.py",
    "content": "# MicroPython sensor task\n...",
    "encoding": "utf-8"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `op_id` | string | 操作 ID |
| `op` | string | `write`(覆盖写入，自动创建父目录) / `read` / `list` / `delete` / `mkdir`(确保目录存在) / `append`(追加写入) |
| `path` | string | 相对于项目目录的文件路径 |
| `content` | string | op=write 时必填，文件内容 |
| `encoding` | string | 编码，默认 utf-8 |

### 5. script_run — 执行本地脚本

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "sr_008",
    "interpreter": "python",
    "script": "flake8",
    "args": ["--max-line-length=100", "firmware/tasks/"],
    "cwd": "{project_dir}",
    "timeout_ms": 30000
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `script_id` | string | 脚本 ID |
| `interpreter` | string | `python` / `node` / `shell` |
| `script` | string | 脚本名或命令 |
| `args` | string[] | 命令行参数 |
| `cwd` | string | 工作目录。`{project_dir}` = 项目根目录；`{skill_dir}` = skill 脚本所在目录。default = `{project_dir}` |
| `timeout_ms` | number | 超时毫秒 |

### 6. phase_complete — 阶段完成

```json
{
  "type": "phase_complete",
  "payload": {
    "result": "success",
    "summary": "器件分析完成，3 个器件中找到 2 个驱动",
    "next_phase": "select-hw",
    "artifacts": [
      {
        "type": "table",
        "title": "器件清单",
        "headers": ["器件", "类型", "接口", "驱动来源", "状态"],
        "rows": [
          ["SSD1306", "OLED", "I2C", "upypi", "✓"],
          ["SHT30", "温湿度", "I2C", "none", "⚠ 冷硬件路径"]
        ]
      },
      {
        "type": "file_tree",
        "title": "项目结构",
        "tree": { "firmware": { "main.py": "file", "tasks": { "sensor.py": "file" } } }
      }
    ],
    "warnings": ["SHT30 驱动未找到，将走冷硬件路径"],
    "errors": []
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `result` | string | `success` / `failed` / `partial` |
| `summary` | string | 必填，人类可读的摘要 |
| `next_phase` | string | 可选，下一阶段名称。插件收到后自动触发对应 skill 的 `start_phase`，`manifest` 取自本消息的 `manifest_content` |
| `manifest_content` | object | 可选，当前 manifest 完整快照。下游 skill 的 `start_phase.payload.manifest` 从此字段自动填充 |
| `artifacts` | array | 产物列表，类型见下表 |
| `warnings` | string[] | 警告信息 |
| `errors` | string[] | 错误信息 |

**artifact 类型：**

| type | 渲染方式 | 额外字段 |
|------|---------|---------|
| `table` | 表格 | `headers` + `rows` |
| `file_tree` | 树形目录 | `tree` (嵌套对象) |
| `markdown` | Markdown 渲染 | `content` |
| `html` | iframe 预览 | `content` / `url` |
| `code_diff` | diff 视图 | `file_path` + `changes[{line_start, line_end, old_text, new_text}]` |
| `file_list` | 文件列表 | `files: [{path, size, status}]` |

### 7. stream — 实时数据流

```json
{
  "type": "stream",
  "payload": {
    "stream_id": "device_repl_001",
    "stream_type": "device_output",
    "chunk": "[0.5s] I2C scan result: [48, 60]\n",
    "chunk_index": 12,
    "done": false
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `stream_id` | string | 流 ID |
| `stream_type` | string | `device_output` / `script_stdout` / `script_stderr` |
| `chunk` | string | 数据块 |
| `chunk_index` | number | 序号（从 0 开始） |
| `done` | boolean | 是否结束 |

---

## 二、P→S 消息（插件发给服务器）

共 7 种：5 种基础消息 + 2 种 autofix 专用消息。

### 0. start_phase — 启动 skill

```json
{
  "type": "start_phase",
  "phase": "analyze",
  "payload": {
    "manifest": { },
    "source": null
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `phase` | string | 目标 skill 名称（analyze / select-hw / scaffold / generate / simulate / deploy / autofix / wiring / diagram / gen-driver / publish） |
| `payload` | object | 各 skill 定义的输入数据。公共字段：`manifest`（上游传递的项目清单）、`session_id`（续接会话时携带）。其余字段由各 skill 接口文档定义 |

`start_phase` 是插件→服务器的第一条消息，触发服务器加载对应 SKILL.md 并开始执行。`manifest` 由上游 skill 的 `phase_complete.manifest_content` 传递；`session_id` 用于续接之前中断的会话（如 gen-driver "稍后继续"）。

### 1. approval_response

```json
{
  "type": "approval_response",
  "payload": {
    "approval_id": "device_confirm_001",
    "action": "confirm",
    "selected_ids": ["d1", "d2"],
    "added_items": [],
    "notes": ""
  }
}
```

### 2. device_result

```json
{
  "type": "device_result",
  "payload": {
    "cmd_id": "dc_042",
    "success": true,
    "stdout": "[48, 60]\n",
    "stderr": "",
    "exit_code": 0
  }
}
```

### 3. script_result

```json
{
  "type": "script_result",
  "payload": {
    "script_id": "sr_008",
    "success": false,
    "stdout": "firmware/tasks/sensor.py:15:1: E302 expected 2 blank lines\n",
    "stderr": "",
    "exit_code": 1
  }
}
```

### 4. file_result

```json
{
  "type": "file_result",
  "payload": {
    "op_id": "fo_015",
    "success": true,
    "error": null
  }
}
```

### 5. user_intervention — 排查中途用户干预（autofix 专用）

```json
{
  "type": "user_intervention",
  "payload": {
    "approval_id": "debug_step_result_003",
    "action": "pause",
    "notes": "先量一下 SDA/SCL 电压再继续"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `approval_id` | string | 对应的审批卡片 ID |
| `action` | string | `pause`（暂停排查）/ `skip`（跳过当前步骤）/ `abort`（终止排查，生成诊断包）/ `resume`（继续） |
| `notes` | string | 用户备注，可选 |

### 6. error_lib_update — 错误库增删改查（autofix 专用）

```json
{
  "type": "error_lib_update",
  "payload": {
    "action": "add",
    "entry": {
      "error_signature": "I2C readback mismatch 0xFF",
      "primary_error": "communication",
      "device_type": "I2C",
      "root_cause": "SDA stuck LOW, check pull-up",
      "fix_strategy": "Verify 4.7kΩ pull-up on SDA/SCL to 3.3V"
    }
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | string | `add` / `update` / `delete` / `query` |
| `entry` | object | error_lib.json 条目。`add` 时必填；`update` 时提供要改的字段；`delete` 时只需 `error_signature`；`query` 时提供匹配条件 |

### 7. stream_ack — 流数据确认/终止

```json
{
  "type": "stream_ack",
  "payload": {
    "stream_id": "device_repl_001",
    "action": "stop",
    "chunk_index": 42,
    "reason": "marker_detected"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `stream_id` | string | 对应的 stream ID |
| `action` | string | `continue`（继续接收）/ `stop`（终止流） |
| `chunk_index` | number | 已收到的最后一个 chunk 序号 |
| `reason` | string | 终止原因。`marker_detected`（检测到预期标记）/ `timeout`（超时）/ `user_request`（手动停止） |

插件在 stream 会话中检测到预期标记（如 "starting scheduler"）时，通过 `stream_ack(action=stop, reason=marker_detected)` 提前终止，并将已捕获的输出包装为 `device_result` 返回服务器。

---

## 三、错误处理

服务器在任意阶段可发送 `phase_complete` 且 `result: "failed"`，携带 `errors` 数组说明原因。插件收到后停止当前阶段的时间线动画，展示错误面板。

插件在执行 device_command / script_run / file_operation 失败时，通过对应的 result 消息携带 `success: false` + `error` 字段，服务器 LLM 决定下一步（重试/跳过/降级）。

### 会话恢复

插件可在 `start_phase` 中携带 `session_id` 续接之前中断的会话（如 gen-driver 的"稍后继续"场景）。服务器收到已存在的 `session_id` 后，恢复上次上下文并从断点继续。

### phase 自动转换

`phase_complete.next_phase` 非空时，插件自动发送 `start_phase` 到对应 phase，`payload.manifest` 来自 `phase_complete.manifest_content`。next_phase 为 null 时停止 pipeline。
