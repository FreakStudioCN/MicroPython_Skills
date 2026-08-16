---
name: mpos-prepare-deps
description: Prepare application-layer dependencies for MicroPythonOS Apps after mpos-analyze-app and before mpos-gen-app. Use when an MPOS App needs pure-Python MicroPython drivers, async/uasyncio/aio libraries, upypi or GitHub dependency research, vendored runtime files, dependency search caching, synchronous-driver adapter planning, or a machine-readable dependency handoff. Does not rebuild firmware, modify lvgl_micropython, add C/native/frozen modules, flash devices, package MPK files, or publish apps.
---

# MicroPythonOS App 依赖准备

## 角色

把 `mpos-analyze-app` 的 `dependency_plan.items` 变成可交给 `mpos-gen-app` 的依赖交接物。只处理应用层可用的依赖：纯 Python 文件、MicroPython package、可随 App 一起 vendoring 的源码、以及 MPY 已可用运行时依赖。

本 skill 可以真实下载文件到 App 目录，但只下载运行时需要的纯 Python/MPY 依赖文件。搜索结果、README、example、package metadata 和候选仓库证据写入缓存目录，不写入 skill 目录。

## 用户可见语言

遵守 `mpos-dev` 的语言连续性规则：当前 workflow 从中文开始，依赖摘要、风险、确认问题和交接说明继续用中文；从英文开始则继续用英文。代码、命令、路径、API 名和 JSON 字段名保持英文。

## 统一项目日志

完成依赖准备并产出 `dependency_handoff.json` 后，必须登记到项目状态目录：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill mpos-prepare-deps \
  --phase prepare-deps \
  --result <success|partial|failed> \
  --artifact dependency_handoff=<dependency_handoff.json> \
  --next-skill <handoff.next_skill-or-null> \
  --event "Prepared runtime dependencies and adapter requirements"
```

缓存仍放 `tmp/mpos-deps-cache/<fullname>/`；项目状态只记录 handoff、缓存路径和摘要，不复制缓存内容。

## 必读上下文

先加载 `mpos-dev`，并读取：

- App 结构与 entrypoint 规则：`mpos-dev/reference/docs-app-model.md`
- 系统 manager、TaskManager、DownloadManager、WebServer、Service：`mpos-dev/reference/docs-frameworks.md`
- 打包校验和 manifest 约束：`mpos-dev/reference/docs-packaging.md`
- MPOS API 精确索引：`mpos-dev/reference/mpos_api_summary.json`
- LVGL API 精确索引：`mpos-dev/reference/lvgl_api_summary.json`

如果输入来自 `mpos-analyze-app`，读取其 JSON。若没有 JSON，先从用户需求中整理等价的 `app.fullname`、目标功能、硬件/协议和依赖项。
`mpos_api_summary.json` 和 `lvgl_api_summary.json` 必须完整读取，用来确认内置 API 是否已经覆盖需求；不能因为任务看起来只是“找依赖”而省略。

可复用 `upy-pkg-guide` 的 upypi / awesome-micropython 搜索流程，但必须在它的基础上追加 async 搜索策略，不能只按同步驱动搜索。

## 边界

- 不讨论“是否必须重编译固件”。本系列 skill 只做应用层开发。
- 不修改 `lvgl_micropython`、board port、CMake、manifest board 配置或 native binding。
- 不接受需要 C extension、frozen module、native module、私有二进制 blob 或固件集成的依赖；标记到 `rejected[]` 并建议换纯 Python/MPY 可用方案。
- 不生成业务 App 代码；同步库的非阻塞封装只写适配建议，交给 `mpos-gen-app` 实现。
- 不把缓存写进 `MicroPython_Skills/` 或 `.claude/skills/`。

## 驱动放置策略

MicroPythonOS 当前运行器会把 entrypoint 所在目录插入 `sys.path`。当前 App entrypoint 通常是 `assets/main.py`，因此 `assets/` 是默认 import 根目录。

优先使用下面的路径，`target_path` 一律相对 App 根目录：

| 依赖形态 | 默认放置 | import 形式 |
|---|---|---|
| 单文件模块 | `assets/<module>.py` | `import <module>` |
| 多文件 package | `assets/<package>/__init__.py` 等 | `import <package>` 或 `from <package> import ...` |
| App 自己的适配层 | `assets/<name>_adapter.py` | 由 `mpos-gen-app` 生成 |
| 仅供参考的 README/example/metadata | `tmp/mpos-deps-cache/<fullname>/<dependency>/` | 不进入 App runtime |
| 必须隔离的第三方源码 | `assets/vendor/<dependency>/...` | 仅在 handoff 中标记 `requires_vendor_path_injection=true` 后使用 |

默认不要使用 `assets/vendor/`。只有依赖命名会和 App 文件冲突、或必须保留上游目录结构时才使用；一旦使用，必须在 JSON 里声明：

- `requires_vendor_path_injection: true`
- `vendor_sys_path: "assets/vendor"`
- `imports[]` 使用实际可运行的导入方式

如果 App 目录尚不存在，不要为了依赖生成 manifest 或业务代码。可以把运行时文件先下载到：

```text
tmp/mpos-deps-cache/<fullname>/staged/assets/
```

同时在 handoff 里保留最终目标 `target_path: "assets/..."`，让 `mpos-gen-app` 创建 App 后迁移或复制。

下载接受的 runtime 文件时优先使用脚本，避免路径漂移：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-prepare-deps/scripts/stage_runtime_file.py \
  --repo <repo-root> \
  --fullname <fullname> \
  --target-path assets/<module>.py \
  --source-url <raw-runtime-file-url> \
  --mode auto
```

