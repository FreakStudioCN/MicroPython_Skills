# upy-scaffold 接口定义

> 状态：✅ 已定稿
>
> Phase 3 — 项目骨架生成。读取 select-hw 阶段的 project-manifest.json，按调度模式生成完整 firmware/ 目录骨架。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | scaffold |
| 上游 Skill | upy-select-hw（自动进入） 或 任意 phase 的增量触发（用户加器件） |
| 下游 Skill | upy-generate |
| 一句话职责 | 确定调度模式 → 渲染模板 → 生成 firmware/ 完整骨架（不写业务逻辑） |

**核心约束：** 不写业务 task、不填驱动代码、不转换异步驱动。只搭骨架，业务留给 upy-generate。

**两种运行模式：**

| 模式 | 触发 | 行为 |
|------|------|------|
| `full` | upy-select-hw 完成 | 全新生成完整 firmware/ 骨架 |
| `incremental` | 用户在后续 phase 新增器件 | 只给新器件生成 `drivers/<name>_driver/__init__.py` stub |

---

## 二、插件输入 → Skill（P→S）

插件发 **1 条消息** 启动本 skill：

```json
{
  "type": "start_phase",
  "phase": "scaffold",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "full",
    "manifest": { "...完整的 project-manifest.json（phase: select-hw）..." },
    "new_devices": []
  }
}
```

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `mode` | string | 是 | 服务器判断 | `"full"` 全新生成 / `"incremental"` 增量 stub |
| `manifest` | object | 是 | upy-select-hw 的 phase_complete | 完整的 project-manifest.json |
| `new_devices` | array | incremental 必填 | 用户新增的器件列表 | `[{name, driver: {source, install_cmd}}]` |

**mode 判断逻辑（服务器端）：**
- `manifest.phase === "select-hw"` 且首次进入 → `full`
- 用户在后续 phase 点了 "添加器件" → select-hw 增量分完引脚后，scaffold 收到 `incremental`

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
full 模式：
  Step 1 审批选型
    → approval_request #1: 合并卡片（调度模式 + 额外模块 + 自定义）
  
  Step 2 文档参考
    → [内部] WebFetch asyncio/_thread 官方文档（服务端有网络，对插件不可见）
  
  Step 3 生成骨架
    → status_update "正在渲染 board.py..."
    → status_update "正在渲染 conf.py / boot.py..."
    → status_update "正在渲染 main.py (mode: timer)..."
    → status_update "正在复制 lib/ 基础库..."
    → status_update "正在生成 drivers/ stub..."
    → status_update "正在复制 tools/ 部署工具..."
    → file_operation × N（每个生成的文件一条 write 消息）
  
  Step 4 校验
    → script_run: flake8
  
  Step 5 输出
    → phase_complete: 结果面板

incremental 模式：
    → status_update "正在为新器件生成 driver stub..."
    → file_operation × 1（只写 drivers/<name>_driver/__init__.py）
    → phase_complete
