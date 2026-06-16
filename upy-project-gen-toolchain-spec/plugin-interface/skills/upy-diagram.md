# upy-diagram 接口定义

> 状态：✅ 已定稿
>
> Phase 7b — 软件架构图生成。通读 firmware/ 全部 .py + manifest，LLM 分析代码结构/执行流程/数据流向，生成 diagram.json，脚本渲染 3 种 Mermaid 图（架构图 + 流程图 + 数据流图）× 4 种格式（.md + .svg + .png + .html）。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | diagram |
| 上游 Skill | upy-generate（手动/自动触发） |
| 下游 Skill | 无 |
| 一句话职责 | 读代码 → LLM 分析分层架构/执行流程/数据流 → 生成 diagram.json → 校验 → 渲染 3 种 Mermaid 图 × 4 格式 = 13 个文件 |

**与 upy-wiring 模式相同，差异：**
- 有用户交互（复杂度选择）
- 输出 3 种图（架构图 graph TB + 流程图 sequenceDiagram + 数据流图 graph LR）
- 输出 13 个文件（vs wiring 的 6 个）

---

## 二、插件输入 → Skill（P→S）

```json
{
  "type": "start_phase",
  "phase": "diagram",
  "session_id": "uuid-xxx",
  "payload": {
    "manifest": { /* 完整的 project-manifest.json */ },
    "complexity": null
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `manifest` | object | 是 | 完整 manifest |
| `complexity` | string? | 否 | `"simple"` / `"medium"` / `"full"`。null → 触发 approval_request 询问。有值（来自用户偏好设置）→ 跳过 |

**复杂度档位约束：**

| 参数 | simple | medium（默认） | full |
|------|:------:|:------------:|:----:|
| 总模块数 | ≤6 | ≤10 | ≤16 |
| 每层模块数 | ≤2 | ≤4 | ≤6 |
| 跨层依赖边 | ≤6 | ≤12 | ≤20 |
| flow 总步数 | ≤5 | ≤8 | ≤14 |
| data_flow 总边数 | ≤2 | ≤4 | ≤8 |

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
(可选) Step 0: 复杂度选择
  → approval_request: 复杂度选择卡片 (diagram_complexity)
  → (complexity 已预设时跳过)

Step 1-2: 读取源码
  → file_operation(read) × N (firmware/ 所有 .py)
  → status_update "✓ 已读取 N 个文件"

Step 3: 分析 + 生成 diagram.json
  → status_update "正在分析代码结构..."
  → status_update "架构: 5 层 / N 模块 / K 条依赖"
  → status_update "流程: M 步骤 (boot→init→scan→create→assembly→run)"
  → status_update "数据流: P 条通道"
  → file_operation(write) → docs/diagram.json
  → status_update "✓ diagram.json 已生成"

Step 4: 校验
  → script_run(validate_json.py --schema .upy/schemas/diagram.schema.json --json docs/diagram.json)
  → (校验失败 → LLM 修复 → file_operation(write) → 重新 script_run，循环至 pass)

Step 5: 渲染
  → status_update "正在渲染架构图 (mermaid.ink)..."
  → status_update "正在渲染流程图..."
  → status_update "正在渲染数据流图..."
  → script_run(render_diagram_local.py --input docs/diagram.json --output docs/ --format all)
  → status_update "✓ 已生成 13 个文件"

Step 6: 更新 manifest
  → file_operation(read) → project-manifest.json
  → (服务端修改 diagrams 字段)
  → file_operation(write) → project-manifest.json

输出
  → phase_complete(file_list + diagnostics table)
```

### approval_request — 复杂度选择（diagram_complexity）

条件触发：`complexity` 为 null 时展示。

```
┌──────────────────────────────────────────┐
│  架构图复杂度                              │
│                                          │
│  选择架构图的详细程度：                      │
│                                          │
│  ○ 简单                                   │
│    高度精简，≤6 模块，≤5 步骤               │
│    适合快速浏览                             │
│                                          │
│  ● 中等 (推荐)                             │
│    平衡信息量，≤10 模块，≤8 步骤             │
│    适合日常开发和沟通                        │
│                                          │
│  ○ 详细                                   │
│    完整展开，≤16 模块，≤14 步骤              │
│    适合复杂项目或归档文档                    │
│                                          │
│  [确认]                                   │
└──────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "diagram_complexity",
    "header": "架构图复杂度",
    "question": "选择架构图的详细程度",
    "summary": {},
    "items": [
      {
        "id": "simple",
        "name": "简单",
        "subtitle": "≤6 模块，≤5 步骤，高度精简",
        "meta": "适合快速浏览",
        "selected": false
      },
      {
        "id": "medium",
        "name": "中等 (推荐)",
        "subtitle": "≤10 模块，≤8 步骤，平衡信息量",
        "meta": "适合日常开发",
        "selected": true
      },
      {
        "id": "full",
        "name": "详细",
        "subtitle": "≤16 模块，≤14 步骤，完整展开",
        "meta": "适合归档文档",
        "selected": false
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "确认", "value": "confirm", "primary": true }
    ]
  }
}
```

