---
name: mpos-gen-app
description: 'Generate, update, and repeatedly repair MicroPythonOS App code after requirements are confirmed. Use after mpos-analyze-app and optionally mpos-prepare-deps to create or modify an internal_filesystem/apps package directory with root MANIFEST.JSON, root icon_64x64.png, assets/*.py entrypoints/dependencies, dependency adapters, and validation results. Always defaults to a two-phase flow: first produce a generation plan and ask for confirmation, then write files only after explicit user confirmation. Supports repeated calls for user feature changes and test-failure repair loops. Does not analyze vague requirements, prepare external dependencies, package MPK files, deploy devices, flash firmware, publish to upystore, or rebuild lvgl_micropython.'
---

# MicroPythonOS App 代码生成

## 角色

把已确认的 MicroPythonOS App 需求落成代码。默认必须两阶段：

1. **确认阶段**：只读上下文，输出生成/修改计划，列出将创建或修改的文件、版本策略、依赖接入、图标方案和校验命令，并请用户确认。此阶段不改文件。
2. **执行阶段**：只有用户明确确认计划后，才创建、修改或修复 App 文件，并运行校验。

如果用户直接给自然语言想法但没有 `mpos-analyze-app` 结果，先路由到 `mpos-analyze-app`。如果需要外部纯 Python 驱动但没有 `mpos-prepare-deps` handoff，先路由到 `mpos-prepare-deps`。

## 统一项目日志

plan/create/update/repair 每次产出 `generation_result.json` 或确认计划后，都必须登记到项目状态目录：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill mpos-gen-app \
  --phase generate \
  --result <planned|success|partial|failed|blocked> \
  --artifact generation_result=<generation_result.json> \
  --next-skill <handoff.next_skill-or-null> \
  --event "Generated, updated, or repaired App files"
```

用户修改需求时，不要自己决定直接覆盖旧产物；先让 `mpos-plan-app` 列出将失效的 artifact 清单并等用户确认。两阶段确认仍强制执行，`mpos-plan-app` 不能替用户确认写文件。

## 必读上下文

生成或修改前先加载 `mpos-dev`，并按需读取：

- App/Activity/Service/Intent：`mpos-dev/reference/docs-app-model.md`
- 系统 manager、TaskManager、DownloadManager、WebServer、Service：`mpos-dev/reference/docs-frameworks.md`
- 打包和 manifest 校验：`mpos-dev/reference/docs-packaging.md`
- MPOS API 精确索引：`mpos-dev/reference/mpos_api_summary.json`
- LVGL API 精确索引：`mpos-dev/reference/lvgl_api_summary.json`
- 上游分析模板：`mpos-analyze-app/templates/analysis_result.json`
- 依赖 handoff 模板：`mpos-prepare-deps/templates/dependency_handoff.json`

本地事实优先：

- `<repo-root>/AGENTS.md`
- `<repo-root>/tests/test_apps_manifest.py`
- `<repo-root>/internal_filesystem/lib/mpos/content/app_manager.py`

## 模式

### plan

默认模式。适用于新建 App、修改功能、或测试失败后修复请求的第一步。

必须输出：

- 目标 App：`fullname`、`name`、`category`、`version`。
- 操作类型：`create`、`update` 或 `repair`。
- 文件计划：要创建/修改/保留的文件。
- Activity/Service 计划。
- 依赖计划：是否消费 `mpos-prepare-deps`，是否要生成同步适配层。
- 图标计划：用 `scripts/generate_icon.py` 根据用户功能说明生成根目录 `icon_64x64.png`。
- 版本策略：新 App `1.0.0`；功能修改 bump patch；测试失败修复不 bump。
- 校验计划：列出执行阶段要跑的门禁。
- 需要确认的问题；没有阻塞问题时也必须询问“确认后我再写文件”。

### create

用户确认后创建新 App。结构必须是：

```text
internal_filesystem/apps/<fullname>/
  MANIFEST.JSON
  icon_64x64.png
  assets/<entrypoint>.py
