# upy-generate 接口定义

> 状态：✅ 已定稿
>
> Phase 4 — 业务代码生成（最重的 skill）。下载驱动、生成 DI 架构的业务代码、Mock 层、单元测试。支持全量生成和 autofix 触发的定向修复两种模式。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | generate |
| 上游 Skill | upy-scaffold（full 模式） / upy-autofix（fix 模式） |
| 下游 Skill | upy-simulate（手动触发） / upy-deploy（自动进入） |
| 一句话职责 | 下载驱动 → 理解 API → 生成工厂+Mock → 生成 task → 补充配置 → DI 装配 → 测试生成 → 多层校验 |

**核心约束：** 除 main.py 外所有代码不 import machine。DI 鸭子类型。print() + logger 双写。每个 task 独立 try/except。

**两种运行模式：**

| 模式 | 触发 | 行为 |
|------|------|------|
| `full` | upy-scaffold 完成 | 全流程 9 个 Phase，从驱动下载到测试生成 |
| `fix` | upy-autofix 委托 | 只读出错文件 → 最小化修改 → lint 验证 → 返回 diff |

---

## 二、插件输入 → Skill（P→S）

### full 模式

```json
{
  "type": "start_phase",
  "phase": "generate",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "full",
    "manifest": { "...完整的 project-manifest.json（phase: scaffold）..." }
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | string | 是 | `"full"` |
| `manifest` | object | 是 | 完整 manifest，必须含 `scaffold_mode` + `devices[].driver` + `pinout` |

### fix 模式（由 upy-autofix 调用）

```json
{
  "type": "start_phase",
  "phase": "generate",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "fix",
    "manifest": { "...完整的 manifest..." },
    "error_context": {
      "traceback": "Traceback (most recent call last):\n  File \"tasks/sensor.py\", line 42, in sensor_read\n    data['temp'] = sensor.measure()[0]\nTypeError: 'NoneType' object is not callable\n",
      "file_path": "firmware/tasks/sensor.py",
      "line_number": 42,
      "driver_name": "SHT30",
      "error_type": "P0_driver_api",
      "attempt_number": 2,
      "previous_attempts": [
        {
          "attempt": 1,
          "strategy": "给 sensor.measure() 返回值加了 None 检查",
          "files_changed": ["firmware/tasks/sensor.py"],
          "result": "同样错误，无效"
        }
      ]
    }
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | string | 是 | `"fix"` |
| `manifest` | object | 是 | 完整 manifest |
| `error_context.traceback` | string | 是 | 原始 Python traceback |
| `error_context.file_path` | string | 是 | 报错文件路径 |
| `error_context.line_number` | number | 是 | 报错行号 |
| `error_context.driver_name` | string | 否 | 涉及的驱动名称 |
| `error_context.error_type` | string | 是 | autofix 分类：`P0_typo_import` / `P0_driver_api` / `P1_pin_addr` / `P1_wdt_mem` / `P2_sensor` / `P3_loop_no_output` / `unknown` |
| `error_context.attempt_number` | number | 是 | 当前是第几次尝试（1~3） |
| `error_context.previous_attempts` | array | 否 | 前几次尝试的策略和结果 |

---

## 三、Skill 输出 → 插件（S→P）

### full 模式消息序列

```
Phase 1: 下载驱动
  → status_update "正在搜索并下载驱动..."
  → [服务器内部] 运行 download_drivers.py（stdin manifest → stdout JSON）
  → [服务器内部] LLM 收到 JSON，得到所有驱动源码内容
  → file_operation(write) × N 将驱动文件写入插件端 firmware/lib/
  → status_update "✓ SSD1306 → upypi (ssd1306-driver v1.3.0)"
  → status_update "⚠ SHT30 → 未找到驱动"
  → status_update "✓ 2/3 驱动已下载，6 个文件"

Phase 2: 理解驱动 → 生成工厂 + Mock
  → status_update "正在阅读 SSD1306 驱动源码..."
  → [服务器内部] LLM 从 download_drivers.py 输出的 JSON 中读取驱动源码
  → [服务器内部] 生成 drivers/ssd1306_driver/__init__.py（工厂函数 + scan 函数）
  → [服务器内部] 生成 drivers/ssd1306_driver/mock.py（Mock 类）
  → file_operation(write) × 2 写入插件端
  → status_update "✓ SSD1306 工厂 + Mock 已生成"
  → （对每个器件重复）
  → status_update "✓ 3 个器件已完成 (工厂 + Mock)"

Phase 3: 生成 task 文件
  → status_update "正在生成 sensor_task.py..."
  → [服务器内部] LLM 根据 manifest.requirements + devices 生成任务代码
  → file_operation(write) × M
  → status_update "✓ sensor_task.py / display_task.py / alarm_task.py 已生成"

Phase 4: 补充 conf.py
  → file_operation(read) 获取当前 conf.py（scaffold 生成的版本）
  → [服务器内部] LLM 补充业务常量（阈值、校准值等）
  → file_operation(write) 覆盖 conf.py
  → status_update "✓ conf.py 已补充业务常量"

Phase 5: 生成 main.py（DI 装配）
  → file_operation(read) 获取当前 main.py（scaffold 生成的骨架）
  → [服务器内部] LLM 填充 DI 装配链 + task 注册 + 日志初始化
  → file_operation(write) 覆盖 main.py
  → status_update "✓ main.py DI 装配完成"

Phase 6: 生成测试文件
  → [服务器内部] LLM 生成 PC 端单元测试 + 设备端冒烟测试
  → file_operation(write) × 2~4
  → status_update "✓ test/pc/test_sensor.py / test/device/test_smoke.py"

Phase 7: 多层校验
  → script_run(flake8) → 不通过 → [内部] LLM 修复 → 重跑 → 通过
  → script_run(pylint) → 同上
  → script_run(check_mpy_imports.py) → 同上
  → script_run(check_dead_config.py) → 同上
  → script_run(check_skeleton_compliance.py) → 同上
  → status_update "✓ 5 项校验全部通过"

Phase 8: 终审
  → [服务器内部] LLM 最终审查（驱动 API 正确性、需求覆盖、测试覆盖、导入兼容性）

Phase 9: 输出
  → phase_complete（文件树 + 器件状态表 + manifest_content）
```

### fix 模式消息序列

```
Step 1: 读取当前文件
  → file_operation(read) × 1~3（读取报错文件 + 相关依赖文件）

Step 2: 分析修复
  → [服务器内部] LLM 读 traceback + 当前代码 + 历史尝试 → 设计修复策略

Step 3: 写入修复
  → file_operation(write) × 1~2（只写被修改的文件）
  → status_update "正在修复 tasks/sensor.py 第 42 行..."

Step 4: 校验
  → script_run(flake8) → script_run(pylint)
  → status_update "✓ lint 校验通过"

Step 5: 返回
  → phase_complete（code_diff + 修复摘要）
```

**fix 模式不发 approval_request。** 用户在 autofix 流程中，修复静默执行。

**fix 模式第一步必须 read。** 文件可能被上一轮 fix 改过，不能凭第一次全量生成时的记忆修改。

### 消息详情

#### status_update 列表

| step_id | message | level | 触发时机 |
|---------|---------|-------|---------|
| dl_start | 正在搜索并下载驱动... | info | Phase 1 开始 |
| dl_driver_ok | ✓ SSD1306 → upypi (ssd1306-driver v1.3.0) | success | 单个驱动下载成功 |
| dl_driver_warn | ⚠ SHT30 → 未找到驱动 | warn | 单个驱动下载失败 |
| dl_done | ✓ 2/3 驱动已下载，6 个文件 | success | Phase 1 完成 |
| factory_start | 正在阅读 SSD1306 驱动源码... | info | Phase 2 开始 |
| factory_ok | ✓ SSD1306 工厂 + Mock 已生成 | success | 单个器件完成 |
| factory_done | ✓ 3 个器件已完成 (工厂 + Mock) | success | Phase 2 完成 |
| task_gen | 正在生成 sensor_task.py... | info | Phase 3 |
| task_ok | ✓ sensor_task.py / display_task.py / alarm_task.py | success | Phase 3 完成 |
| conf_update | 正在补充 conf.py 业务常量... | info | Phase 4 |
| conf_ok | ✓ conf.py 已补充业务常量 | success | Phase 4 完成 |
| main_gen | 正在装配 main.py DI 链... | info | Phase 5 |
| main_ok | ✓ main.py DI 装配完成 | success | Phase 5 完成 |
| test_gen | 正在生成测试文件... | info | Phase 6 |
| test_ok | ✓ test/pc/ + test/device/ 已生成 | success | Phase 6 完成 |
| lint_start | 正在运行 flake8 校验... | info | Phase 7 开始 |
| lint_flake8_ok | ✓ flake8 通过 | success | 单项校验通过 |
| lint_flake8_fail | ✗ flake8 发现 N 个错误，正在修复... | warn | 校验失败，自动修复 |
| lint_pylint_ok | ✓ pylint 通过 | success | 同上 |
| lint_mpy_imports_ok | ✓ MPY 导入兼容性检查通过 | success | 同上 |
| lint_dead_config_ok | ✓ 死配置检测通过 | success | 同上 |
| lint_skeleton_ok | ✓ 骨架合规检查通过 | success | 同上 |
| lint_all_ok | ✓ 5 项校验全部通过 | success | Phase 7 完成 |
| review_done | ✓ 终审完成，无遗留问题 | success | Phase 8 完成 |
| fix_read | 正在读取 firmware/tasks/sensor.py... | info | fix 模式 Step 1 |
| fix_analyze | 正在分析错误原因... | info | fix 模式 Step 2 |
| fix_write | 正在修复 tasks/sensor.py 第 42 行... | info | fix 模式 Step 3 |
| fix_lint_ok | ✓ 修复后 lint 校验通过 | success | fix 模式 Step 4 |
| fix_done | ✓ 修复完成 | success | fix 模式 Step 5 |

#### script_run 校验链

5 个校验脚本按顺序执行。任一步失败 → LLM 读 errors 列表 → 修复 → 重跑该脚本。每个脚本超时 15 秒。

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "gen_lint_001",
    "interpreter": "python",
    "script": "check_skeleton_compliance.py",
    "args": ["--manifest", "-", "--project-dir", "{project_dir}"],
    "cwd": "{skill_dir}",
    "timeout_ms": 15000
  }
}
```

所有校验脚本统一输出格式：

```json
{
  "status": "pass",
  "errors": [
    {
      "file": "firmware/tasks/sensor.py",
      "line": 5,
      "message": "import logging 不在 MicroPython 白名单中",
      "severity": "error"
    }
  ],
  "warnings": [],
  "summary": "1 error, 0 warnings"
}
```

| 脚本 | 检查内容 | 退出码 |
|------|---------|--------|
| `flake8` | 代码风格 + 语法错误 | 非 0 = 有问题 |
| `pylint` | 代码质量（使用 .pylintrc 配置） | 非 0 = 有问题 |
| `check_mpy_imports.py` | 扫描所有 import，对照 63 个 MPY 白名单 | 非 0 = 有违规 |
| `check_dead_config.py` | conf.py 中定义的常量是否被引用 | 非 0 = 有死配置 |
| `check_skeleton_compliance.py` | 5 项骨架合规检查 | 非 0 = 有违规 |

#### file_operation — 驱动下载写入

`download_drivers.py` 在服务器端运行（利用服务器网络），输出 JSON 到 stdout。服务器解析后：

```json
{
  "type": "file_operation",
  "payload": {
    "op_id": "gen_dl_001",
    "op": "write",
    "path": "firmware/lib/ssd1306.py",
    "content": "# MicroPython SSD1306 OLED driver...\n...",
    "encoding": "utf-8"
  }
}
```

同时 LLM 直接从 JSON 中获取驱动源码内容进入 Phase 2，无需额外 `file_operation(read)`。

#### phase_complete — full 模式

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "generate",
    "result": "success",
    "summary": "代码生成完成：3 个驱动（2 个 upypi + 1 个冷硬件），4 个 task 文件，5 项校验全部通过",
    "next_phase": "deploy",
    "artifacts": [
      {
        "type": "table",
        "title": "器件驱动状态",
        "headers": ["器件", "类型", "驱动来源", "工厂", "Mock", "状态"],
        "rows": [
          ["SSD1306", "OLED", "upypi", "✓", "✓", "就绪"],
          ["SHT30", "温湿度", "none", "✓", "✓", "冷硬件路径"],
          ["蜂鸣器", "GPIO", "—", "✓", "✓", "标准 GPIO"]
        ]
      },
      {
        "type": "file_tree",
        "title": "生成文件",
        "tree": {
          "firmware": {
            "board.py": "file",
            "conf.py": "file (updated)",
            "boot.py": "file",
            "main.py": "file (updated)",
            "lib": { "ssd1306.py": "file", "ssd1306_README.md": "file", "..." : "..." },
            "drivers": {
              "ssd1306_driver": { "__init__.py": "file", "mock.py": "file" },
              "sht30_driver": { "__init__.py": "file", "mock.py": "file" },
              "buzzer_driver": { "__init__.py": "file", "mock.py": "file" }
            },
            "tasks": { "sensor_task.py": "file", "display_task.py": "file", "alarm_task.py": "file" }
          },
          "test": {
            "pc": { "test_sensor.py": "file", "test_alarm.py": "file" },
            "device": { "test_smoke.py": "file" }
          }
        }
      }
    ],
    "warnings": [
      "SHT30 走冷硬件路径，驱动函数体为空，需手动填充"
    ],
    "errors": [],
    "manifest_content": "{完整的更新后 project-manifest.json JSON 文本}"
  }
}
```

