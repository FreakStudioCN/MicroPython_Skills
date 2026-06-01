---
name: upy-diagram
description: 第七步——软件架构图生成。读取 firmware/ 代码和 project-manifest.json，LLM 生成中间 JSON，脚本渲染 Mermaid 文本架构图（.md 代码块，CLI 原生可读）+ 可选 PNG。触发：upy-generate 完成后。
---

# 软件架构图生成 Skill

## 角色定位

给定 `project-manifest.json`（phase: generate）和 `firmware/` 下所有 `.py` 文件，LLM 理解 `diagram.schema.json` 后分析代码结构、执行流程、数据流向，填入中间 JSON，再由脚本校验并生成 Mermaid 文本图（Markdown 代码块）。**Mermaid .md 是主要输出（纯文本，CLI 原生可读），PNG 是可选后端。LLM 负责阅读代码并填写 JSON，脚本只做校验和文本图生成。**

---

## 前置检查

```bash
python --version
python -c "import jsonschema; print('jsonschema OK')"
```

缺失则提示安装：`pip install jsonschema`

PNG 渲染需要额外依赖，详见 Step 6 选项。

---

## 执行步骤

### Step 1: LLM 阅读 Schema → 理解结构

读取中间 JSON schema：

```
G:/MicroPython_Skills/upy-project-gen-toolchain-spec/diagram.schema.json
```

理解 4 个必需字段：`meta`, `architecture`, `flow`, `data_flow`，以及可选字段 `task_registry`, `diagnostics`。

### Step 2: LLM 阅读源代码 → 分析结构

读取以下所有文件（每个文件必须通读）：

```
{project_dir}/project-manifest.json
{project_dir}/firmware/main.py            ← 入口：DI 装配链 + 流程步骤
{project_dir}/firmware/conf.py            ← 配置常量
{project_dir}/firmware/board.py           ← 板级 pin 常量映射
{project_dir}/firmware/boot.py            ← 启动代码
{project_dir}/firmware/lib/               ← 基础库（logger/scheduler/time_helper 等）
{project_dir}/firmware/drivers/           ← 驱动工厂 + mock（每个 driver 一个包）
{project_dir}/firmware/tasks/             ← 业务 task 文件
```

### Step 3: LLM 分析并填写 diagram.json

#### 3A: `meta` — 元数据

从 manifest 提取：`project`, `mode`, `mcu`, `source_phase`。
`generated_at` 填当前 UTC 时间（ISO 8601）。

#### 3B: `architecture.layers[]` — 分层架构

**层定义（自下而上）：**

| 层 ID | label | 包含哪些模块 |
|-------|-------|-------------|
| `board` | 板级层(Board) | `board.py` — pin 常量映射 |
| `lib` | 基础库(Library) | `lib/` 下所有 .py：logger, scheduler, time_helper 等 |
| `driver` | 驱动层(Driver) | `drivers/<name>_driver/__init__.py` — 各器件工厂 |
| `task` | 任务层(Task) | `tasks/*.py` — 业务 task 函数 |
| `entry` | 入口层(Entry) | `main.py` — DI 装配入口 |
| `test` | 测试层(Test) | `test/pc/*.py` — PC 端测试；`test/device/*.py` — 设备端测试 |

可选附加层：`host`（`host/` 下有代码时）。

**每个 module 对象：**
- `name`：Python import 路径，如 `tasks.sensor_task`
- `path`：相对文件路径，如 `firmware/tasks/sensor_task.py`
- `role`：模块职责的中文简述（从 docstring 首行提取，无 docstring 则 LLM 补写）
- `provides`：导出的函数名/类名列表（从 `def` / `class` 提取，排除 `_` 前缀的私有符号）
- `depends_on`：依赖的模块名列表（从 `import` / `from X import` 提取，排除 `machine` 和标准库）
- `depends_on_machine`：是否直接 `import machine`（true 仅 main.py）
- `has_mock`：`drivers/<name>_driver/mock.py` 是否存在
- `is_generated`：文件是否由 upy-generate 生成（`@Generated : upy-generate` 标记）
- `is_template`：文件是否来自 scaffold 模板
- `source`：来源枚举（`scaffold_template` / `llm_generated` / `upypi_download` / `github_download` / `cold_driver` / `user_custom`）