### status_update 列表

| step_id | level | message | 触发时机 |
|---------|-------|---------|---------|
| read_src | info | 正在读取 firmware/ 源码... | Step 2 开始 |
| read_done | success | ✓ 已读取 N 个文件 | Step 2 完成 |
| analyze | info | 正在分析代码结构... | Step 3 开始 |
| arch_summary | success | 架构: 5 层 / N 模块 / K 条跨层依赖 | 架构分析完成 |
| flow_summary | success | 流程: M 步骤 (boot→init→...→run) | 流程分析完成 |
| dataflow_summary | success | 数据流: P 条通道 | 数据流分析完成 |
| gen_json | info | 正在生成 diagram.json... | 写入 JSON |
| gen_done | success | ✓ diagram.json 已生成 | Step 3 完成 |
| validate | info | 正在校验 diagram.json... | Step 4 |
| validate_pass | success | ✓ 校验通过 | 通过 |
| validate_fail | warn | ✗ N errors → 修复中 (第 M 轮) | 失败 |
| render_arch | info | 正在渲染架构图 (mermaid.ink)... | 架构图渲染 |
| render_flow | info | 正在渲染流程图... | 流程图渲染 |
| render_data | info | 正在渲染数据流图... | 数据流图渲染 |
| render_done | success | ✓ 已生成 13 个文件 | Step 5 完成 |
| update_manifest | info | 正在更新 manifest... | Step 6 |
| done | success | ✓ 架构图生成完成 | 全部完成 |

### script_run — render_diagram_local.py（Step 5）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "diagram_render",
    "interpreter": "python",
    "script": ".upy/scripts/render_diagram_local.py",
    "args": ["--input", "docs/diagram.json", "--output", "docs/", "--format", "all"],
    "cwd": "{project_dir}",
    "timeout_ms": 90000
  }
}
```

**timeout 90s** — 渲染 3 种图 × 3 种格式（.md 本地生成，.svg/.png 调 mermaid.ink API 各需 1 次 HTTP 请求），共 6 次网络请求。

### phase_complete

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "diagram",
    "result": "success",
    "summary": "架构图生成完成：5 层 / 8 模块 / 12 条依赖 / 6 步流程 / 3 条数据流 (中等复杂度)",
    "next_phase": null,
    "artifacts": [
      {
        "type": "file_list",
        "title": "生成文件 (13)",
        "files": [
          { "path": "docs/diagram.json", "size": 8192, "status": "new", "description": "架构中间 JSON" },
          { "path": "docs/architecture.md", "size": 3072, "status": "new", "description": "分层架构图 Mermaid" },
          { "path": "docs/architecture.svg", "size": 45056, "status": "new", "description": "分层架构图 SVG" },
          { "path": "docs/architecture.png", "size": 87040, "status": "new", "description": "分层架构图 PNG" },
          { "path": "docs/architecture.html", "size": 10240, "status": "new", "description": "分层架构图 HTML" },
          { "path": "docs/flowchart.md", "size": 2048, "status": "new", "description": "执行流程图 Mermaid" },
          { "path": "docs/flowchart.svg", "size": 32768, "status": "new", "description": "执行流程图 SVG" },
          { "path": "docs/flowchart.png", "size": 56320, "status": "new", "description": "执行流程图 PNG" },
          { "path": "docs/flowchart.html", "size": 9216, "status": "new", "description": "执行流程图 HTML" },
          { "path": "docs/data_flow.md", "size": 1536, "status": "new", "description": "数据流图 Mermaid" },
          { "path": "docs/data_flow.svg", "size": 24576, "status": "new", "description": "数据流图 SVG" },
          { "path": "docs/data_flow.png", "size": 39936, "status": "new", "description": "数据流图 PNG" },
          { "path": "docs/data_flow.html", "size": 7168, "status": "new", "description": "数据流图 HTML" }
        ]
      },
      {
        "type": "table",
        "title": "诊断信息",
        "headers": ["指标", "值"],
        "rows": [
          ["总模块数", "8"],
          ["总依赖边", "12"],
          ["最大深度", "4 层"],
          ["循环依赖", "无"],
          ["孤立模块", "无"],
          ["直接 import machine", "main.py (仅入口层，正常)"]
        ]
      }
    ],
    "warnings": [],
    "errors": []
  }
}
```

