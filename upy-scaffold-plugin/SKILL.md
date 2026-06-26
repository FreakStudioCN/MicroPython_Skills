---
name: upy-scaffold-plugin
description: 插件化工作流版 MicroPython 项目骨架生成。用于 Codex 收到 next_phase=upy-scaffold-plugin 的 phase_complete(upy-flash-mpy-firmware-plugin) 或用户在后续阶段新增器件时；消费 select-hw manifest_content，审批调度模式和模块后生成 file_operation 写入的 firmware/ 骨架，或 incremental 只生成新器件 driver stub。
---

# upy-scaffold-plugin 插件化工作流

`upy-scaffold-plugin` 是第三阶段项目骨架生成的插件化版本。它只搭 `firmware/`、`tools/`、`.upy/` 等工程骨架，不写业务 task、不填驱动实现、不做同步/异步驱动转换；这些留给 `upy-generate-plugin`。

上游正式链路是：

```
upy-analyze-plugin -> upy-select-hw-plugin -> upy-flash-mpy-firmware-plugin -> upy-scaffold-plugin -> upy-generate-plugin
```

输入事实必须来自 `select-hw` 的 `manifest_content`。当启动消息来自 `upy-flash-mpy-firmware-plugin` 时，优先读 `payload.manifest_content`；若缺失，则按 `payload.source_phase_complete` 或 `payload.source_phase_complete_path` 追溯到 `phase_complete.select_hw.json.payload.manifest_content`。不要从日志、旧草稿或对话记忆推断硬件事实。

## 启动消息

full 模式：

```json
{
  "type": "start_phase",
  "phase": "upy-scaffold-plugin",
  "payload": {
    "mode": "full",
    "source_phase": "upy-flash-mpy-firmware-plugin",
    "source_phase_complete_path": "sessions/<session_id>/phase_complete.upy_flash_mpy_firmware_plugin.json",
    "runtime_context": {
      "artifact_root": ".",
      "artifact_root_mode": "cwd",
      "session_root": "sessions/<session_id>",
      "project_root": "sessions/<session_id>/project",
      "resource_root": "<runtime-provided>"
    },
    "capabilities": {
      "approval_request": true,
      "script_run": true,
      "file_operation": true
    }
  }
}
```

incremental 模式：

```json
{
  "type": "start_phase",
  "phase": "upy-scaffold-plugin",
  "payload": {
    "mode": "incremental",
    "manifest": { "phase": "scaffold" },
    "new_devices": [{ "name": "DHT22", "driver": { "source": "upypi" } }]
  }
}
```

## full 流程

1. 校验上游阶段：`phase_complete(upy-flash-mpy-firmware-plugin)` 必须是 `result=success` 且 `next_phase=upy-scaffold-plugin`。迁移期直测可直接传 `select-hw` manifest，但正式链路不要跳过固件阶段。
2. 从 `manifest_content` 读取 `mcu`、`devices`、`pinout`、`bom`、`requirements`。
3. 发送 `approval_request(scaffold_config)`，把调度模式、额外模块和自定义文件合并到一张卡片。
4. 用户确认后运行 `scripts/init_scaffold.py` 生成 stdout JSON。
5. 将 stdout JSON 的 `directories[]` 用于插件端预建目录，将 `files[]` 逐条转成 `file_operation(op=write)`。
6. 发送 `script_run(flake8)`，由宿主在项目目录运行 lint；脚本自身不运行 flake8。
7. 宿主把 `file_operations[]` 写入项目目录后，运行 `python -m flake8 firmware tools`；必须使用项目根 `.flake8` 的 MicroPython-aware 配置，返回 0 才能继续。
8. 输出 `phase_complete(result=success, next_phase=upy-generate-plugin)`，并在 `payload.manifest_content` 中带回脚本输出的更新后 manifest。

## approval_request: scaffold_config