`--mode auto` 规则：如果 `internal_filesystem/apps/<fullname>/` 已存在，真实写入 App 的 `assets/`；如果 App 尚未创建，写入 `tmp/mpos-deps-cache/<fullname>/staged/assets/`。不要把 README、example、package metadata 当 runtime 文件下载到 App。

## 搜索策略

先判断 MPOS 内置能力是否足够。若 `mpos-dev` 已提供 manager/framework/native MPY 能力，优先使用内置能力并标记 `source: "mpos_builtin"`，不要下载外部库。

板载硬件遵守 `mpos-dev/reference/docs-hardware-capabilities.md`：不得为板载摄像头、音频、输入、IMU、灯光、电池、SD、GPS、红外、LoRa 或环境传感器下载板卡驱动，也不得把 `mpos.board.*` 当依赖。能力合同为 `portable_api=false` 时返回 `MPOS_CAPABILITY_API_MISSING`。

只有 `analysis_result.json.required_accessories[]` 明确声明外接硬件时，才允许搜索 App-local 驱动；handoff 必须包含连接协议、待确认接线、总线/引脚冲突、阻塞行为、设备权限和真机验证要求。未确认接线时不得把 GPIO/I2C/SPI/UART 数值写入运行时代码。

外部搜索按以下来源顺序：

1. `mpos_builtin`
2. `micropython-lib`
3. upypi / mip package
4. awesome-micropython
5. GitHub/GitLab/Codeberg 仓库
6. 单文件纯 Python driver

每个依赖至少使用基础词和 async 词两组搜索：

```text
<name> micropython
<name> micropython driver
<name> micropython async
<name> micropython asyncio
<name> micropython uasyncio
<name> micropython aio
<protocol> micropython non-blocking
<protocol> micropython await create_task sleep_ms
<protocol> micropython websocket mqtt ble aioble espnow async
```

高价值关键词：

```text
async, asyncio, uasyncio, aio, await, create_task, sleep_ms,
event loop, task, coroutine, non-blocking, nonblocking, stream,
queue, lock, event, callback, reconnect, timeout, websocket,
web server, mqtt, ble, aioble, espnow, aioespnow
```

开始外部搜索前，用脚本生成并缓存查询计划：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-prepare-deps/scripts/build_search_plan.py \
  --repo <repo-root> \
  --fullname <fullname> \
  --dependency "<dependency-name>" \
  --protocol "<protocol-or-feature>" \
  --write-cache
