# upy-deploy 接口定义

> 状态：✅ 已定稿
>
> Phase 5 — 一键烧录运行。编译 .py→.mpy、上传 firmware/、软复位、持久会话采集 REPL 输出、抓取设备日志、判定 PASS/FAIL。FAIL 时构造 error_context 传给 upy-autofix。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | deploy |
| 上游 Skill | upy-generate 或 upy-simulate（用户手动触发）；upy-autofix（incremental 模式自动触发） |
| 下游 Skill | upy-autofix（FAIL 时）；upy-wiring / upy-diagram（PASS 时并行生成可视化） |
| 一句话职责 | 编译上传 → 软复位 → 运行采集 → 日志抓取 → LLM 判定 PASS/FAIL |

**两种运行模式：**

| 模式 | 触发方 | 用途 |
|------|--------|------|
| `full` | 用户点击 [一键烧录] 按钮 | 全新编译+全量上传+运行 |
| `incremental` | upy-autofix 修复后自动调用 | 仅编译上传 changed_files，然后运行验证 |

**核心约束：**
- 所有 mpremote 操作经 `device_command` / `script_run` 由插件执行，服务端不接触串口
- Phase 6 判定由服务端 LLM 完成（替代原 grep 规则）
- `flash_device.py` + `read_device_log.py` 需支持 `--json` 标志输出结构化数据
- main.py 最后上传，且保留 .py 不编译

---

## 二、插件输入 → Skill（P→S）

### Full 模式（用户手动触发）

```json
{
  "type": "start_phase",
  "phase": "deploy",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "full",
    "com_port": "COM3",
    "manifest": { /* 完整的 project-manifest.json */ },
    "previous_error": null
  }
}
```

### Incremental 模式（autofix 自动触发）

```json
{
  "type": "start_phase",
  "phase": "deploy",
  "session_id": "uuid-xxx",
  "payload": {
    "mode": "incremental",
    "com_port": "COM3",
    "manifest": { /* 完整的 project-manifest.json */ },
    "changed_files": [
      "firmware/tasks/sensor_task.py",
      "firmware/drivers/sht30/mock.py"
    ],
    "previous_error": {
      "error_type": "RuntimeError",
      "traceback": "Traceback (most recent call last):\n  File \"main.py\", line 42...",
      "failed_phase": "deploy",
      "failed_at": "Phase 4: REPL 捕获到 NameError"
    }
  }
}
```

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `mode` | string | 是 | 插件 | `"full"` / `"incremental"` |
| `com_port` | string | 是 | 插件串口选择器 | 如 COM3、/dev/ttyACM0 |
| `manifest` | object | 是 | upy-generate 输出 | 完整 project-manifest.json |
| `changed_files` | string[] | mode=incremental 时必填 | upy-autofix | autofix 修改过的文件列表，仅编译上传这些 |
| `previous_error` | object? | 否 | upy-autofix | 上次 deploy 失败的错误上下文，LLM 可据此调整策略 |

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
Phase 1: 编译 + 上传 + 校验
  → status_update "正在编译 .py → .mpy... (N 文件)"
  → script_run(flash_device.py --port COM3 --compile --upload --verify --no-reset --json)
  → stream × N (script_stdout, 每文件一行 JSON)
  → script_result
  → status_update "✓ 编译上传完成：15 .mpy + 5 .py，校验通过"

Phase 2: 软复位 + 等待重连
  → status_update "正在软复位设备..."
  → device_command(action="soft_reset")
  → device_result (插件内部完成重连等待，含重连耗时)
  → status_update "✓ 设备已就绪（重连耗时 2.3s）"

Phase 3: 持久会话采集
  → status_update "正在采集设备输出... (60s 超时)"
  → device_command(action="stream", timeout_ms=60000)
  → stream × N (device_output, 实时 REPL 输出行)
  → device_result (采集完成，含完整输出文本)
  → status_update "✓ 采集完成：共 342 行输出"

Phase 4: 抓取设备日志
  → status_update "正在读取设备日志..."
  → script_run(read_device_log.py --port COM3 --log-dir /log --json)
  → script_result (stdout = JSON 格式的日志内容)
  → status_update "✓ 已读取 2 个日志文件"

Phase 5: LLM 判定
  → status_update "正在分析运行结果..."
  → phase_complete (PASS/FAIL + error_context)