#### phase_complete — fix 模式

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "generate",
    "result": "success",
    "summary": "已修复 tasks/sensor.py 第 42 行：sensor.measure() 返回值增加 None 检查",
    "next_phase": null,
    "artifacts": [
      {
        "type": "code_diff",
        "title": "修改内容",
        "file_path": "firmware/tasks/sensor.py",
        "changes": [
          {
            "line_start": 41,
            "line_end": 43,
            "old_text": "    data['temp'] = sensor.measure()[0]\n    data['hum'] = sensor.measure()[1]",
            "new_text": "    result = sensor.measure()\n    if result is not None:\n        data['temp'] = result[0]\n        data['hum'] = result[1]"
          }
        ]
      }
    ],
    "warnings": [],
    "errors": []
  }
}
```

**code_diff artifact 结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | `"code_diff"` |
| `title` | string | diff 标题 |
| `file_path` | string | 被修改的文件路径 |
| `changes[].line_start` | number | 修改起始行号 |
| `changes[].line_end` | number | 修改结束行号 |
| `changes[].old_text` | string | 修改前代码 |
| `changes[].new_text` | string | 修改后代码 |

**fix 模式不返回 manifest_content。** 修复不改变 manifest 结构，autofix 自行更新 `updated_at` 即可。

---

## 四、SKILL.md 修改点

共 11 处改动：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 前置检查 | `python --version` + requests/flake8/pylint import 检查 | 删除 | 服务器环境保证 |
| 2 | Phase 1 | `python download_drivers.py --project-dir {dir}` 写本地磁盘 | `python download_drivers.py --manifest - < manifest.json` stdin 进，stdout 出 JSON。服务器解析后发 file_operation(write) 给插件 | 服务器不写本地磁盘 |
| 3 | Phase 1A 换行符修复 | 一大段内联 Python（30 行 Bash heredoc） | 逻辑内置到 download_drivers.py，下载完自动修复，不单独成步骤 | 简化流程 |
| 4 | Phase 2A | LLM 读 `firmware/lib/<driver>.py` 文件 | LLM 从 download_drivers.py 的 stdout JSON 中直接读取驱动源码 | 省去 file_operation(read) 来回 |
| 5 | Phase 2B | 修改自建 I2C 的驱动 `lib/<driver>.py` | 改完后发 file_operation(write) 覆盖插件端对应文件 | 服务器改过的内容要同步到插件端 |
| 6 | Phase 3~6 | 生成文件 → 隐式写磁盘 | 每个生成的文件发 file_operation(write) 到插件端 | 文件在插件端 |
| 7 | Phase 7A flake8 | `subprocess.run(flake8)` | `script_run(flake8)` | 文件在插件端，lint 也要在插件端跑 |
| 8 | Phase 7B pylint | `subprocess.run(pylint)` | `script_run(pylint)` | 同上 |
| 9 | Phase 7C MPY 导入检查 | `find` + `grep` + LLM 手动分析 | `script_run(check_mpy_imports.py)` 确定性校验 | LLM 枚举不可靠，脚本 100% 可靠 |
| 10 | Phase 7D 死配置检测 | `python -c "..."` 内联提取 + grep | `script_run(check_dead_config.py)` 确定性校验 | 同上 |
| 11 | 新增 fix 模式 | 无 | 接收 `mode="fix"` + `error_context`，先 `file_operation(read)` 读出错文件 → LLM 最小化修改 → `file_operation(write)` 写回 → lint → 返回 code_diff | autofix 重入 |

---

## 五、校验脚本改动

### 5.1 download_drivers.py（改）

**路径：** `G:\MicroPython_Skills\upy-generate\scripts\download_drivers.py`

| 改动 | 内容 |
|------|------|
| 输入方式 | `--project-dir` 改为 `--manifest -`（从 stdin 读 manifest JSON） |
| 输出方式 | 不再写磁盘。stdout 输出 JSON（见下方格式），stderr 保留日志 |
| 换行符修复 | 内置化：下载完每个文件后自动 compile 检查 + 修复 `\r\r\n` |
| manifest 写入 | 移除第 243-248 行的 manifest 更新逻辑（由 Phase 9 统一处理） |

**stdout JSON 格式（固定）：**

```json
{
  "drivers": [
    {
      "device_name": "SSD1306",
      "source": "upypi",
      "package_name": "ssd1306-driver",
      "version": "1.3.0",
      "files": [
        {"path": "firmware/lib/ssd1306.py", "content": "源码...", "encoding": "utf-8"},
        {"path": "firmware/lib/ssd1306_README.md", "content": "文档...", "encoding": "utf-8"},
        {"path": "firmware/lib/ssd1306_example.py", "content": "示例...", "encoding": "utf-8"}
      ]
    }
  ],
  "errors": [
    {"device_name": "SHT30", "source": "upypi", "reason": "HTTP 404", "fallback": "none"}
  ],
  "summary": "Downloaded 2/3 drivers, 6 files total"
}
```

### 5.2 check_mpy_imports.py（新增）

**路径：** `G:\MicroPython_Skills\upy-generate\scripts\check_mpy_imports.py`

替代当前 Phase 7C 的 `find` + `grep` 手动流程。

**检查逻辑：**
1. 扫描 `firmware/` 下所有 `.py` 文件（排除 `firmware/lib/`）
2. 提取 `import X` 和 `from X import Y` 中的顶层模块名 X
3. 对照 63 个 MicroPython 白名单
4. 不在白名单但 firmware/ 下有同名 `.py` 文件 → 报 error：应改为相对导入
5. 不在白名单且 firmware/ 下无 → 报 warning：可能不支持

```bash
python check_mpy_imports.py --project-dir {project_dir}
# stdout → {"status": "pass", "errors": [], "warnings": [], "summary": "..."}
# exit: 0=pass, 1=fail
```

### 5.3 check_dead_config.py（新增）

**路径：** `G:\MicroPython_Skills\upy-generate\scripts\check_dead_config.py`

替代当前 Phase 7D 的内联 Python + grep。

**检查逻辑：**
1. 提取 `conf.py` 中所有 `UPPER_CASE = value` 常量名
2. 扫描 `firmware/` + `test/` 下所有 `.py` 文件（排除 `conf.py` 自身和 `firmware/lib/`）
3. 检查每个常量是否被引用（`from conf import X` 或 `conf.X`）
4. 未引用 → 死配置，报 warning

```bash
python check_dead_config.py --project-dir {project_dir}
# stdout → {"status": "pass", "errors": [], "warnings": [...], "summary": "..."}
```

### 5.4 check_skeleton_compliance.py（新增）

**路径：** `G:\MicroPython_Skills\upy-generate\scripts\check_skeleton_compliance.py`

确保 upy-generate 生成的代码遵守了 upy-scaffold 设定的骨架。

**五项检查：**

| # | 检查项 | 规则 |
|---|--------|------|
| 1 | 调度器模式一致性 | main.py 的调度方式（Timer/asyncio/_thread）与 `manifest.scaffold_mode` 一致 |
| 2 | board.py 引脚引用 | GPIO 号必须来自 `from board import` 而非硬编码 `Pin(4)`（main.py 除外） |
| 3 | conf.py 常量引用 | 阈值/间隔等数值必须 `from conf import` 而非硬编码（main.py 除外） |
| 4 | DI 链路完整 | main.py 中驱动创建必须经过 `drivers/*/__init__.py` 工厂函数 |
| 5 | 不直接 import machine | tasks/*.py 不出现 `import machine` 或 `from machine import` |

```bash
python check_skeleton_compliance.py --project-dir {project_dir} --manifest - < manifest.json
# stdout → {"status": "pass", "errors": [], "warnings": [], "summary": "..."}
```

### 5.5 两阶段 file_operation(read)（fix 模式特有）

fix 模式下，LLM 需要先读取出错文件的当前内容。如果错误涉及多个文件（如 sensor.py 调用了一个改了签名的函数），需要读取多个文件。

LLM 自主决定读哪些文件，但**至少**要读 `error_context.file_path` 指向的文件。

---

## 六、插件端需要实现的 UI 组件

| 组件 | 对应消息 | 关键功能 |
|------|---------|---------|
| 进度时间线 | status_update × 20+ | 全流程最密集的时间线（下载→工厂→生成→测试→校验），复用已有组件 |
| 文件写入进度 | file_operation × 20+ | 骨架生成后第二次大量文件写入。与 scaffold 阶段复用同一组件 |
| 校验状态面板 | script_run × 5 | 串行显示 5 个校验脚本的进行/通过/失败状态 |
| 代码 diff 视图 | phase_complete (code_diff) | **新组件**：fix 模式展示修改前后对比，绿色新增/红色删除 |
| 结果面板 | phase_complete (full) | 器件状态表 + 文件树 + 警告信息 |

### code_diff 渲染规范

插件收到 `type: "code_diff"` artifact 时，渲染为 diff 视图：

```
┌─ 修改内容 — firmware/tasks/sensor.py ─┐
│                                        │
│  -    data['temp'] = sensor.measure()[0]│
│  -    data['hum'] = sensor.measure()[1]│
│  +    result = sensor.measure()        │
│  +    if result is not None:           │
│  +        data['temp'] = result[0]     │
│  +        data['hum'] = result[1]      │
│                                        │
└────────────────────────────────────────┘
```

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发送 status_update 序列（20 条）→ 验证长时间线滚动、折叠
2. 手动构造 phase_complete（含 file_tree + table）→ 验证文件树 + 表格
3. 手动构造 phase_complete（fix 模式，含 code_diff）→ **重点测试 diff 视图**：
   - 单行修改
   - 多行修改
   - 新增代码块
4. 手动发 script_run × 5 序列 → 验证校验面板逐一更新

### Skill 端测试（无插件）

1. **full 模式完整流程：**
   - mock_plugin 发送 start_phase（mode=full, manifest=温湿度项目，phase: scaffold）
   - 自动验证：download_drivers.py stdout JSON schema 正确
   - 自动验证：生成的工厂/Mock 方法签名与驱动源码一致
   - 自动验证：5 个校验脚本全部 pass
   - 检查所有 file_operation content 是合法 Python
2. **fix 模式：**
   - 先通过 full 模式生成完整项目
   - mock_plugin 发送 start_phase（mode=fix, error_context={traceback, file_path, ...}）
   - 验证先发了 file_operation(read)
   - 验证只发了被修改文件的 file_operation(write)，未改其他文件
   - 验证 phase_complete 包含 code_diff artifact
3. **fix 模式重复调用（模拟 autofix 3 次重入）：**
   - 第一次 fix → 改 sensor.py
   - 第二次 fix（同一错误）→ 先 read sensor.py → 发现已有 None 检查 → 换策略 → 改 main.py
   - 第三次 fix → 验证 LLM 正确使用了 previous_attempts 信息
4. **download_drivers.py 换行符修复：**
   - 构造一个含 `\r\r\n` 的假驱动文件（mock HTTP 返回）
   - 验证下载后 Python compile 通过
5. **校验脚本边界用例：**
   - check_mpy_imports.py：含 `import typing` 的文件 → 预期 fail
   - check_dead_config.py：conf.py 定义了 5 个常量，只用了 3 个 → 预期 fail
   - check_skeleton_compliance.py：tasks/sensor.py 硬编码了 GPIO4 → 预期 fail