**LLM 自主决定：**
- 是否拆分一个 task 文件为多个 module（如果一个 task 文件有多个独立功能）
- `cross_layer_deps[].style`：solid（直接依赖）/ dashed（DI 注入依赖）/ dotted（测试依赖）

#### 3C: `flow[]` — 执行流程

从 `main.py` 提取执行步骤序列，每一步：

- `seq`：从 1 开始的序号
- `phase`：步骤阶段
  - `boot` → 启动延时、WDT 设置
  - `init` → I2C/SPI 总线初始化、日志初始化
  - `scan` → I2C 器件扫描（`scan_xxx_i2c()`）
  - `create` → 驱动实例创建（`create_xxx()`）
  - `assembly` → DI 装配（驱动注入 task）
  - `run` → 调度器启动 / 事件循环运行
  - `shutdown` → 清理（如存在）
- `action`：中文简短标题（如 "初始化 I2C0 总线"）
- `detail`：具体参数（I2C 地址、Pin 脚号、频率等）
- `source_line`：在 main.py 中的行号
- `depends_on_step`：前置步骤 seq（如 create 依赖 scan 成功）
- `on_error`：失败策略（`fatal` 终止 / `skip_device` 跳过该器件继续 / `retry` 重试 / `degrade` 降级运行）
- `is_conditional` + `branches`：条件分支（如 scan 成功→create，失败→skip）

**LLM 自主决定：** 步骤粒度（一个 init 动作可拆成多步或合并）、条件分支的细节。

#### 3D: `data_flow[]` — 数据流

分析 task 函数之间的数据传递：

- `from` / `to`：数据来源和去向（模块名或函数名）
- `data`：传递的数据描述（如 "sensor_data dict {temp, humidity, pressure}"）
- `channel`：传输通道
  - `shared_dict` → 通过共享 dict 传递（如 `data["temp"] = ...`）
  - `function_return` → 函数返回值传递
  - `global_var` → 全局变量
  - `queue` → 通过 Queue 传递（async 模式）
  - `callback_param` → 回调函数参数
- `rate`：刷新频率（如 `1Hz`、`on_change`、`100ms`）

**LLM 自主决定：** data_flow 的粒度（可合并同类型流或逐条列出）。

#### 3E: `task_registry[]` — 任务注册清单

从 main.py 提取调度器注册信息（timer 模式从 `sc.register()` 提取，async 模式从 `asyncio.create_task()` 提取）：

- `name`：任务名
- `callback`：回调函数名
- `interval_ms`：执行间隔
- `mode`：`periodic` / `once` / `on_event`

#### 3F: `diagnostics` — 诊断信息

LLM 分析代码后填写：

- `total_modules`：architecture 中的模块总数
- `total_dependencies`：depends_on 的依赖边总数
- `max_depth`：依赖图最大深度（从 entry 向下数）
- `circular_deps`：检测到的循环依赖（应为空数组）
- `orphan_modules`：未被任何模块依赖的模块（如纯工具函数）
- `machine_direct_access`：直接 import machine 的模块（除 main.py 外应警告）

### Step 4: 校验 diagram.json

```bash
python G:/MicroPython_Skills/upy-project-gen-toolchain-spec/scripts/validate_json.py \
  --schema G:/MicroPython_Skills/upy-project-gen-toolchain-spec/diagram.schema.json \
  --json {project_dir}/docs/diagram.json
```

校验失败 → 修改 diagram.json → 重新校验，直到 pass。

### Step 5: 生成 Mermaid .md 文件 (主要输出)

**这是本 skill 的主要输出。** 脚本从 diagram.json 生成 3 个 Markdown 文件，每个文件内含 Mermaid 代码块，CLI 直接可读，VS Code / GitHub 原生渲染。