只发一个审批请求，`approval_id` 固定为 `scaffold_config`。必须包含 `item_groups`：

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "scaffold_config",
    "header": "项目骨架配置",
    "question": "选择调度模式和需要注入的模块",
    "items": [
      {"id": "mode_timer", "name": "Timer tick", "group": "scheduler_mode"},
      {"id": "mode_async", "name": "asyncio", "group": "scheduler_mode"},
      {"id": "mode_thread", "name": "_thread", "group": "scheduler_mode"},
      {"id": "module_logger", "name": "日志系统", "group": "extra_modules"},
      {"id": "module_flash", "name": "部署工具", "group": "extra_modules"}
    ],
    "allow_add": true,
    "item_groups": {
      "scheduler_mode": {"multi_select": false, "label": "调度模式"},
      "extra_modules": {"multi_select": true, "label": "额外模块"}
    }
  }
}
```

调度模式推荐规则只影响 `selected/meta`，不能限制用户选择：

| 条件 | 推荐 |
|---|---|
| `requirements.network == "wifi"` | `mode_async` |
| display/LCD/LVGL 相关器件或 `special_requirements` 含 lcd/lvgl/display | `mode_async` |
| 其他 | `mode_timer` |

模块 id 映射到脚本 `--modules`：

| id | 输出 |
|---|---|
| `module_logger` | `firmware/lib/logger/*` |
| `module_time_helper` | `firmware/lib/time_helper.py` |
| `module_maintenance` | `firmware/tasks/maintenance.py` |
| `module_flash` | `tools/flash_device.py` |
| `module_log_tools` | `tools/read_device_log.py` + `tools/log_report.py` |

若未选 `module_maintenance`，`main.py` 不得导入或调用 `maintenance_tick`。若模式不是 `timer`，不得注入 `firmware/lib/scheduler/timer_sched.py`。

## script_run: init_scaffold.py

脚本是确定性渲染器，只读 manifest，stdout 输出 JSON，不写项目目录：

```bash
python -X utf8 <resource_root>/upy-scaffold-plugin/scripts/init_scaffold.py \
  --mode timer \
  --manifest <session_root>/phase_complete.upy_flash_mpy_firmware_plugin.json \
  --modules '["logger","flash_device","log_tools"]' \
  --custom-files '["firmware/lib/my_utils.py"]'
```

Prefer `--manifest <path>` over stdin redirection on Windows. If stdin is used (`--manifest -`), `init_scaffold.py` reads raw stdin bytes as UTF-8-SIG; callers should still run Python with `-X utf8`.

stdin 传完整 `manifest_content`。stdout 格式：

```json
{
  "phase": "scaffold",
  "mode": "timer",
  "scaffold_mode": "timer",
  "directories": ["firmware", "firmware/lib/logger"],
  "files": [
    {"path": "firmware/board.py", "content": "...", "encoding": "utf-8"},
    {"path": "project-manifest.json", "content": "{...}", "encoding": "utf-8"},
    {"path": "docs/.gitkeep", "content": "", "encoding": "utf-8"}
  ],
  "file_operations": [
    {
      "type": "file_operation",
      "payload": {
        "op_id": "scaffold_fo_001",
        "op": "write",
        "path": "firmware/board.py",
        "content": "...",
        "encoding": "utf-8"
      }
    }
  ],
  "status_updates": [
    {"step_id": "scaffold_start", "message": "正在生成项目骨架...", "level": "info"}
  ],
  "artifacts": [
    {"type": "file_tree", "title": "项目结构", "tree": {"firmware": {"board.py": "file"}}},
    {"type": "file_list", "title": "待写入文件", "files": [{"path": "firmware/board.py", "status": "pending"}]}
  ],
  "file_tree": {"firmware": {"board.py": "file"}},
  "manifest_content": {"phase": "scaffold", "scaffold_mode": "timer"},
  "phase_complete_payload": {
    "phase": "scaffold",
    "result": "success",
    "summary": "Generated 18 files, 10 directories",
    "next_phase": "upy-generate-plugin",
    "artifacts": []
  },
  "warnings": []
}
```

宿主可以直接使用 `file_operations[]`，也可以按 `files[]` 自行装配：

```json
{
  "type": "file_operation",
  "payload": {
    "op_id": "scaffold_fo_001",
    "op": "write",
    "path": "firmware/board.py",
    "content": "...",
    "encoding": "utf-8"
  }
}
```

路径必须保持相对项目根的 POSIX 风格，不要写绝对路径。

`phase_complete_payload` 是 payload 草案，不是完整 message envelope；真实 `msg_id`、`session_id`、`timestamp`、`idempotency_key` 由运行时宿主填写。

## incremental 流程

当用户在后续 phase 新增器件，跳过审批卡片，直接运行：

```bash
python -X utf8 <resource_root>/upy-scaffold-plugin/scripts/init_scaffold.py \
  --mode incremental \
  --manifest - \
  --new-devices '[{"name":"DHT22","driver":{"source":"upypi"}}]'
```

只允许输出新增器件的 `firmware/drivers/<name>_driver/__init__.py` stub 和更新后的 `project-manifest.json`，然后 `phase_complete(result=success, next_phase=upy-generate-plugin)`。不得重写 `firmware/main.py`、`board.py` 或其他骨架文件。增量 payload 必须带 `incremental=true` 与 `generate_scope="new_devices_only"`。

## 输出约束

- `board.py` 只放引脚常量和查询函数，不实例化硬件。
- `main.py` 只生成硬件实例化和调度框架；业务 task 注册位置保留 TODO。
- `timer` 模式使用 `firmware/lib/scheduler/timer_sched.py` 的 `Scheduler`；不要为端口兼容性改写该内部库，库默认 `timer_id=-1` 必须保留，因为 RP2/Pico 和 Zephyr 只支持虚拟 Timer。端口差异必须在 `main.py` 入口装配层解决：只有 RP2/Pico/RP2040/RP2350 和 Zephyr 可以显式生成 `Scheduler(timer_id=-1, tick_ms=...)`；其他 MCU/port 默认生成 `Scheduler(timer_id=0, tick_ms=...)` 或其他已验证非负硬件 Timer ID，不得生成隐式 `Scheduler(...)`、`Scheduler(tick_ms=...)` 或 `Scheduler(timer_id=-1)`。`async` 模式直接使用 `uasyncio`；`thread` 模式直接使用 `_thread`。
- GPIO 方向必须来自 `pinout[].type` 和引脚语义：`gpio_out`、`DATA`、`DO`、`OUT`、`GAIN`、`SD` 默认 `Pin.OUT`；`gpio_in` 默认 `Pin.IN`。不要把 WS2812 DATA 这类输出脚生成成 `Pin.IN`。
- `main.py` 必须有启动期 fatal guard。安装 rotating logger 后，关键启动状态必须 `print + logger` 双写；未捕获的启动/装配异常必须 `sys.print_exception()` 打到串口，并通过 `logger.exception()` 写入 `/log/run_*.log`。不要依赖 MicroPython 自动把顶层 traceback 写入文件日志。
- 不生成业务 `tasks/sensor_task.py`、`display_task.py`、`network_task.py`。
- `conf.py` 不得写 Wi-Fi 密码、API Key 或其他敏感数据。
- `tools/flash_device.py` 必须实现生产部署过滤：`main.py`、`boot.py`、`conf.py` 始终作为 `.py` 上传，不编译为 `.mpy`；`firmware/drivers/**/mock.py` 只属于测试替身，不得编译或上传，且 stale `build/mpy/drivers/**/mock.mpy` 也必须跳过。JSON summary 必须记录 `compiled_files`、`uploaded_files`、`skipped_files`，供 deploy-plugin 判定禁止产物。
- `.upy/` 只复制当前仓库真实存在的 schema 和工具脚本；不要伪造不存在的后续工具。
- `project-manifest.json` 必须作为 `file_operation` 写入项目根；`payload.manifest_content` 同时保留对象形式。
- `docs/.gitkeep` 必须保留，作为项目文档入口。
- `.flake8` 必须是 MicroPython-aware 配置：不要全局忽略 `F821/F401`，使用 `builtins=const` 和精确 `per-file-ignores`。
- `phase_complete.payload.artifacts` 必须是数组，至少包含 `file_tree` 和 `file_list`。
- `phase_complete.payload.next_phase` 成功时为 `upy-generate-plugin`；partial/failed 时为 `null`。

## 本地验证

运行：

```bash
python -X utf8 upy-scaffold-plugin/test/smoke_tests.py
python -X utf8 upy-scaffold-plugin/scripts/apply_scaffold.py \
  --session-dir <session_root> \
  --manifest <session_root>/phase_complete.upy_flash_mpy_firmware_plugin.json \
  --mode async \
  --modules logger,flash_device,time_helper,maintenance \
  --write-phase-complete