```

### 消息详情

#### script_run — flash_device.py（Phase 1）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "deploy_flash",
    "interpreter": "python",
    "script": "tools/flash_device.py",
    "args": ["--port", "COM3", "--compile", "--upload", "--verify", "--no-reset", "--json"],
    "cwd": "{project_dir}",
    "timeout_ms": 120000
  }
}
```

**`--json` 输出格式（stdout 每行一条 JSON）：**

```
{"step": "scan", "total": 20, "entry_files": ["main.py", "boot.py"]}
{"step": "compile", "file": "tasks/sensor_task.py", "status": "ok", "size": 1536}
{"step": "compile", "file": "tasks/display_task.py", "status": "ok", "size": 2048}
{"step": "compile", "file": "drivers/sht30/sht30.py", "status": "skip", "reason": "entry_file"}
{"step": "upload", "file": "lib/scheduler.mpy", "status": "ok", "size_kb": 2.1, "progress": "1/18"}
{"step": "upload", "file": "main.py", "status": "ok", "size_kb": 1.5, "progress": "18/18", "note": "entry_last"}
{"step": "verify", "remote_total": 20, "local_total": 20, "missing": [], "status": "ok"}
{"step": "done", "status": "success", "compiled": 15, "uploaded": 20, "errors": []}
```

服务端 LLM 解析每行 JSON，将 compile/upload 进度转为 `status_update`。

#### device_command — soft_reset（Phase 2）

```json
{
  "type": "device_command",
  "payload": {
    "cmd_id": "deploy_reset",
    "action": "soft_reset",
    "timeout_ms": 60000
  }
}
```

**插件端行为（非简单透传）：**
1. 执行 `mpremote connect <com> soft-reset`
2. 进入重连等待循环（每 2s 发 `resume exec "print(1)"` 轮询）
3. 若 COM 口变化（Windows），自动 `mpremote connect list` 重新扫描
4. 收到 `"1"` → 设备就绪 → 返回 success
5. 60s 超时 → 返回 failure

```json
{
  "type": "device_result",
  "payload": {
    "cmd_id": "deploy_reset",
    "success": true,
    "stdout": "设备就绪 (COM3, 重连耗时 2.3s)",
    "stderr": "",
    "exit_code": 0
  }
}
```

#### device_command — stream（Phase 3）

```json
{
  "type": "device_command",
  "payload": {
    "cmd_id": "deploy_repl",
    "action": "stream",
    "timeout_ms": 60000,
    "expect_output": true
  }
}
```

**插件端行为：**
1. 打开 `mpremote connect <com> repl` 持久会话
2. 每收到一行输出 → 发一条 `stream` 消息（`stream_type: "device_output"`）
3. 检测到 `"starting scheduler"` 或等效标志 → 提前终止（early_exit=true）
4. 60s 超时 → 关闭会话
5. 发送 `device_result`（含完整输出文本供 LLM 分析）

```
stream 消息示例:
  chunk_index=0:  "MPY: soft-reboot\n"
  chunk_index=1:  "I2C scan: [0x3C, 0x44]\n"
  chunk_index=2:  "[INFO] starting scheduler\n"
  ...
  chunk_index=341: "[INFO] tick 60 complete\n"
  → device_result(success=true, stdout=<完整文本>)
```

#### script_run — read_device_log.py（Phase 4）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "deploy_read_log",
    "interpreter": "python",
    "script": "tools/read_device_log.py",
    "args": ["--port", "COM3", "--log-dir", "/log", "--json"],
    "cwd": "{project_dir}",
    "timeout_ms": 30000
  }
}
```

**`--json` 输出格式（stdout）：**

```json
{
  "status": "ok",
  "log_dir": "/log",
  "logs": [
    {
      "name": "run_0.log",
      "size_bytes": 2048,
      "content": "2026-06-17T10:30:00Z [INFO] boot complete\n..."
    },
    {
      "name": "run_1.log",
      "size_bytes": 512,
      "content": "..."
    }
  ],
  "errors": []
}
```

当设备端无日志文件时：`{"status": "empty", "log_dir": "/log", "logs": [], "errors": []}`

#### phase_complete（Phase 5 — LLM 判定）

**PASS 示例：**

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "deploy",
    "result": "success",
    "summary": "部署成功：设备运行 60s 无异常，scheduler 正常调度 3 个任务",
    "next_phase": null,
    "artifacts": [
      {
        "type": "markdown",
        "title": "运行摘要",
        "content": "### 设备运行报告\n\n- **设备**: ESP32-WROOM-32 @ COM3\n- **采样**: 60 ticks × 1000ms = 60s\n- **I2C 扫描**: [0x3C (SSD1306), 0x44 (SHT30)]\n- **任务**: sensor_task (每 tick), display_task (每 5 tick), alarm_task (每 tick)\n- **日志**: run_0.log (2048 bytes)\n- **异常**: 无"
      },
      {
        "type": "table",
        "title": "部署阶段",
        "headers": ["阶段", "状态", "说明"],
        "rows": [
          ["编译", "✓", "15 .py → .mpy"],
          ["上传", "✓", "20 文件，0 失败"],
          ["校验", "✓", "20/20 文件一致"],
          ["复位", "✓", "COM3 重连 2.3s"],
          ["运行", "✓", "60s 无异常"]
        ]
      }
    ],
    "warnings": [],
    "errors": [],
    "error_context": null
  }
}
```