```

### 消息详情

#### approval_request #1 — 合并审批卡片

合并了当前 SKILL.md 的三个 AskUserQuestion（调度模式 + 额外模块 + 自定义）为一张卡片，分三个区域。

```
┌──────────────────────────────────────────┐
│  项目骨架配置                              │
│                                          │
│  ▸ 调度模式（单选）                        │
│  ◉ Timer tick (推荐)                      │
│     ISR计数 + 主循环轮询，适合纯传感器采集    │
│  ○ asyncio                                │
│     uasyncio 协程，适合 WiFi / LCD 项目     │
│  ○ _thread                                │
│     多线程，适合阻塞式操作                   │
│                                          │
│  ▸ 额外模块（多选）                        │
│  ☑ 日志系统 (lib/logger/*)                 │
│  ☑ 部署工具 (tools/flash_device.py)        │
│  ☐ 性能计时器 (lib/time_helper.py)         │
│  ☐ 维护任务 (tasks/maintenance.py)         │
│  ☐ PC日志读取 (tools/read_device_log.py)   │
│                                          │
│  ▸ 自定义文件（可选）                       │
│  [+ 添加自定义目录/文件]                    │
│                                          │
│  [确认，开始生成骨架]  [修改配置]            │
└──────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "scaffold_config",
    "header": "项目骨架配置",
    "question": "选择调度模式和需要注入的模块",
    "summary": {
      "project_name": "温湿度监测报警器",
      "mcu": "ESP32 DevKit V1"
    },
    "items": [
      {
        "id": "mode_timer",
        "name": "Timer tick (推荐)",
        "subtitle": "ISR计数 + 主循环轮询，适合纯传感器采集",
        "meta": "★ 推荐",
        "selected": true,
        "group": "scheduler_mode"
      },
      {
        "id": "mode_async",
        "name": "asyncio",
        "subtitle": "uasyncio 协程，适合 WiFi / LCD / LVGL 项目",
        "meta": "",
        "selected": false,
        "group": "scheduler_mode"
      },
      {
        "id": "mode_thread",
        "name": "_thread",
        "subtitle": "多线程，适合阻塞式操作",
        "meta": "",
        "selected": false,
        "group": "scheduler_mode"
      },
      {
        "id": "module_logger",
        "name": "日志系统",
        "subtitle": "lib/logger/* — logging + rotating_logger，设备端日志记录与轮转",
        "meta": "推荐",
        "selected": true,
        "group": "extra_modules"
      },
      {
        "id": "module_flash",
        "name": "部署工具",
        "subtitle": "tools/flash_device.py — mpy 编译 + 固件烧录 + 文件上传",
        "meta": "推荐",
        "selected": true,
        "group": "extra_modules"
      },
      {
        "id": "module_time_helper",
        "name": "性能计时器",
        "subtitle": "lib/time_helper.py — timed_function / timed_coro 装饰器",
        "meta": "",
        "selected": false,
        "group": "extra_modules"
      },
      {
        "id": "module_maintenance",
        "name": "维护任务",
        "subtitle": "tasks/maintenance.py — GC 检查 + 空闲回调",
        "meta": "",
        "selected": false,
        "group": "extra_modules"
      },
      {
        "id": "module_log_tools",
        "name": "PC 日志工具",
        "subtitle": "tools/read_device_log.py + log_report.py — PC 端日志读取与 JSON 报告",
        "meta": "",
        "selected": false,
        "group": "extra_modules"
      }
    ],
    "allow_add": true,
    "allow_remove": false,
    "multi_select": true,
    "item_groups": {
      "scheduler_mode": {"multi_select": false, "label": "调度模式"},
      "extra_modules": {"multi_select": true, "label": "额外模块"}
    },
    "actions": [
      { "label": "确认，开始生成骨架", "value": "confirm", "primary": true },
      { "label": "修改配置", "value": "modify" }
    ]
  }
}
```

**item_groups 字段说明（新增）：**

将 items 按 `group` 分组渲染，不同组可以有不同的选择模式：
- `scheduler_mode`：`multi_select: false` → 单选（radio button）
- `extra_modules`：`multi_select: true` → 多选（checkbox）

**调度模式推荐规则（LLM 在服务端根据 manifest 判断，仅标记 ★ 推荐）：**

| 条件 | 推荐 |
|------|------|
| devices 中有 display 且含 LVGL | async |
| requirements.network = wifi | async |
| 默认 | timer |

#### status_update 列表

| step_id | message | level | 触发时机 |
|---------|---------|-------|---------|
| scaffold_start | 正在生成项目骨架... | info | Step 3 开始 |
| render_board | 正在渲染 board.py（引脚映射 + 查询函数）... | info | 生成 board.py |
| render_conf | 正在渲染 conf.py / boot.py... | info | 生成配置文件 |
| render_main | 正在渲染 main.py (mode: timer)... | info | 生成入口文件 |
| copy_lib | 正在复制 lib/ 基础库 (logger + scheduler)... | info | 复制模板文件 |
| gen_drivers | 正在生成 drivers/ stub (3 个器件)... | info | 生成驱动桩 |
| copy_tools | 正在复制 tools/ 部署工具... | info | 复制 PC 工具 |
| scaffold_lint | 正在运行 flake8 校验... | info | 校验开始 |
| scaffold_lint_ok | ✓ flake8 校验通过 | success | 校验通过 |
| scaffold_lint_warn | ⚠ flake8 发现 N 个问题，已自动修复 | warn | 校验有问题但可修复 |
| scaffold_done | ✓ 骨架生成完成：18 个文件，8 个目录 | success | 全部完成 |
| incremental_stub | 正在为新器件 DHT22 生成 driver stub... | info | incremental 模式 |
| incremental_done | ✓ DHT22 driver stub 已生成 | success | incremental 完成 |

#### file_operation 序列

服务器先运行 `init_scaffold.py`（stdin 读 manifest，stdout 输出 JSON），得到文件列表后逐条发送：

```json
{
  "type": "file_operation",
  "payload": {
    "op_id": "scaffold_fo_001",
    "op": "write",
    "path": "firmware/board.py",
    "content": "# -*- coding: utf-8 -*-\n# @Generated : upy-scaffold\n...",
    "encoding": "utf-8"
  }
}
```

**full 模式生成的完整文件清单（timer 模式 + 全模块）：**

| # | 文件路径 | 生成方式 | 说明 |
|---|---------|---------|------|
| 1 | `firmware/board.py` | 模板渲染 | 引脚映射 BOARDS 字典 + 查询函数 |
| 2 | `firmware/conf.py` | 模板渲染 | 采样率/日志/看门狗常量 |
| 3 | `firmware/boot.py` | 模板渲染 | WDT + emergency_exception_buf |
| 4 | `firmware/main.py` | 模板渲染 | 按模式生成硬件实例化 + 调度器框架 |
| 5 | `firmware/lib/logger/logging.py` | 纯复制 | 日志核心 |
| 6 | `firmware/lib/logger/rotating_logger.py` | 纯复制 | 轮转日志 |
| 7 | `firmware/lib/logger/__init__.py` | 纯复制 | logger 包导出 |
| 8 | `firmware/lib/scheduler/timer_sched.py` | 纯复制 | Timer 调度器（仅 timer 模式） |
| 9 | `firmware/lib/scheduler/__init__.py` | 生成 | `from .timer_sched import Scheduler` |
| 10 | `firmware/lib/time_helper.py` | 纯复制 | 性能计时装饰器（可选） |
| 11 | `firmware/tasks/maintenance.py` | 纯复制 | GC 检查 + 空闲回调（可选） |
| 12 | `firmware/tasks/__init__.py` | 生成 | `# Tasks package` |
| 13~N | `firmware/drivers/<name>_driver/__init__.py` | 生成 | 每个器件一个 stub，含 TODO 注释 |
| N+1 | `tools/flash_device.py` | 纯复制 | mpy 编译 + 烧录 + 上传 |
| N+2 | `tools/read_device_log.py` | 纯复制 | PC 端设备日志读取 |
| N+3 | `tools/log_report.py` | 纯复制 | 日志→JSON 报告 |
| N+4 | `README.md` | 模板渲染 | 项目名 + BOM 表 + 引脚表 |
| N+5 | `LICENSE` | 生成 | MIT |
| N+6 | `.flake8` | 生成 | F821/F401 豁免 + max-line=120 |
| N+7~14 | `host/.gitkeep` 等 | 生成 | 占位文件（8 个目录） |
| — | `.upy/schemas/project-manifest.schema.json` | 纯复制 | manifest 校验 schema |
| — | `.upy/schemas/wiring.schema.json` | 纯复制 | wiring.json 校验 schema |
| — | `.upy/schemas/diagram.schema.json` | 纯复制 | diagram.json 校验 schema |
| — | `.upy/schemas/diagnostic_bundle.schema.json` | 纯复制 | 诊断包校验 schema |
| — | `.upy/scripts/validate_json.py` | 纯复制 | 通用 JSON Schema 校验器（wiring + diagram + autofix 共用） |
| — | `.upy/scripts/init_scaffold.py` | 纯复制 | 骨架生成脚本（本 skill 自用） |
| — | `.upy/scripts/download_drivers.py` | 纯复制 | 驱动下载（generate 用） |
| — | `.upy/scripts/render_wiring_local.py` | 纯复制 | 接线图渲染（wiring 用） |
| — | `.upy/scripts/render_diagram_local.py` | 纯复制 | 架构图渲染（diagram 用） |
| — | `.upy/scripts/extract_pdf.py` | 纯复制 | PDF 文本提取（gen-driver 用） |
| — | `.upy/scripts/convert_arduino.py` | 纯复制 | Arduino API 映射（gen-driver 用） |
| — | `.upy/scripts/flash_device.py` | 纯复制 | 烧录+验证（deploy 用） |
| — | `.upy/scripts/read_device_log.py` | 纯复制 | 设备日志读取（deploy 用） |
| — | `.upy/scripts/run_on_device.py` | 纯复制 | REPL 执行+捕获（gen-driver + deploy 共用） |
| — | `.upy/scripts/hardware_sanity.py` | 纯复制 | 硬件信号验证（autofix 用） |
| — | `.upy/scripts/triage.py` | 纯复制 | 自动排查（autofix 用） |
| — | `.upy/error_lib.json` | 纯复制 | 错误库模板（autofix 用） |

#### script_run — flake8 校验

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "scaffold_lint_001",
    "interpreter": "python",
    "script": "flake8",
    "args": ["firmware/", "tools/", "--max-line-length=120"],
    "cwd": "{project_dir}",
    "timeout_ms": 15000
  }
}
```

#### phase_complete

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "scaffold",
    "result": "success",
    "summary": "项目骨架生成完成：timer 模式，18 个文件，8 个目录",
    "next_phase": "generate",
    "artifacts": [
      {
        "type": "file_tree",
        "title": "项目结构",
        "tree": {
          "firmware": {
            "board.py": "file",
            "conf.py": "file",
            "boot.py": "file",
            "main.py": "file",
            "lib": {
              "logger": {
                "logging.py": "file",
                "rotating_logger.py": "file",
                "__init__.py": "file"
              },
              "scheduler": {
                "timer_sched.py": "file",
                "__init__.py": "file"
              },
              "time_helper.py": "file"
            },
            "tasks": {
              "maintenance.py": "file",
              "__init__.py": "file"
            },
            "drivers": {
              "sht30_driver": { "__init__.py": "file" },
              "ssd1306_driver": { "__init__.py": "file" },
              "buzzer_driver": { "__init__.py": "file" }
            },
            "assets": {}
          },
          "tools": {
            "flash_device.py": "file",
            "read_device_log.py": "file",
            "log_report.py": "file"
          },
          "test": { "device": {}, "pc": {} },
          "host": {},
          "build": { "firmware": {}, "mpy": {} }
        }
      }
    ],
    "warnings": [],
    "errors": [],
    "manifest_content": "{完整的更新后 project-manifest.json JSON 文本}"
  }
}
```

**manifest_content 新增/更新字段：**
- `phase`: `"scaffold"`
- `scaffold_mode`: `"timer"` / `"async"` / `"thread"`
- `scaffold_modules`: `["logger", "flash_device", ...]`

---

## 四、SKILL.md 修改点

共 7 处改动，按执行步骤排列：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 前置检查 | `python --version` + `python -c "import flake8"` | 删除。依赖检查由服务器环境保证 | 插件用户不可见服务器环境 |
| 2 | Step 1A | AskUserQuestion 单选调度模式 | 合并到 approval_request #1 的 `scheduler_mode` 分组（单选，含推荐标记） | 3 问合并为 1 卡 |
| 3 | Step 1B | AskUserQuestion 多选额外模块 | 合并到同一 approval_request 的 `extra_modules` 分组（多选） | 同上 |
| 4 | Step 1C | AskUserQuestion 自定义文件 | 合并到同一 approval_request，通过 `allow_add: true` + 输入框实现 | 同上 |
| 5 | Step 2 | WebFetch asyncio/_thread 官方文档 | 不变。服务端有网络，对插件不可见 | 无需改动 |
| 6 | Step 3 | `python init_scaffold.py --project-dir {dir} --mode {mode}` 写本地磁盘 | `python init_scaffold.py --mode {mode} --manifest - < manifest.json`（stdin 进，stdout 出 JSON）。服务器解析 JSON 后发 `file_operation` 序列给插件 | 服务器不写本地磁盘 |
| 7 | 新增 incremental | 无此模式 | `--mode incremental --new-devices '[{...}]'` 只给新器件生成 `drivers/<name>_driver/__init__.py` stub | 支持 deploy 阶段加器件 |

---

## 五、模板文件与脚本改动

### 5.1 init_scaffold.py 改动

**路径：** `G:\MicroPython_Skills\upy-scaffold\scripts\init_scaffold.py`

| 改动 | 内容 |
|------|------|
| 输入方式 | `--project-dir` 改为 `--manifest -`（从 stdin 读 manifest JSON） |
| 输出方式 | 不再写磁盘。输出 JSON 到 stdout：`{phase, mode, directories[], files[{path, content, encoding}], summary}` |
| 模板引擎 | 引入 `string.Template`（Python 标准库，零额外依赖），替代 5 个 `generate_*` 函数的 `lines.append()` 拼接 |
| 增量模式 | 新增 `--mode incremental --new-devices '[{name, driver}]'` |
| flake8 移除 | 移除脚本末尾的 `subprocess.run(flake8)`，改为由 Phase 4 的 `script_run` 消息触发 |

**string.Template 替换示例：**

```python
from string import Template

def render_template(tmpl_name, variables):
    tmpl_path = os.path.join(TEMPLATES_DIR, tmpl_name + ".tmpl")
    with open(tmpl_path, "r", encoding="utf-8") as f:
        tmpl = Template(f.read())
    return tmpl.safe_substitute(variables)
```

**init_scaffold.py 核心流程（伪代码）：**

```python
def main():
    args = parse_args()
    manifest = json.load(sys.stdin)

    variables = extract_variables(manifest)  # 从 manifest 提取模板变量
    files = []
    dirs = []

    # 1. 渲染模板文件
    for tmpl in ["firmware/board.py", "firmware/conf.py", "firmware/boot.py",
                 f"firmware/main_{mode}.py", "firmware/README.md"]:
        content = render_template(tmpl, variables)
        files.append({"path": tmpl, "content": content, "encoding": "utf-8"})

    # 2. 纯复制文件（根据模式和用户勾选决定复制哪些）
    for src in COPY_FILES[mode]:
        content = read_raw(os.path.join(TEMPLATES_DIR, src))
        files.append({"path": "firmware/" + src, "content": content, "encoding": "utf-8"})

    # 3. 生成 driver stubs
    for device in manifest["devices"]:
        stub = f"# {device['name']} driver stub\n# TODO: upy-generate fills this\n"
        name = safe_var_name(device["name"])
        files.append({"path": f"firmware/drivers/{name}_driver/__init__.py",
                       "content": stub, "encoding": "utf-8"})
        dirs.append(f"firmware/drivers/{name}_driver")

    # 4. 其他生成文件
    files.append({"path": ".flake8", "content": generate_flake8(), "encoding": "utf-8"})
    files.append({"path": "LICENSE", "content": generate_license(), "encoding": "utf-8"})

    # 5. 收集目录
    dirs += infer_directories(files)

    # 6. 输出 JSON 到 stdout
    output = {
        "phase": "scaffold",
        "mode": mode,
        "scaffold_mode": mode,
        "directories": sorted(set(dirs)),
        "files": files,
        "summary": f"Generated {len(files)} files, {len(dirs)} directories"
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
```

### 5.2 新增模板文件（7 个 .py.tmpl）

**路径：** `G:\MicroPython_Skills\upy-scaffold\templates\firmware\`

| 模板文件 | 用途 | 关键变量 |
|---------|------|---------|
| `board.py.tmpl` | 引脚映射常量 | `${MCU_MODEL}` `${BOARD_ID}` `${I2C_PINS_BLOCK}` `${FIXED_PINS_BLOCK}` `${I2C_FREQ}` `${UART_BAUD}` `${BOOT_SENSITIVE_LIST}` `${FLASH_PINS_LIST}` `${INPUT_ONLY_LIST}` |
| `conf.py.tmpl` | 项目配置常量 | `${PROJECT_NAME}` `${MCU_MODEL}` `${FW_VERSION}` `${SAMPLE_INTERVAL_MS}` `${LOG_DIR}` `${LOG_LEVEL}` |
| `boot.py.tmpl` | 启动引导 | `${GENERATED_AT}`（几乎无变量，仅 emergency_exception_buf 模板） |
| `main_timer.py.tmpl` | Timer 模式入口 | `${PROJECT_NAME}` `${I2C_INIT_BLOCK}` `${GPIO_INIT_BLOCK}` |
| `main_async.py.tmpl` | asyncio 模式入口 | 同上 |
| `main_thread.py.tmpl` | _thread 模式入口 | 同上 |
| `README.md.tmpl` | 项目 README | `${PROJECT_NAME}` `${MODE}` `${MCU_MODEL}` `${MCU_BOARD}` `${FIRMWARE_URL}` `${BOM_TABLE_ROWS}` `${PINOUT_TABLE_ROWS}` `${TOTAL_PRICE}` |

多行块变量（`${I2C_INIT_BLOCK}`、`${GPIO_INIT_BLOCK}`、`${BOM_TABLE_ROWS}`、`${PINOUT_TABLE_ROWS}`、`${FIXED_PINS_BLOCK}`、`${I2C_PINS_BLOCK}`）由 Python 脚本从 manifest.pinout/manifest.bom 预先计算好字符串，模板里放一个占位符。

### 5.3 模板目录结构

```
upy-scaffold/templates/
├── firmware/                     ← 7 个 .py.tmpl 模板（需渲染）
│   ├── board.py.tmpl
│   ├── conf.py.tmpl
│   ├── boot.py.tmpl
│   ├── main_timer.py.tmpl
│   ├── main_async.py.tmpl
│   ├── main_thread.py.tmpl
│   └── README.md.tmpl
├── lib/                          ← 纯复制（9 个 .py，无变量）
│   ├── logger/
│   │   ├── logging.py
│   │   ├── rotating_logger.py
│   │   └── __init__.py
│   ├── scheduler/
│   │   └── timer_sched.py
│   └── time_helper.py
├── tasks/
│   └── maintenance.py            ← 纯复制
└── pc/                           ← 纯复制
    ├── flash_device.py
    ├── read_device_log.py
    └── log_report.py
```

纯复制的 9 个 `.py` 文件是完整可运行的代码，不包含 `${变量}` 占位符，脚本读什么就输出什么。

### 5.4 init_scaffold.py stdout JSON 规范

```json
{
  "phase": "scaffold",
  "mode": "timer",
  "scaffold_mode": "timer",
  "directories": [
    "firmware/drivers/buzzer_driver",
    "firmware/drivers/sht30_driver",
    "firmware/drivers/ssd1306_driver",
    "firmware/lib/logger",
    "firmware/lib/scheduler",
    "firmware/tasks",
    "host",
    "test/device",
    "test/pc",
    "tools",
    ".upy",
    ".upy/schemas",
    ".upy/scripts"
  ],
  "files": [
    {
      "path": "firmware/board.py",
      "content": "# -*- coding: utf-8 -*-\n# @Generated : upy-scaffold\n...",
      "encoding": "utf-8"
    },
    {
      "path": "firmware/main.py",
      "content": "from machine import Pin, I2C\n...",
      "encoding": "utf-8"
    }
  ],
  "summary": "Generated 18 files, 10 directories"
}
```

服务器收到后遍历 `files` 数组，逐条发 `file_operation`（op: "write"）给插件端写入本地磁盘。`directories` 数组用于插件端预先创建目录。

---

## 六、插件端需要实现的 UI 组件

| 组件 | 对应消息 | 关键功能 |
|------|---------|---------|
| 进度时间线 | status_update × 5~8 条 | 复用已有时间线组件 |
| 骨架配置卡片 | approval_request #1 | 调度模式单选 + 额外模块多选 + 自定义文件输入框。**新增 `item_groups` 分组渲染**（不同 group 不同选择模式） |
| 文件树预览 | phase_complete artifact[0] | 树形目录展示生成的文件结构 |
| 文件写入 | file_operation × N | 逐文件写入本地磁盘（需新增"骨架生成中，正在写入文件..."进度提示） |

### item_groups 分组渲染规范

当 approval_request 包含 `item_groups` 字段时，插件应按分组渲染：

```
┌─ scheduler_mode: "调度模式" (radio) ─┐
│  ◉ Timer tick (推荐)                 │
│  ○ asyncio                           │
│  ○ _thread                           │
└──────────────────────────────────────┘

┌─ extra_modules: "额外模块" (checkbox) ┐
│  ☑ 日志系统                           │
│  ☑ 部署工具                           │
│  ☐ 性能计时器                         │
└──────────────────────────────────────┘
```

`item_groups` 中每个 group 的 `multi_select` 决定渲染为 radio 还是 checkbox。

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发 `approval_request` #1（骨架配置卡片）→ 验证：
   - `item_groups` 分组渲染正确（scheduler_mode 单选、extra_modules 多选）
   - 切换调度模式，推荐标记跟随显示
   - 勾选/取消额外模块
   - 点击"添加自定义文件"弹出输入框
2. 手动发 `phase_complete`（含 file_tree artifact）→ 验证文件树渲染正确
3. 手动发 `file_operation` 序列（5 条 write）→ 验证文件逐条写入本地磁盘 + 进度提示

### Skill 端测试（无插件）

1. **full 模式 + timer：**
   - mock_plugin 发送 start_phase（mode=full, manifest=温湿度项目，phase: select-hw）
   - 对 approval_request #1 自动回复 `{"action": "confirm", "selected_ids": ["mode_timer", "module_logger", "module_flash"]}`
   - 验证 init_scaffold.py stdout JSON 包含 15+ 个文件
   - 验证所有 file_operation 路径正确、encoding 为 utf-8
2. **full 模式 + async：**
   - mock_plugin 回复中选择 mode_async
   - 验证 main.py 使用 uasyncio 框架
   - 验证不注入 scheduler/timer_sched.py
3. **incremental 模式：**
   - mock_plugin 发送 start_phase（mode=incremental, new_devices=[{name: "DHT22", driver: {source: "upypi"}}]）
   - 验证只生成 1 个文件：`firmware/drivers/dht22_driver/__init__.py`
4. **init_scaffold.py 模板渲染：**
   - 给一个标准 manifest，运行 `python init_scaffold.py --mode timer --manifest - < test_manifest.json`
   - 验证 stdout JSON 中 board.py 的 I2C 引脚与 manifest.pinout 一致
   - 验证 main.py 的 GPIO 初始化与 manifest.pinout 一致
   - 验证 README.md 的 BOM 表与 manifest.bom 一致
