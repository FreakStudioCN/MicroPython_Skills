# upy-wiring 接口定义

> 状态：✅ 已定稿
>
> Phase 7a — 接线图生成。通读 firmware/ 全部 .py 源码提取实际引脚/总线/地址，与 manifest 交叉验证，LLM 生成 wiring.json，脚本渲染 Mermaid .md + SVG + PNG + HTML。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | wiring |
| 上游 Skill | upy-scaffold 或 upy-generate（手动/自动触发） |
| 下游 Skill | upy-diagram（并行，可同时生成） |
| 一句话职责 | firmware 源码为权威数据源 → LLM 提取硬件连接事实 → 生成 wiring.json → 校验 → 渲染 Mermaid 接线图 + SVG + PNG + HTML + 引脚交叉引用表 |

**核心约束：**
- firmware > manifest > LLM 推断（数据优先级）
- LLM 生成 JSON，脚本只做校验+渲染
- schema 是唯一契约：wiring.json 必须通过 validate_json.py 校验
- SVG + PNG + HTML 为必需输出

---

## 二、插件输入 → Skill（P→S）

```json
{
  "type": "start_phase",
  "phase": "wiring",
  "session_id": "uuid-xxx",
  "payload": {
    "manifest": { /* 完整的 project-manifest.json */ },
    "complexity": "full"
  }
}
```

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `manifest` | object | 是 | upy-generate 输出 | 完整 manifest，含 mcu/devices/pinout/bom |
| `complexity` | string | 否 | 插件设置 | `"simple"` — 仅 .md；`"full"` — .md + .svg + .png + .html + _pins.md。默认 `"full"` |

**注意：** manifest 已在 start_phase 中传入，LLM 无需再 file_operation(read) manifest。但 firmware/ 源文件**不在** payload 中，需通过 file_operation(read) 逐文件读取。

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
Step 1-3: 读取源码 + 提取硬件事实
  → status_update "正在读取 firmware/ 源码..."
  → file_operation(read) × N (firmware/ 下所有 .py 文件)
  → status_update "✓ 已读取 N 个文件，提取 X 个引脚，Y 条总线，Z 个告警"

Step 4: 生成 wiring.json
  → status_update "正在生成接线图中间 JSON..."
  → file_operation(write) → docs/wiring.json
  → status_update "✓ wiring.json 已生成"

Step 5: 校验
  → script_run(validate_json.py --schema .upy/schemas/wiring.schema.json --json docs/wiring.json)
  → script_result
  → (校验失败 → LLM 修复 wiring.json → file_operation(write) → 重新校验，循环至 pass)

Step 6: 渲染
  → status_update "正在渲染接线图 (mermaid.ink)..."
  → script_run(render_wiring_local.py --input docs/wiring.json --output docs/ --format all)
  → status_update "✓ 已生成 wiring.md + .svg + .png + .html + _pins.md"

Step 7: 更新 manifest
  → file_operation(read) → project-manifest.json
  → (服务端修改 wiring 字段)
  → file_operation(write) → project-manifest.json

输出
  → phase_complete(file_list)
```

### status_update 列表

| step_id | level | message | 触发时机 |
|---------|-------|---------|---------|
| read_src | info | 正在读取 firmware/ 源码... | Step 2 开始 |
| read_file | info | 读取: firmware/tasks/sensor_task.py (N/M) | 每文件 |
| read_done | success | ✓ 已读取 N 个文件，提取 X 个引脚，Y 条总线，Z 个告警 | Step 2+3 完成 |
| gen_json | info | 正在生成接线图中间 JSON... | Step 4 |
| gen_done | success | ✓ wiring.json 已生成 | Step 4 完成 |
| validate | info | 正在校验 wiring.json... | Step 5 |
| validate_pass | success | ✓ wiring.json 校验通过 | 校验通过 |
| validate_fail | warn | ✗ wiring.json: N errors → 修复中 (第 M 轮) | 校验失败，进入修复循环 |
| render | info | 正在渲染接线图 (mermaid.ink API)... | Step 6 |
| render_svg | info | 正在渲染 SVG... | render_wiring_local 子步骤 |
| render_png | info | 正在渲染 PNG... | render_wiring_local 子步骤 |
| render_done | success | ✓ 已生成 5 个文件 | Step 6 完成 |
| update_manifest | info | 正在更新 manifest... | Step 7 |
| done | success | ✓ 接线图生成完成 | 全部完成 |

### script_run — validate_json.py（Step 5）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "wiring_validate",
    "interpreter": "python",
    "script": ".upy/scripts/validate_json.py",
    "args": ["--schema", ".upy/schemas/wiring.schema.json", "--json", "docs/wiring.json"],
    "cwd": "{project_dir}",
    "timeout_ms": 15000
  }
}
```