```

`MANIFEST.JSON` 使用完整对象，不使用字符串型 activity：

```json
{
  "classname": "ExampleActivity",
  "entrypoint": "assets/main.py",
  "intent_filters": [{"action": "main", "category": "launcher"}]
}
```

### update

用户修改功能时，先读取现有 App 的 manifest、entrypoint、assets、相关测试，再最小修改。不要重写无关文件，不要覆盖用户已有资源。功能修改默认 bump patch，例如 `1.0.0` -> `1.0.1`。

如果用户提出新增硬件、外部驱动或协议库，而没有依赖 handoff，停止并路由到 `mpos-analyze-app` 或 `mpos-prepare-deps`。

### repair

测试失败或用户反馈运行失败时，读取失败日志、命令输出、traceback、上次 `generation_result.json` 和相关源码。只修自己生成或本轮明确涉及的 App 文件。

允许不限次数自动修复自己生成/修改的文件：每轮做最小 patch，重新运行失败门禁和必要的完整门禁，直到通过或遇到外部阻塞。外部阻塞包括缺少用户需求、缺少依赖 handoff、工具未安装、硬件事实变化、或失败来自非本 App 文件。

repair 不 bump version，除非用户明确要求把修复作为发布版本。

## 需求确认

写文件前必须确认这些内容：

- `fullname` 是否可接受，目录是否为 `internal_filesystem/apps/<fullname>`。
- App 可见行为和 MVP 范围。
- Activity/Service 数量和入口文件。
- 是否要接入 `mpos-prepare-deps` 的 runtime 文件、imports、adapter requirements。
- 生成图标是否按功能说明自动生成。
- 版本策略是否接受。
- 校验范围是否接受。

缺失非阻塞字段时给默认值，但仍要把默认值放入确认计划中。用户未确认时不写文件。

## 依赖接入

如果有 `mpos-prepare-deps` handoff：

- 把 runtime 文件放到 handoff 的 `target_path`，通常是 `assets/<module>.py` 或 `assets/<package>/...`。
- 如果 handoff 有 `staged_path`，从 staged cache 复制到 App 目录。
- 对 `async_compatible=true` 的依赖，按 `imports[]` 直接使用。
- 对 `sync_needs_adapter=true` 的依赖，必须生成 `assets/<name>_adapter.py` 或等价适配层，并把 handoff 的 `adapter_requirements[]` 逐条落实。
- 如果 `requires_vendor_path_injection=true`，只在 entrypoint 开头加入最小 path 注入：

```python
import sys

_VENDOR_DIR = sys.path[0] + "/vendor"
if _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)
```

不要把同步库直接放进 `async def` 或 LVGL 事件回调里阻塞执行。使用 `TaskManager.create_task`、`TaskManager.sleep_ms`、短周期状态机、timeout 和取消路径。

## 图标生成

新 App 或缺失图标时，使用本 skill 的脚本生成图标：

```bash
python3 /home/leeqingshui/MicroPython_Skills/mpos-gen-app/scripts/generate_icon.py \
  --prompt "<用户功能说明>" \
  --label "<App name>" \
  --output internal_filesystem/apps/<fullname>/icon_64x64.png
```

脚本只用 Python 标准库生成 64x64 PNG，不依赖 Pillow。图标应基于功能关键词选择简单符号；如果关键词不明确，用 App 名首字母。

## 代码规则

- 新代码优先从根 `mpos` 模块导入：`from mpos import Activity, TaskManager, SharedPreferences`。
- UI 代码必须 `import lvgl as lv` 并遵守 `mpos-dev` 的 LVGL 规则。
- 不硬编码屏幕分辨率，使用 `lv.pct(100)`、flex、align。
- 新 label 立即 `set_text("")` 或设置最终文本。
- `lv.style_t()` 后必须 `init()` 再 setter。
- 事件回调接受 event 参数，使用 `obj.add_event_cb(callback, lv.EVENT.CLICKED, None)`。
- 不给 LVGL 对象随意赋 Python 属性；用 closure、dict 或并行列表保存状态。
- 持久化用 `SharedPreferences(self.appFullName)`。
- 不写真实 API key、token、password、Bearer 到代码、manifest、测试、日志或 JSON。
- 不使用 CPython-only runtime 模块：`typing`、`dataclasses`、`pathlib`、`logging`、`requests`、`subprocess`、`multiprocessing`。
- 需要 asyncio 时优先 `uasyncio`；CPython fallback 只能用于测试兼容模式：

```python
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
```

## 校验门禁

执行阶段每次写文件后必须运行并记录这些门禁。命令从 `<repo-root>` 仓库根执行。

1. App manifest 校验：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python -m unittest tests/test_apps_manifest.py
```