**FAIL 示例：**

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "deploy",
    "result": "failed",
    "summary": "部署失败：设备运行至 tick 12 时 SHT30 抛出 OSError",
    "next_phase": "autofix",
    "artifacts": [
      {
        "type": "markdown",
        "title": "错误摘要",
        "content": "### 错误信息\n\n- **类型**: OSError\n- **位置**: firmware/tasks/sensor_task.py:23 — sht30.measure()\n- **发生时刻**: tick 12 (设备启动后 ~15s)\n- **日志**: run_0.log 含完整 Traceback"
      }
    ],
    "warnings": [],
    "errors": ["OSError: I2C read failed at tick 12"],
    "error_context": {
      "phase": "deploy",
      "error_type": "OSError",
      "file_path": "firmware/tasks/sensor_task.py",
      "line_number": 23,
      "traceback": "Traceback (most recent call last):\n  File \"main.py\", line 42, in sensor_cb\n  File \"tasks/sensor_task.py\", line 23, in sensor_read\nOSError: I2C read failed",
      "repl_output": "<完整 REPL 输出文本>",
      "log_files": {
        "run_0.log": "<日志文件内容>"
      },
      "log_report": {
        "error_count": 1,
        "errors": [
          { "level": "P0_TRACEBACK", "message": "OSError: I2C read failed", "line": 42 }
        ]
      },
      "device_info": {
        "com_port": "COM3",
        "i2c_scan": "[0x3C, 0x44]",
        "firmware": "MicroPython v1.24.1"
      }
    }
  }
}
```

**error_context 传给 upy-autofix：** autofix 收到 `error_context` 后提取 `traceback` + `file_path` + `line_number` 作为入口，`repl_output` + `log_report` 作为辅助上下文。

#### status_update 列表

| step_id | level | message | 触发时机 |
|---------|-------|---------|---------|
| compile_start | info | 正在编译 .py → .mpy... | Phase 1 开始 |
| compile_progress | info | 编译中: sensor_task.py → sensor_task.mpy (15/15) | 每文件编译完成 |
| compile_done | success | ✓ 编译完成：15 .mpy，0 失败 | 编译阶段结束 |
| upload_start | info | 正在上传 firmware/ → 设备... | 上传阶段开始 |
| upload_progress | info | 上传中: lib/scheduler.mpy (1/20) | 每文件上传完成 |
| upload_done | success | ✓ 上传完成：20 文件 | 上传阶段结束 |
| verify_start | info | 正在校验文件完整性... | 校验阶段开始 |
| verify_done | success | ✓ 校验通过：20/20 文件一致 | 校验通过 |
| verify_fail | warn | ⚠ 缺失 2 文件，正在重传... | 校验不通过 |
| reset_start | info | 正在软复位设备... | Phase 2 开始 |
| reset_done | success | ✓ 设备已就绪（重连耗时 X.Xs） | 设备就绪 |
| reset_timeout | error | ✗ 设备重连超时 (60s) | 重连超时 |
| stream_start | info | 正在采集设备输出 (60s)... | Phase 3 开始 |
| stream_done | success | ✓ 采集完成：XXX 行输出 | 采集结束 |
| stream_early | success | ✓ scheduler 已启动，提前结束采集 | 检测到 starting scheduler |
| log_start | info | 正在读取设备日志... | Phase 4 开始 |
| log_done | success | ✓ 已读取 N 个日志文件 | 日志读取完成 |
| log_empty | info | 设备端无日志文件 | 无日志 |
| judge_start | info | 正在分析运行结果... | Phase 5 开始 |
| judge_pass | success | ✓ 部署成功：设备运行正常 | PASS |
| judge_fail | error | ✗ 部署失败：[错误类型] | FAIL |

### 无需 approval_request

deploy 全程无人机交互卡片。用户只需点击 [一键烧录] 按钮启动，后续自动执行。

---

## 四、SKILL.md 修改点

共 8 处改动：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 前置检查 | `python --version` + `mpremote --version` | 删除。依赖由插件环境保证 | 服务端不感知运行环境 |
| 2 | Phase 1 上传 | 直接调用 `mpremote fs cp/mkdir` 或 `python flash_device.py` | `script_run(flash_device.py --json --verify)` | 脚本由插件本地执行，JSON 输出供服务端解析 |
| 3 | Phase 2 校验 | 独立步骤：`mpremote fs tree/ls` + Bash 对比 | 合并到 Phase 1：`flash_device.py --verify` 上传后自动校验，缺文件自动重传 | 减少一次 script_run 往返 |
| 4 | Phase 3 软复位 | `mpremote soft-reset` + Python 轮询 `exec("print(1)")` | `device_command(action="soft_reset")`，插件内部完成整个重连等待循环，返回成功/超时 | 插件封装重连逻辑，服务端只关心结果 |
| 5 | Phase 4 持久会话 | subprocess.Popen + threading 代码（pipe/PTY） | `device_command(action="stream", timeout_ms=60000)` → `stream` 消息逐行推送 | stream 消息复用，插件端建立 REPL 会话 |
| 6 | Phase 5 抓日志 | `mpremote fs cat/cp` + `log_report.py` | `script_run(read_device_log.py --json)` 一次返回全部日志内容（JSON）；服务端可再调 `script_run(log_report.py)` 做结构化解析 | 减少多轮 mpremote 调用，一次取回 |
| 7 | Phase 6 初判 | grep 规则本地判定（Traceback/rst cause/MemoryError） | 服务端 LLM 综合分析 REPL 输出 + log_report JSON → 判定 PASS/FAIL | LLM 有全量项目上下文，判定更准确；能区分预期 warning vs 真实 error |
| 8 | 新增 incremental 模式 | 仅 full 模式 | 新增 `mode=incremental`：读取 `changed_files` → 仅编译上传这些文件 → flash_device.py 用 `--files` 参数 | autofix→deploy 快速验证闭环，无需全量重传 |

---

## 五、校验脚本改动

### flash_device.py

**路径：** `G:\MicroPython_Skills\upy-scaffold\templates\pc\flash_device.py`

| 改动 | 内容 |
|------|------|
| 新增 `--json` 标志 | 每步输出一行 JSON 到 stdout（step/status/file/size 等），替代当前 `print("[compile] ...")` 人类可读格式。不带 `--json` 时保持原输出 |
| 新增 `--verify` 标志 | 上传完成后自动 `fs ls` 遍历远程目录，对比本地文件列表，输出 `{"step":"verify", "missing":[...], "status":"ok"/"fail"}`。缺文件时自动重传 |
| 新增 `--files` 参数 | 值 `"tasks/sensor.py,drivers/sht30/sht30.py"`（逗号分隔相对路径）。指定后仅编译/上传这些文件（incremental 模式）。**入口文件始终保留 .py 不编译** |
| 移除 `select_com_port()` | 交互式 COM 口选择 → 由 `--port` 参数传入（插件端已在 start_phase 提供）。无 `--port` 时报错退出 |
| 移除 `--flash` 固件烧录 | 固件烧录属于一次性操作，不在 deploy 流程中执行。参数保留但 deploy 不使用 |
| `_upload_dir` 排序保证 | main.py 始终最后一个上传（已有逻辑，确保不退化） |

**`--json` 输出行类型规范：**

| step | 字段 | 说明 |
|------|------|------|
| `scan` | `total`, `entry_files` | 扫描结果：文件总数 + 入口文件列表（不编译） |
| `compile` | `file`, `status`, `size?`, `error?` | status: ok / skip(入口文件) / fail |
| `upload` | `file`, `status`, `size_kb`, `progress`, `note?` | progress: "N/M"；note: entry_last 表 main.py 最后上传 |
| `verify` | `remote_total`, `local_total`, `missing`, `status` | 校验结果 |
| `done` | `status`, `compiled`, `uploaded`, `errors` | 最终摘要 |

### read_device_log.py

**路径：** `G:\MicroPython_Skills\upy-scaffold\templates\pc\read_device_log.py`

| 改动 | 内容 |
|------|------|
| 新增 `--json` 标志 | 输出结构化 JSON 到 stdout（`{status, log_dir, logs[{name, size_bytes, content}], errors[]}`），替代当前原始文本输出。不带 `--json` 时保持原输出 |
| 移除 `--tail` / `--clear` | deploy 流程不使用这些功能。参数保留但 deploy 不调用 |

### log_report.py

**路径：** `G:\MicroPython_Skills\upy-scaffold\templates\pc\log_report.py`

**基本不需要改。** 已输出结构化 JSON，与 error_context 兼容。确认 `parse_log()` 的 error level 枚举与 error_context 一致即可。

### run_on_device.py（与 gen-driver 共用）

**路径：** `G:\MicroPython_Skills\upy-deploy\scripts\run_on_device.py`（新建）

**用途：** 通过 mpremote 将 .py 文件送入设备 REPL 执行，捕获 stdout/stderr 到日志文件。gen-driver 的 Step 3 验证循环和 Step 7 独立测试使用；deploy 的 Phase 3 REPL 快测也可复用。

| 参数 | 说明 |
|------|------|
| `--com` | COM 端口号 |
| `--file` | 要执行的 .py 文件路径（相对于项目目录） |
| `--capture` | 启用输出捕获（写入 logs/ 目录） |
| `--timeout-ms` | 设备执行超时 (ms)，默认 30000 |
| `--json-summary` | stdout 输出 `{"status":"ok","output_file":"...","exit_code":0,"duration_ms":N}` |

与 `flash_device.py` 的区别：`flash_device.py` 负责编译+上传+校验（完整部署），`run_on_device.py` 负责 REPL 送入执行+捕获输出（快速验证）。

---

## 六、插件端需要实现的 UI 组件

| 组件 | 对应消息 | 关键功能 |
|------|---------|---------|
| 部署进度时间线 | status_update × 10~15 | 编译→上传→校验→复位→运行→日志→判定 七阶段 |
| 设备终端面板 | stream（device_output） | **复用 simulate 的终端面板**，实时显示 REPL 输出行 |
| 部署结果面板 | phase_complete | PASS：运行摘要 markdown + 阶段表格；FAIL：错误摘要 + error_context 预览 |
| [一键烧录] 按钮 | 触发 start_phase(mode="full") | generate/simulate 完成后启用 |
| [重新烧录] 按钮 | 触发 start_phase(mode="full") | FAIL 后替换"一键烧录"按钮 |

### 设备终端面板说明

与 simulate 的终端面板共用同一 UI 组件，区别在于数据源：
- simulate：`stream` 消息 `stream_type: "script_stdout"`（sim_main.py --plain 输出）
- deploy：`stream` 消息 `stream_type: "device_output"`（REPL 实时输出）

插件收到 stream 消息后实时追加到终端面板。支持暂停滚动、复制文本、清空。

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发 `status_update` 序列 → 验证七阶段时间线渲染
2. 手动发 `stream` 序列（模拟 REPL 输出行）→ 验证终端面板实时滚动
3. 手动发 `phase_complete` (PASS) → 验证运行摘要 + 阶段表格渲染
4. 手动发 `phase_complete` (FAIL + error_context) → 验证错误摘要面板 + autofix 入口
5. 构造 `start_phase` 消息 → 验证 [一键烧录] 按钮点击后发出正确 JSON

### Skill 端测试（无插件）

1. 用 mock_plugin.py 模拟：
   - `script_run(flash_device.py)` → 返回模拟 JSON 行输出
   - `device_command(action="soft_reset")` → 返回成功
   - `device_command(action="stream")` → 返回模拟 REPL 输出（含/不含 Traceback）
   - `script_run(read_device_log.py)` → 返回模拟日志 JSON
2. 验证 PASS 路径：正常 REPL 输出 + 无错误日志 → result="success"
3. 验证 FAIL 路径：REPL 含 Traceback → result="failed" + error_context 完整
4. 验证 incremental 模式：changed_files 传入 → flash_device.py 仅处理指定文件
5. 检查所有发出的消息 JSON 符合 02-protocol.md Schema