**说明：** `validate_json.py` 和 `wiring.schema.json` 均由 upy-scaffold 拷贝到项目 `.upy/` 目录下，插件本地可访问。

### script_run — render_wiring_local.py（Step 6）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "wiring_render",
    "interpreter": "python",
    "script": ".upy/scripts/render_wiring_local.py",
    "args": ["--input", "docs/wiring.json", "--output", "docs/", "--format", "all"],
    "cwd": "{project_dir}",
    "timeout_ms": 60000
  }
}
```

**说明：** 渲染脚本需要网络（mermaid.ink API）生成 SVG/PNG，必须在插件端执行。timeout 60s 覆盖网络延迟。

### phase_complete

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "wiring",
    "result": "success",
    "summary": "接线图生成完成：2 条总线 (I2C×1, GPIO×3)，12 个引脚，3 个告警",
    "next_phase": "diagram",
    "artifacts": [
      {
        "type": "file_list",
        "title": "生成文件",
        "files": [
          { "path": "docs/wiring.json", "size": 4096, "status": "new", "description": "接线中间 JSON" },
          { "path": "docs/wiring.md", "size": 2048, "status": "new", "description": "Mermaid 接线示意图" },
          { "path": "docs/wiring.svg", "size": 32768, "status": "new", "description": "SVG 矢量接线图" },
          { "path": "docs/wiring.png", "size": 65536, "status": "new", "description": "PNG 接线图" },
          { "path": "docs/wiring.html", "size": 8192, "status": "new", "description": "自包含 HTML（浏览器查看）" },
          { "path": "docs/wiring_pins.md", "size": 1024, "status": "new", "description": "引脚交叉引用表" }
        ]
      }
    ],
    "warnings": [
      "检测到 I2C 无上拉电阻声明：请确认 SDA/SCL 已接 4.7kΩ 上拉到 3.3V"
    ],
    "errors": []
  }
}
```

**warnings 示例（LLM 按规则自动生成）：**

| 条件 | level | 示例 msg |
|------|-------|---------|
| I2C 地址冲突 | `danger` | "SHT30 and BMP280 both at 0x76 — address conflict" |
| 无上拉电阻声明 | `warning` | "Verify I2C pull-up resistors on SDA/SCL (4.7kΩ to 3.3V)" |
| 5V 器件接 3.3V | `danger` | "LCD1602: 5V device on 3.3V pin — level shifter needed" |
| 蜂鸣器无限流电阻 | `info` | "Add 220Ω resistor in series with buzzer" |
| firmware 与 manifest 不一致 | `danger` | "SHT30: firmware uses 0x44, manifest says 0x45" |

---

## 四、SKILL.md 修改点

共 6 处改动：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 前置检查 | `python --version` + `python -c "import jsonschema"` | 删除。依赖由插件环境 + scaffold 预置文件保证 | 服务端不感知运行环境 |
| 2 | Step 1 读 schema | LLM Read `wiring.schema.json`（spec 目录） | schema 由 scaffold 预置到 `{project}/.upy/schemas/wiring.schema.json`。服务端 LLM 内置 schema 知识直接生成 JSON，不再读文件 | spec 文件不在项目目录，服务端无法访问 |
| 3 | Step 2-3 读源文件 | LLM 直接 Read firmware/**/*.py + manifest | `file_operation(read)` 逐文件读取 firmware/ 下所有 .py。manifest 已在 start_phase.payload 中，无需重复读取 | 服务器通过插件读文件 |
| 4 | Step 4 写 wiring.json | LLM 写本地文件 | `file_operation(write)` → docs/wiring.json | 统一文件操作 |
| 5 | Step 5 校验 | `python validate_json.py --schema <spec路径> --json ...` | `script_run(validate_json.py --schema .upy/schemas/wiring.schema.json --json docs/wiring.json)`。脚本由 scaffold 预置到 `.upy/scripts/` | schema 和脚本需在项目目录中，插件本地可执行 |
| 6 | Step 6+7 渲染 | `python render_wiring_local.py --input ... --output ...` | `script_run(render_wiring_local.py --input docs/wiring.json --output docs/ --format all)`。脚本由 scaffold 预置 | 渲染需网络(mermaid.ink) + 写本地文件 → 插件执行 |
| 7 | Step 8 更新 manifest | `python -c "..."` inline 脚本 | `file_operation(read)` manifest → 服务端修改 wiring 字段 → `file_operation(write)` | 统一文件操作 |