2. CPython 与 MicroPython 语法校验：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-gen-app/scripts/check_app_syntax.py \
  --repo <repo-root> \
  --app-fullname <fullname>
```

3. MicroPython import 风险：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-gen-app/scripts/check_app_mpy_imports.py \
  --app-dir internal_filesystem/apps/<fullname>
```

4. 项目 lint：

```bash
make lint
```

5. flake8：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python -m flake8 \
  --config /home/leeqingshui/MicroPython_Skills/mpos-gen-app/templates/flake8-mpos-app.ini \
  internal_filesystem/apps/<fullname>
```

使用固定模板 `templates/flake8-mpos-app.ini`。该模板按当前全部真实 App 基线校准：只选 `E9,F63,F7,F82`，补充 MicroPython/native/viper/RP2 PIO 指令内建名，不全局忽略 `F821`；仅对 `rp2_*.py`、`*_pio.py` 做文件级 `F821` 忽略，避免 PIO 汇编伪操作数污染普通 Python 检查。如果新生成 App 出现未定义名，修代码，不要临时放宽模板。

6. pylint。使用固定 MicroPython-aware rcfile，不要改仓库配置：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python -m pylint \
  --persistent=n \
  --rcfile=/home/leeqingshui/MicroPython_Skills/mpos-gen-app/templates/pylintrc-mpos-app \
  internal_filesystem/apps/<fullname>/assets
```

使用固定模板 `templates/pylintrc-mpos-app`。该模板按当前全部真实 App 基线校准：忽略 MicroPython/MPOS 导入、LVGL 动态成员、docstring、命名和历史风格噪声；保留 fatal/error/usage 类问题，例如 `undefined-variable`、`used-before-assignment`、`function-redefined`、`no-method-argument`。不要把 `x`、`y`、`pin` 这类普通变量名加入全局 builtins；若确实生成 RP2 PIO helper，只允许在该 helper 文件头局部声明 `# pylint: disable=undefined-variable` 并在 `generation_result.validation.warnings` 记录原因。Pylint exit code 是 bitmask：fatal(1)、error(2)、usage(32) 是强失败；warning(4)、refactor(8)、convention(16) 只记录 warning，除非用户要求严格模式。

7. 清理缓存产物：

```bash
find internal_filesystem/apps/<fullname> -name __pycache__ -o -name '*.pyc' -print
```

如果有输出，删除后重跑相关门禁。不要把 `__pycache__/` 或 `.pyc` 写入交接 JSON。

## 输出 JSON

执行阶段结束时输出并可保存 `generation_result.json`。结构参考 `templates/generation_result.json`，并用脚本校验：

```bash
python3 /home/leeqingshui/MicroPython_Skills/mpos-gen-app/scripts/validate_generation_result.py \
  /path/to/generation_result.json
```

成功的 `create/update/repair` 必须记录：

- `confirmed_by_user: true`
- 创建/修改文件
- 版本变化
- icon 生成结果
- 依赖和同步 adapter 结果
- 所有校验门禁及 returncode
- `handoff.next_skill: "mpos-test-app"`

plan 阶段 `confirmed_by_user` 必须是 `false`，并且 `handoff.next_skill` 仍指向 `mpos-gen-app`。

## 下游

代码生成成功后交给 `mpos-test-app`。如果用户只要求生成代码，可以把 `handoff.next_skill` 设为 `null`，但仍必须报告校验结果。