```

执行真实搜索时必须覆盖脚本输出中的 `base_queries` 和 `async_queries`。如果基础词找到同步库，也继续执行 async/aio/uasyncio/non-blocking 查询；只有在 async 候选不可用、不兼容或风险更高时，才接受同步库并标记 adapter。

## 缓存规则

缓存目录固定为：

```text
tmp/mpos-deps-cache/<fullname>/
```

缓存可以包含：

- search query、结果列表、时间戳、source URL
- upypi package JSON、mip metadata、awesome-micropython 命中项
- GitHub/GitLab repo metadata、README、examples、license
- 下载前的候选文件清单和兼容性笔记
- `build_search_plan.py` 生成的 `search_plan.json` 和每个依赖的 `search_queries.json`
- `stage_runtime_file.py` 生成的 `downloads/*.json`，记录 source URL、目标路径、sha256、实际写入 App 或 staging 的位置

缓存不能包含账号、token、私有网络凭据或用户设备信息。缓存文件不要作为 App runtime 文件打包，除非用户明确要求把 license 或 attribution 放进 App。

## 兼容性筛选

接受依赖前检查：

- 是否纯 Python/MPY 可放入 App 目录。
- 是否支持 MicroPython，不依赖 CPython-only 模块，例如 `requests`、`threading`、`pathlib`、runtime `typing`、`dataclasses`。
- 是否使用 async 模式：`import asyncio` / `uasyncio`、`async def`、`await`、`create_task`、`sleep_ms`、`wait_for`、stream、queue、lock。
- 是否存在阻塞模式：`while True` 加 `time.sleep`、阻塞 socket、同步 `urequests`、长时间 busy loop。
- 是否有明确硬件总线需求：I2C/SPI/UART/GPIO/ADC/PWM/BLE/WiFi，并能由 MPOS/设备 API 提供。
- license 是否允许 vendoring；不清楚时在 `risks[]` 标记。

同步库允许作为候选，但如果被接受，必须满足：

```json
"async_compatible": false,
"sync_needs_adapter": true
```

并在 `adapter_requirements[]` 说明 `mpos-gen-app` 需要如何封装，例如：

- 用 `TaskManager.create_task` 调度轮询。
- 用 `TaskManager.sleep_ms` 或 `asyncio.sleep_ms` 替代 `time.sleep`。
- 把阻塞 I/O 移到短周期 task，给 UI loop 让出控制。
- 设置 timeout、重连和取消路径。

## 工作流

1. 读取 `mpos-analyze-app` JSON 或等价需求，确定 `app.fullname`、App 目录、目标硬件/协议、`dependency_plan.items`。
2. 读取 `mpos-dev`，先找 MPOS 内置 API 是否覆盖需求。
3. 对每个外部需求先运行 `build_search_plan.py --write-cache`，生成基础词和 async/aio/uasyncio/non-blocking 查询。
4. 执行真实搜索，并把搜索证据写入 `tmp/mpos-deps-cache/<fullname>/`；handoff 的每个外部依赖必须记录 `search_queries[]` 和 `cache_records[]`。
5. 对候选依赖做应用层、MicroPython、async、阻塞、license、文件大小和 import 路径检查。
6. 用 `stage_runtime_file.py --mode auto` 只下载接受的 runtime 文件到 App 的 `assets/` 路径；App 不存在时下载到 staging cache。
7. 给同步依赖写清 `sync_needs_adapter=true` 和 `adapter_requirements[]`。
8. 输出 Markdown 摘要和 JSON handoff。JSON 应匹配 `templates/dependency_handoff.json`，并可用校验脚本检查。

## 输出要求

用户可见输出按这个顺序：

1. `依赖位置`：说明 runtime 文件最终放在 `internal_filesystem/apps/<fullname>/assets/` 下，缓存放在 `tmp/mpos-deps-cache/<fullname>/`。
2. `采用/拒绝的依赖`：列出每项依赖来源、目标路径、async 状态、风险。
3. `同步适配`：列出所有 `sync_needs_adapter=true` 的依赖和交给 `mpos-gen-app` 的封装要求。
4. `需要确认`：只列真正阻塞的问题；没有则写“无阻塞问题”。
5. `JSON`：fenced `json` 代码块，包含完整 dependency handoff。

## JSON 契约

使用 `templates/dependency_handoff.json` 作为字段模板。关键要求：

- `schema_version` 固定为 `"mpos-prepare-deps-v1"`。
- `phase` 固定为 `"prepare-deps"`。
- `app.fullname`、`app.app_dir`、`app.assets_dir` 必须存在。
- `cache.enabled` 为 `true` 时，`cache.path` 必须以 `tmp/mpos-deps-cache/` 开头。
- `search_policy.sources` 必须包含 `mpos_builtin`、`micropython-lib`、`upypi`、`awesome-micropython`、`github`。
- `search_policy.async_terms` 必须包含 `async`、`asyncio`、`uasyncio`、`aio`、`await`、`create_task`、`sleep_ms`、`non-blocking`。
- 接受的依赖必须有 `name`、`source`、`url`、`target_path`、`install_action`、`imports`、`app_layer_ok`、`async_compatible`、`sync_needs_adapter`。
- 接受的依赖 `target_path` 必须以 `assets/` 开头。
- 外部接受依赖必须有 `search_queries[]`，且包含 async/aio/uasyncio/non-blocking 查询。
- `cache.enabled=true` 时，外部接受依赖必须有 `cache_records[]`，并且路径位于 `tmp/mpos-deps-cache/<fullname>/`。
- `staged_path` 必须位于 `tmp/mpos-deps-cache/<fullname>/staged/assets/`。
- `async_compatible=false` 的接受依赖必须设置 `sync_needs_adapter=true`。
- 被拒绝依赖写入 `rejected[]`，必须包含 `name` 和 `reason`。
- `handoff.next_skill` 通常是 `"mpos-gen-app"`；如果还缺用户选择，则回到 `"mpos-analyze-app"` 或 `"mpos-plan-app"`。

校验命令：

```bash
python3 /home/leeqingshui/MicroPython_Skills/mpos-prepare-deps/scripts/validate_dependency_handoff.py \
  /home/leeqingshui/MicroPython_Skills/mpos-prepare-deps/templates/dependency_handoff.json
```

## 下游交接

传给 `mpos-gen-app` 的重点不是“找到了哪个库”，而是“如何安全 import 和如何不阻塞 MPOS/LVGL async 调度”：

- 最终 runtime 文件清单和 `target_path`。
- `imports[]` 的准确写法。
- `async_compatible` / `sync_needs_adapter`。
- `adapter_requirements[]`。
- `risks[]` 和必须测试的硬件/网络场景。
- `rejected[]`，防止下游又选回 native/C/frozen 方案。