---

## 四、SKILL.md 修改点

共 6 处改动：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 前置检查 | `python --version` + `python -c "import jsonschema"` | 删除 | 服务端不感知环境 |
| 2 | Step 0 复杂度 | `AskUserQuestion(...)` | `approval_request` 复杂度选择卡片。`complexity` 已在 start_phase 中预设时跳过 | 插件端交互 |
| 3 | Step 1 读 schema | LLM Read `diagram.schema.json` | schema 由 scaffold 预置到 `.upy/schemas/`。服务端 LLM 内置 schema 知识直接生成 JSON | spec 不在项目目录 |
| 4 | Step 2 读源码 | LLM 直接 Read firmware/**/*.py + manifest | `file_operation(read)` 逐文件读取。manifest 已在 start_phase.payload 中 | 服务器通过插件读文件 |
| 5 | Step 4 校验 | `validate_json.py --schema <spec路径> --json ...` | `script_run(validate_json.py --schema .upy/schemas/diagram.schema.json --json docs/diagram.json)` | schema+脚本由 scaffold 预置到 `.upy/` |
| 6 | Step 5+6 渲染 | `render_diagram_local.py --input ... --output ...` | `script_run(render_diagram_local.py --input docs/diagram.json --output docs/ --format all)`。脚本由 scaffold 预置 | 需网络(mermaid.ink) + 写文件 → 插件执行 |
| 7 | Step 7 更新 manifest | `python -c "..."` inline 脚本 | `file_operation(read)` → 服务端修改 diagrams 字段 → `file_operation(write)` | 统一文件操作 |

---

## 五、校验脚本

### validate_json.py

与 wiring 共用，**无需改**。已是通用 JSON Schema 校验器。

### render_diagram_local.py

**路径：** `G:\MicroPython_Skills\upy-diagram\scripts\render_diagram_local.py`

| 改动 | 内容 |
|------|------|
| 新增 `--json-summary` | 渲染完成时输出一行 JSON：`{"status":"ok","files":[{"path":"docs/architecture.md","size":3072},...],"errors":[]}` |

**其余无需改。** 防御式读取已在 wiring 脚本中验证过。

### 对 upy-scaffold 的影响

| 源文件 | 目标位置 | 说明 |
|--------|---------|------|
| `diagram.schema.json` | `{project}/.upy/schemas/diagram.schema.json` | 校验 diagram.json |
| `render_diagram_local.py` | `{project}/.upy/scripts/render_diagram_local.py` | 渲染 3 种图 |

**与 wiring 共用 validate_json.py，无需重复拷贝。**

---

## 六、插件端 UI 组件

| 组件 | 对应消息 | 说明 |
|------|---------|------|
| 复杂度选择卡片 | approval_request `diagram_complexity` | 简单/中等/详细 三选一，仅 complexity 为空时弹出 |
| 进度时间线 | status_update × ~12 | 读取→分析(架构/流程/数据流)→生成→校验→渲染×3 |
| 架构图预览 | file_list → 点击 architecture.html | WebView 内嵌预览 |
| 流程图预览 | file_list → 点击 flowchart.html | WebView 内嵌预览 |
| 数据流图预览 | file_list → 点击 data_flow.html | WebView 内嵌预览 |
| 诊断信息面板 | phase_complete table artifact | 总模块/依赖/深度/循环依赖/孤立模块 |
| [生成架构图] 按钮 | 触发 start_phase | generate 完成后启用 |

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发 approval_request `diagram_complexity` → 验证三选一 + 确认
2. 手动发 `status_update` 序列 → 验证三阶段（架构/流程/数据流）进度
3. 手动发 `phase_complete` (file_list 13 文件 + diagnostics table) → 验证文件列表 + 诊断信息面板
4. 点击 architecture.html / flowchart.html / data_flow.html → 验证 WebView 预览

### Skill 端测试（无插件）

1. 准备完整 firmware/ 目录 + manifest，mock file_operation(read) 返回文件内容
2. 验证 complexity="simple": 总模块数 ≤6、flow 步数 ≤5
3. 验证 complexity="medium": 总模块数 ≤10、flow 步数 ≤8
4. 验证 complexity="full": 总模块数 ≤16、flow 步数 ≤14
5. LLM 生成 diagram.json → validate_json.py 校验通过
6. render_diagram_local.py → 确认 13 个输出文件 + --json-summary 输出正确
7. 检查所有发出的消息 JSON 符合 02-protocol.md Schema