```

`test/run_local_actual_project.py` is a compatibility wrapper only; formal local actual tests and Claude Code host-side apply/finalize runs should call `scripts/apply_scaffold.py`.

## Protocol Addendum: project root, idempotency, and final manifest

These rules are normative for the plugin workflow and local Claude Code actual tests:

- `session_root` stores phase state, logs, checkpoint files, and phase_complete JSON.
- Scaffold project files MUST be written under `project_root`.
- If the caller only provides a session directory, use `project_root=<session_root>/project`.
- `file_operations[].payload.path` and `files[].path` stay POSIX-style paths relative to `project_root`; never prefix them with `sessions/<id>/project`.
- `python -m flake8 --jobs=1 firmware tools` MUST run with `cwd=project_root` and MUST return 0 before success can advance to `upy-generate-plugin`.
- Final `phase_complete.payload.runtime_context` MUST include `artifact_root`, `artifact_root_mode`, `session_root`, `project_root`, `file_operation_root`, and `resource_root`.
- `runtime_context.project_root`, `runtime_context.file_operation_root`, `payload.file_manifest.root`, and `payload.lint.cwd` SHOULD be artifact-relative POSIX paths, for example `sessions/<session_id>/project`.
- Final `phase_complete.payload.source` MUST record `source_phase`, `source_phase_complete_path`, `source_manifest_kind`, and `manifest_merge_strategy`. Do not rely on top-level `source_phase` fields only.
- Final `phase_complete.payload.scaffold` MUST record a stage-level summary while preserving `manifest_content.scaffold`, `manifest_content.scaffold_modules`, and `project/project-manifest.json`. Include final `mode`, `modules`, `custom_files`, `project_root`, `file_count`, `directory_count`, `file_status_counts`, `file_manifest_path`, `phase_complete_path`, `lint`, `source`, `approval_id`, `idempotency_key`, `incremental`, `generate_scope`, and `completed_at`.
- Final `phase_complete.payload.approval` MUST record the `scaffold_config` decision, including selected mode/modules/custom files and confirmation time.
- Final `phase_complete.payload.permissions` MUST record approved file writes and the flake8 script run with idempotency keys.
- Final `phase_complete.payload.lint` MUST record flake8 `command`, artifact-relative `cwd`, `config`, `returncode`, `stdout`, `stderr`, and `completed_at`.
- Renderer `file_list.status=pending` is only a draft state. Final `phase_complete` after local/host write MUST use `created`, `updated`, `unchanged`, `skipped`, or `error`.
- Final `phase_complete.payload.file_manifest` MUST include `root`, `generated_at`, and per-file `path`, `status`, `encoding`, `bytes`, `sha256`, `sha256_before`, `sha256_after`, `overwrite`, and optional `reason`.
- Success MUST write `scaffold_file_manifest.json` under `session_root`; it MUST use the same object shape as `payload.file_manifest`: `{root, generated_at, files}`. Do not write a bare file array.
- Final `phase_complete.payload.artifacts` MUST include `file_tree`, `file_list`, and `file_manifest`; `artifacts[type=file_manifest].path` MUST point to `sessions/<session_id>/scaffold_file_manifest.json`, and the final `file_list.title` should be `Scaffold 写入结果`.
- Retry/idempotency contract:
  - Missing target file -> `created`.
  - Existing identical file -> `unchanged`.
  - Existing different file without explicit overwrite approval -> `skipped` plus `structured_errors[].code=FILE_CONFLICT`, `result=partial`, `next_phase=null`.
  - Explicit overwrite approval or local `--force` -> `updated`.
- Time fields SHOULD be generated through `upy-project-gen-toolchain-spec/scripts/workflow_time.py --json`; fallback local UTC is only for local tooling degradation.
- Windows JSON reads MUST use UTF-8/UTF-8-SIG, never default GBK.
- For Claude Code local actual tests, use `scripts/apply_scaffold.py --session-dir <session_root> --manifest <phase_complete> --write-phase-complete`. Avoid inline `python -c` finalizers with raw Windows paths because `\U` in paths can trigger Python unicodeescape syntax errors.
- Success manifest MUST set `manifest_content.phase=scaffold`, `manifest_content.domain_phase=scaffold`, and `manifest_content.final_status=scaffolded`. Existing `firmware_flash` facts from flash phase MUST be preserved.
- `payload.warnings` and `structured_errors` should use structured objects. Do not write local machine absolute paths into formal warnings or artifacts.
```

覆盖：

- full + timer 输出 JSON、路径和 encoding。
- async 模式不注入 scheduler。
- incremental 只生成新驱动 stub 和 `project-manifest.json`，并进入 `upy-generate-plugin`。
- `approval_request.scaffold_config` 的 `item_groups` 分组协议。
- 本地 actual runner 应用 `file_operations[]` 到临时项目目录，并运行 flake8 gate。