```bash
python G:/MicroPython_Skills/upy-diagram/scripts/render_diagram_local.py \
  --input {project_dir}/docs/diagram.json \
  --output {project_dir}/docs/
```

输出 3 个 Markdown 文件（内含 Mermaid 代码块）：

| 文件 | Mermaid 图类型 | 内容 |
|------|---------------|------|
| `docs/architecture.md` | `graph TB` | 分层架构图：subgraph 按层分组，节点=模块，边=依赖 |
| `docs/flowchart.md` | `sequenceDiagram` | 执行流程图：MCU 参与者，按 phase 分组，条件分支 + 错误处理 |
| `docs/data_flow.md` | `graph LR` | 数据流图：模块间数据通道，不同类型箭头表示不同 channel |

### Step 6: PNG 渲染（可选）

渲染脚本内置两种 PNG 方案：

**方案 A — mermaid.ink API（零本地依赖，需要网络）：**

```bash
python G:/MicroPython_Skills/upy-diagram/scripts/render_diagram_local.py \
  --input {project_dir}/docs/diagram.json \
  --output {project_dir}/docs/ \
  --format png
```

原理：Mermaid 代码 Base64 编码 → GET `https://mermaid.ink/img/{base64}?type=png` → 保存 PNG。

**方案 B — mermaid-cli（本地渲染，需要 Node.js）：**

```bash
npm install -g @mermaid-js/mermaid-cli
python G:/MicroPython_Skills/upy-diagram/scripts/render_diagram_local.py \
  --input {project_dir}/docs/diagram.json \
  --output {project_dir}/docs/ \
  --format png-local
```

默认使用 `--format md`（方案 A 适合服务器端，方案 B 适合本地 PC）。

### Step 7: 更新 manifest

```bash
cd {project_dir} && python -c "
import json, os
from datetime import datetime, timezone
path = 'project-manifest.json'
with open(path, 'r', encoding='utf-8') as f:
    m = json.load(f)
m['diagrams'] = m.get('diagrams', {})
m['diagrams']['json'] = 'docs/diagram.json'
m['diagrams']['architecture'] = 'docs/architecture.md'
m['diagrams']['flowchart'] = 'docs/flowchart.md'
m['diagrams']['data_flow'] = 'docs/data_flow.md'
m['diagrams']['generated_at'] = datetime.now(timezone.utc).isoformat()
with open(path, 'w', encoding='utf-8') as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
print('[OK] manifest diagrams updated')
"
```

---

## 与其他 skill 的关系

- ← `upy-generate`：输入完整 firmware 代码 + manifest
- 与 `upy-wiring` 并行：可同时生成
- → VS Code 插件 WebView：展示 Mermaid 图（Markdown 预览）或 PNG

---

## 强约束

- **LLM 生成 JSON，脚本只做校验 + 渲染**：与 `upy-generate` 模式一致
- **schema 是唯一契约**：diagram.json 必须通过 `validate_json.py` 校验
- **必须通读所有 firmware/*.py**：不跳过任何文件，架构分析基于真实代码
- **层 ID 必须使用 enum 值**：`board`, `lib`, `driver`, `task`, `entry`, `host`, `test`
- **flow phase 必须使用 enum 值**：`boot`, `init`, `scan`, `create`, `assembly`, `run`, `shutdown`
- **data_flow channel 必须使用 enum 值**：`function_return`, `shared_dict`, `global_var`, `queue`, `callback_param`
- **module.source 必须使用 enum 值**：`scaffold_template`, `llm_generated`, `upypi_download`, `github_download`, `cold_driver`, `user_custom`
- **provides/depends_on 从真实 import 和 def 提取**：不编造符号
- **diagnostics 如实填写**：包括 orphan_modules 和 machine_direct_access 警告
- **渲染脚本防御式读取**：缺失字段不会崩溃，但会在 stderr 输出警告