---

## 五、校验脚本改动

### validate_json.py

**路径：** `G:\MicroPython_Skills\upy-project-gen-toolchain-spec\scripts\validate_json.py`

**无需改动。** 已经是通用 JSON Schema 校验器，输入 `--schema` + `--json`，输出 `[OK]` / `[FAIL]` + 错误列表，exit code 0=pass / 1=fail / 2=error。script_run 直接使用。

### render_wiring_local.py

**路径：** `G:\MicroPython_Skills\upy-wiring\scripts\render_wiring_local.py`

| 改动 | 内容 |
|------|------|
| 新增 `--json-summary` | 渲染完成时输出一行 JSON 摘要到 stdout：`{"status":"ok","files":[{"path":"docs/wiring.md","size":2048},...],"errors":[]}`。供服务端确认输出文件列表和大小 |

**其余不需要改。** 渲染脚本已经是防御式读取（`safe_get`），不会因 wiring.json 字段缺失崩溃。

### 对 upy-scaffold 的影响

| 源文件 | 目标位置 | 用途 |
|--------|---------|------|
| `G:/.../upy-project-gen-toolchain-spec/scripts/validate_json.py` | `{project}/.upy/scripts/validate_json.py` | wiring + diagram 共用校验 |
| `G:/.../upy-project-gen-toolchain-spec/wiring.schema.json` | `{project}/.upy/schemas/wiring.schema.json` | 校验 wiring.json |
| `G:/.../upy-wiring/scripts/render_wiring_local.py` | `{project}/.upy/scripts/render_wiring_local.py` | 渲染接线图 |

---

## 六、插件端 UI 组件

| 组件 | 对应消息 | 说明 |
|------|---------|------|
| 进度时间线 | status_update × ~10 | 读取→提取→生成→校验→渲染→输出 |
| 接线图预览 | 点击 file_list 中的 wiring.html | WebView 内嵌预览（Tab 切换接线图/源码/引脚表） |
| [生成接线图] 按钮 | 触发 start_phase | scaffold/generate 完成后启用 |
| [重新生成] 按钮 | 替换按钮 | 已生成后可重新生成 |

### 接线图预览说明

插件收到 phase_complete(file_list) 后，渲染为文件列表。用户点击 `wiring.html` → WebView 预览：

```
┌──────────────────────────────────────────┐
│ [接线图] [Mermaid源码] [引脚表]            │
├──────────────────────────────────────────┤
│                                          │
│   ┌─────────────────────┐                │
│   │    ESP32 DevKit     │                │
│   │  ┌──────┬──────┐    │    ┌────────┐  │
│   │  │ GPIO21│ SDA  │────┼────│ SHT30  │  │
│   │  │ GPIO22│ SCL  │────┼────│ 0x44   │  │
│   │  └──────┴──────┘    │    └────────┘  │
│   └─────────────────────┘                │
│                                          │
└──────────────────────────────────────────┘
```

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发 `status_update` 序列 → 验证读取→生成→校验→渲染→输出时间线
2. 手动发 `file_operation(read)` 请求 → 返回模拟 firmware/ 文件内容
3. 手动发 `file_operation(write)` → docs/wiring.json → 确认文件写入
4. 手动发 `phase_complete` (file_list) → 验证文件列表渲染 + wiring.html 预览入口

### Skill 端测试（无插件）

1. 准备完整 firmware/ 目录 + manifest，mock file_operation(read) 返回文件内容
2. LLM 生成 wiring.json → 运行 validate_json.py 校验通过
3. 运行 render_wiring_local.py → 确认 5 个输出文件生成
4. 验证交叉验证规则：构造 firmware 与 manifest 不一致的 case → 确认以 firmware 为准 + 告警
5. 检查所有发出的消息 JSON 符合 02-protocol.md Schema
