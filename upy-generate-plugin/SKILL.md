---
name: upy-generate-plugin
description: 插件化 MicroPython 业务代码生成阶段。用于收到 next_phase=upy-generate-plugin 的 scaffold phase_complete 后，生成驱动依赖、factory/mock、tasks、conf.py、main.py、测试、lint/check/git commit 和 phase_complete；也用于 deploy/simulate/autofix 或用户反馈后以 mode=fix 最小修复代码。
---

# upy-generate-plugin 插件化工作流

`upy-generate-plugin` 是 MicroPython 项目流水线的业务代码生成阶段。它消费 `upy-scaffold-plugin` 的 `manifest_content` 和项目骨架，生成完整 firmware 业务代码、测试、依赖文件和 `phase_complete`。它必须保留旧 `upy-generate` 的嵌入式约束，但把直读直写改成插件协议：

```text
file_operation(read/write)
script_run(...)
approval_request(...)
permission_request(...)
status_update(...)
phase_complete(...)
```

正式链路：

```text
upy-analyze-plugin
-> upy-select-hw-plugin
-> upy-flash-mpy-firmware-plugin
-> upy-scaffold-plugin
-> upy-generate-plugin
-> upy-deploy-plugin 或 upy-simulate-plugin
```

失败或反馈闭环：

```text
deploy / simulate / test 失败
-> upy-autofix-plugin
-> upy-generate-plugin(mode=fix)
```

若 `upy-autofix-plugin` 暂未实现，允许：

```text
upy-deploy-plugin
-> 用户输入现象/反馈问题
-> upy-generate-plugin(mode=fix, source=user_feedback_after_deploy)
-> upy-deploy-plugin
```

## 必读引用

真实 full/fix 生成前，按阶段读取这些引用文件。它们迁移自旧 `G:\MicroPython_Skills\upy-generate\SKILL.md` 的关键约束和模板，优先级高于本文件摘要：

| 时机 | 必读文件 |
|---|---|
| 解析协议、写 `phase_complete`、解释 JSON 字段 | `references/protocol_fields.md` |
| 开始 full/fix 生成前 | `references/legacy_constraints.md` |
| 生成 driver factory/mock 前 | `references/driver_factory_templates.md` |
| 生成 task 和 PC 测试前 | `references/task_generation_rules.md` |
| 生成 device MicroPython unittest 测试前 | `references/device_unittest_subset.md` |
| 修改 `conf.py` 或 `main.py` 前 | `references/main_conf_rules.md` |
| 使用 MicroPython 硬件/外设/端口 API 前 | `knowledge/micropython_official_library_index.json` |
| 需要 LLM/ASR/TTS/IoT/MQTT/Webhook/云 API 前 | `references/cloud_integrations.md` |
| 运行质量门禁前 | `references/validation_gates.md` |
| 输出 success 和 git commit 前 | `references/final_review_checklist.md` |

## 启动消息

full 模式：

```json
{
  "protocol_version": "1.0",
  "type": "start_phase",
  "phase": "upy-generate-plugin",
  "session_id": "uuid",
  "idempotency_key": "upy-generate-plugin:<session_id>:full:v1",
  "payload": {
    "mode": "full",
    "source_phase": "upy-scaffold-plugin",
    "source_phase_complete_path": "sessions/<session_id>/phase_complete.upy_scaffold_plugin.json",
    "next_phase_preference": "deploy",
    "runtime_context": {
      "artifact_root": ".",
      "artifact_root_mode": "cwd",
      "session_root": "sessions/<session_id>",
      "project_root": "sessions/<session_id>/project",
      "file_operation_root": "sessions/<session_id>/project",
      "resource_root": "upy-generate-plugin"
    },
    "capabilities": {
      "approval_request": true,
      "file_operation": true,
      "script_run": true,
      "git_operation": false,
      "checkpoint_resume": true,
      "cancellation": true
    }
  }
}
```

fix 模式：

```json
{
  "type": "start_phase",
  "phase": "upy-generate-plugin",
  "payload": {
    "mode": "fix",
    "source": "user_feedback_after_deploy",
    "error_context": {
      "user_feedback": "设备上电后 OLED 没显示，串口只打印 boot ok",
      "deploy_result_path": "sessions/<session_id>/phase_complete.upy_deploy_plugin.json",
      "serial_excerpt": "...",
      "previous_generate_commit": "abc123"
    }
  }
}
```

## full 流程

1. 校验上游 `phase_complete(upy-scaffold-plugin)`：`result=success` 且 `next_phase=upy-generate-plugin`。迁移期直测可直接传 manifest，但正式链路不要跳过 scaffold。随后运行 `scripts/check_session_state.py --session-dir <session_root> --project-dir <project_root>`，如果发现 stale 旧 generate 记录，必须归档/忽略旧 `phase_complete.upy_generate_plugin.json` 和 `generate_phase_log.md`，不得把它当作当前 success/resume 状态。
2. 读取 `payload.manifest_content`、`runtime_context.project_root`、`firmware/board.py`、`firmware/conf.py`、`firmware/main.py`、`.flake8`。
3. 运行前询问用户是否补充装置行为。只允许补充业务行为、阈值、周期、状态机、日志和模拟场景；新增硬件或改引脚必须回退到 analyze/select-hw/scaffold。
4. 写 `project/generate_plan.json`，先只规划不写运行时代码。计划必须包含 scheduler_mode、driver adapters、tasks、config_constants、main_assembly、tests、resource_plan、cloud_integrations（如果需要云 API）。语音、传感器、云 API、状态机或跨 tick 业务流还必须包含 `data_flow_contract[]`，并为每条关键数据流声明 contract test 覆盖。随后运行 `scripts/check_generate_plan.py --project-dir <project_root> --require-plan`，失败则停在 partial，不要继续大规模写代码。
5. 用英文关键词解析驱动和中间件依赖。先运行 `scripts/resolve_upypi_packages.py` 枚举 `https://upypi.net/packages.json`，再按英文关键词调用搜索、awesome-micropython 或 GitHub fallback。
6. 如果需求涉及 LLM、ASR、TTS、视觉、IoT/MQTT、Webhook、天气地图、对象存储、第三方 REST API 或任何付费/带凭据云服务，读取 `references/cloud_integrations.md` 和 `knowledge/cloud_service_catalog.json`，发起用户确认：服务商、官方文档/控制台/价格链接、是否已开通计费/购买 token、API Key 是否准备好、是否需要网关/代理。不要把真实 token 写入代码。
7. 运行 `scripts/download_drivers.py`。脚本只读 manifest/stdin，只 stdout JSON；不得直接写项目目录，不得直接改 `project-manifest.json`。
8. 将脚本输出的 `files[]` 逐条转成 `file_operation(write)`，目标必须位于 `firmware/lib/...`。
9. 读取 `references/driver_factory_templates.md`，再读取驱动源码、README、example 和 package metadata，生成 `firmware/drivers/<name>_driver/__init__.py` 与 `mock.py`。Mock 方法签名必须来自驱动源码。
10. 读取 `references/task_generation_rules.md`，按 scaffold 选择的调度模式生成 task：
   - `timer`：周期 tick，避免阻塞，优先使用 `time_helper.timed_function`。
   - `async`：使用 `uasyncio`，优先使用 `timed_coro`，阻塞 sleep 改为 `await asyncio.sleep_ms`。
   - `thread`：使用 `_thread` worker、锁和主循环心跳。
11. 复用 scaffold 资产：`firmware/lib/logger`、`time_helper`、`maintenance`、`scheduler`。不要重复生成日志系统。
12. 读取 `references/main_conf_rules.md`，更新 `firmware/conf.py`，所有阈值、周期、重试、日志配置必须在 conf 中，不在 task/main 中硬编码；云 API 只能写非密钥 endpoint、模型名、超时、重试、功能开关和 secret 名称，不写真实密钥。
13. 涉及 `machine`、`network`、`neopixel`、`esp32`、`rp2`、`bluetooth` 等硬件/外设/端口 API 时，必须先查 `knowledge/micropython_official_library_index.json` 对应 MicroPython 官方页面，并在 `manifest_content.generate.doc_evidence[]` 记录 `module`、官方 `url`、`reason`。只有 CPython 参考链接或 MicroPython 页面内容不足时，不能当作充分外设实现依据，必须补端口文档证据或输出 partial。
14. 继续按 `references/main_conf_rules.md` 更新 `firmware/main.py`，保留启动延时，安装 rotating logger，完成 `machine -> factory -> driver -> task` DI 装配，启动时执行 I2C scan，print 与 logger 双写关键状态。写完 `conf.py/main.py` 立即运行 `scripts/check_conf_contract.py --project-dir <project_root>`。
15. 生成 PC `unittest` 和 device MicroPython `unittest` 测试。生成设备端测试前必须读取 `references/device_unittest_subset.md`；设备端测试不是 CPython-only 测试，也不应只是 import smoke。只要设备端测试 import `unittest`，必须在 `runtime_dependencies.mip` 声明 deploy 阶段安装 `unittest`，不要默认把 micropython-lib 源码复制进项目。
16. 读取 `references/validation_gates.md`，运行完整质量门禁：`.pylintrc`、generate_plan、py_compile、conf_contract、driver compile、flake8、pylint、PC unittest、MicroPython import、dead config、task no-machine、device unittest subset、runtime dependencies、doc evidence、skeleton compliance、generated semantics、cloud integrations、session checkpoint。
17. 读取 `references/final_review_checklist.md`，逐项做最终审查，并输出结构化 `review_findings`。
18. 生成 `phase_complete` 草案后运行 `scripts/check_final_review_consistency.py` 与 `scripts/check_phase_complete_consistency.py --phase-complete <phase_complete> --project-dir <project_root>`；如果失败，必须改为 `partial/failed`、`next_phase=null` 并记录 structured error。
19. 检查和最终审查通过后发起 git commit 权限请求。full 和 fix 每次通过校验都必须 commit。
20. 输出 `phase_complete`，默认 `next_phase=upy-deploy-plugin`；用户可选 `upy-simulate-plugin` 或 `null`。如果云服务是 `mock_only` 或 `blocked`，不得进入 deploy。
21. 成功后询问是否生成附加产物：`upy-diagram-plugin` 和 `upy-wiring-plugin`。它们只能进入 `optional_next_phases`，不得覆盖主 `next_phase`。

Additional hard rules:

- Run `check_generate_plan.py --require-plan` before broad code writes, and run `check_generate_plan.py --require-plan --check-files` after code writes. Planned task/driver/middleware/test paths that do not exist are blocking failures.
- For voice/sensor/cloud/state-machine flows, `generate_plan.json` must declare `data_flow_contract[]` with producer, consumer, invariant, storage when cross-stage, and test coverage. Prefer generated contract tests over trying to infer all business semantics from static AST checks.
- Never mark skipped pylint as success. If `.pylintrc` is missing, run `scripts/ensure_pylintrc.py`; then run pylint and record the real integer return code.
- `phase_complete.result=success` requires `file_manifest.files` to include both `project-manifest.json` role `manifest` and `generate_plan.json` role `plan`.
- `phase_complete.result=success` requires `session_state.upy_generate_plugin.json`, `checks.session_state_checkpoint.ok=true`, and an artifact entry with `type=session_state`.
- Write `session_state.upy_generate_plugin.json` only through `scripts/update_session_state.py`; do not hand-write a simplified JSON state. It must include `protocol_version`, `checkpoint`, `attempt`, `idempotency_key`, `manifest_hash`, `git_commit`, and `usage`.
- `manifest_hash` means the SHA256 of `project/project-manifest.json`, not the git commit. `session_state.git_commit` and `phase_complete.payload.generate.git.commit` must record final deliverable project HEAD. If `project-manifest.json` records an earlier code-generation commit, use `generate.git.code_commit` or include an explicit `commit_role`; do not imply it is final HEAD.
- `project-manifest.json` must advance consistently: `phase="generate"`, `domain_phase="generate"` when present, and `final_status="generated"` when present.
- `phase_complete.result=success` requires `payload.artifacts[]` to include both `type=session_state` and `type=file_manifest`.
- `phase_complete.result=success` requires `optional_next_phases` to offer `upy-diagram-plugin` and `upy-wiring-plugin`.
- `phase_complete.result=success` requires a completed git commit after clean gates. Commit denied, dry-run, not-a-git-repository, or commit skipped means `partial` with `next_phase=null`.
- `phase_complete.result=success` must not leave or commit CPython cache files. Run quality gates with bytecode disabled or temporary compile targets, remove project-local `__pycache__/` and `*.pyc` before git commit, and keep them out of `file_manifest` and artifacts.
- `phase_complete.result=success` must include `manifest_content.generate.runtime_dependencies` when generated firmware/device tests require mip packages; deploy installs them with `mpremote mip install`.
- `phase_complete.result=success` must include `manifest_content.generate.doc_evidence[]` for hardware/peripheral MicroPython APIs.
- `phase_complete.result=success` must include a production deploy plan: `manifest_content.generate.deploy_plan.source_only` contains `firmware/main.py`, `firmware/boot.py`, and `firmware/conf.py`; `upload_exclude` contains `firmware/drivers/**/mock.py` and `firmware/drivers/**/mock.mpy`. Driver mocks are test/support artifacts and must not be required by runtime firmware.
- Generate real device-side MicroPython unittest interface/contract tests under `device/tests/` by default. Keep `test/device/` only for legacy compatibility or existing project layout. Device tests should verify generated protocol/state/task/driver/config contracts, not only imports.
- Treat `NETWORK_DISCONNECTED`, `RATE_LIMITED`, and `UPSTREAM_TIMEOUT` as retryable interruption states. Treat `TOKEN_BUDGET_EXCEEDED`, `MODEL_CONTEXT_EXHAUSTED`, and `CANCELLED_BY_USER` as non-retryable unless the user changes budget/model/intent. Record them in `session_state.last_error` and structured errors.
- In async scheduler mode, do not call blocking driver/time operations directly inside `async def`: `time.sleep_ms`, `read_samples`, `play_samples`, `connect`, scan loops, or synchronous HTTP. Use cooperative state machines/adapters, thread mode, or emit `partial`.
- Do not hide blocking async calls with `getattr`, `__getattribute__`, alias variables, lambdas, reflection helpers, or thin sync wrapper functions. Yielding once before `record()`, `play()`, `connect()`, scan loops, or synchronous HTTP is not a non-blocking adapter. Use a real cooperative state machine, thread/worker handoff, genuinely non-blocking API, or emit `partial`.
- Use ASCII comments in generated firmware unless the project already requires non-ASCII. Avoid decorative box-drawing or mojibake separator comments in generated `.py` files.
- When `project-manifest.json` is `phase=scaffold` but a previous `phase_complete.upy_generate_plugin.json` says success, treat that previous generate event as stale/audit-only. If `generate_plan.json` or file_manifest paths are missing, start from scaffold input instead of resuming the stale generate output.
- If timer/scheduler assembly is generated or modified, read `knowledge/esp32_timer_scheduler_api.pitfall.json` before writing `firmware/main.py`. Do not rewrite scaffold-owned `firmware/lib/scheduler/timer_sched.py` just to solve port compatibility; inspect its API/defaults and keep its `timer_id=-1` default because RP2/Pico and Zephyr require virtual timers. Only RP2/Pico/RP2040/RP2350 and Zephyr should use `Timer(-1)` / `Scheduler(timer_id=-1)`. Other MCU/port targets must pass an explicit valid non-negative hardware timer id such as `Scheduler(timer_id=0, error_cb=...)`; do not generate implicit `Scheduler()` / `Scheduler(tick_ms=...)` when the scheduler default maps to `Timer(-1)`.
- Peripheral documentation evidence must be exact enough for the used API. `machine.Pin`, `machine.I2S`, `machine.Timer`, `neopixel`, `network.WLAN`, etc. must cite their corresponding MicroPython official page from `knowledge/micropython_official_library_index.json`; a parent `machine` page is not sufficient for a specific `machine.*` class when the index has a specific page.
- Do not edit scaffold-owned framework files such as `firmware/lib/logger/*`, `firmware/lib/scheduler/*`, `firmware/lib/time_helper.py`, or `firmware/tasks/maintenance.py` unless the user explicitly requests a scaffold library contract change. Fix generator code, entrypoint assembly, validation scripts, or deploy tooling instead.
- When generated `main.py` installs the scaffold rotating logger, do not modify scaffold logger source to add timestamps. Instead, generated calls must mix timestamp/uptime into message text at the call site, for example with `time.ticks_ms()`, `time.ticks_diff()`, `time.localtime()`, or an explicit helper. This preserves scaffold ownership while making `/log/run_*.log` useful after deploy.

## 运行前用户补充

发起一个可选审批/输入请求，收集：

- 采样周期、阈值、报警策略、输出动作。
- 网络重试、离线缓存、日志级别。
- OLED/UI、蜂鸣器、继电器、LED 等行为。
- 用户想优先进入 deploy、simulate 或 stop。
- 期望 diagram/wiring 产物。

判断规则：

| 用户补充内容 | 处理 |
|---|---|
| 业务行为、阈值、周期、状态机 | generate 直接吸收 |
| 新增/替换电子模块 | 回退 analyze/select-hw |
| 改引脚、总线、电源 | 回退 select-hw/scaffold |
| 只想看业务逻辑模拟 | `next_phase=upy-simulate-plugin` |
| 只生成代码 | `next_phase=null`，带 checkpoint |

## 依赖和驱动规则

- 所有驱动和中间件文件必须写到 `firmware/lib`，协议路径使用 POSIX 相对路径。
- 用户中文需求必须先转英文关键词再搜索。示例：`温湿度` -> `temperature humidity sensor`，`MQTT 上报` -> `mqtt publish client`。
- V0 可调用 `upy-pkg-guide` 作为 adapter，但输出必须归一化为 JSON：包名、来源、版本、文件、README、example、API 摘要、warnings。
- 如果 `devices[].driver.status == cold_driver_required`，可以生成 Mock 和业务框架，但不得输出 deploy-ready success；应 partial 并建议 `upy-gen-driver-plugin` 或 simulate。

## 云服务/API 接入规则

- 涉及 LLM、火山方舟、阿里云百炼/通义、腾讯混元、百度千帆、OpenAI、Azure OpenAI、Gemini、Anthropic、ASR/TTS、IoT/MQTT、Webhook、短信/邮件、天气地图、对象存储、任意第三方 REST API 时，必须读取 `references/cloud_integrations.md`。
- 先给用户服务商官方 docs/console/pricing 链接，让用户决定是否开通、购买 token/额度、生成 API Key，或改用自己的 HTTPS gateway/proxy。
- `knowledge/cloud_service_catalog.json` 是可扩展服务目录。缺少服务商时可以生成 `custom_http_proxy` 方案，但必须记录原因和用户待办。
- `manifest_content.generate.cloud_integrations[]` 必须记录 provider、category、services、official_links、credential_management、user_action_required、deploy_ready。
- 不得把真实 API Key/token/AK/SK/password/Bearer 写入 `conf.py`、task、main、测试、日志、phase_complete 或 git commit。只记录 secret 名称和 deploy-time 提示。
- 需要 HMAC/OAuth/token exchange/mTLS/大型 SDK/账号级 AKSK 的云服务，优先生成网关/代理模式；ESP32 只调用受控 HTTPS gateway。
- 云服务未确认、未开通计费、未准备凭据或只是 mock 时，`next_phase` 必须是 `upy-simulate-plugin` 或 `null`，不能默认 deploy。
- 运行 `scripts/check_cloud_integrations.py --project-dir <project_root>`；真实 success 前还要通过 `check_phase_complete_consistency.py`。

## 代码生成约束

- 先读取 `references/legacy_constraints.md`，保留旧 `upy-generate` 的单元测试驱动嵌入式开发哲学。
- 除 `firmware/main.py` 和硬件 factory 外，业务 task 不得 import `machine`。
- task 使用依赖注入，不直接实例化硬件。
- 每个传感器/器件读写独立 try/except，一个失败不影响其他。
- 关键状态必须 print + `lib.logger` 双写：启动、驱动初始化、读数、报警、显示、网络发送、异常。
- 生成 task 时必须遵守 `references/task_generation_rules.md` 的日志矩阵。
- 生成 factory/mock 时必须遵守 `references/driver_factory_templates.md` 的 I2C/GPIO/SPI 模板和驱动 API 解析规则。
- 生成 `main.py` 和 `conf.py` 时必须遵守 `references/main_conf_rules.md` 的 rotating logger、I2C scan、boot delay、配置常量规则。
- PC 测试必须使用 CPython `unittest`，覆盖正常、设备为 None、驱动异常三类场景。
- device 测试必须读取并遵守 `references/device_unittest_subset.md`：使用 MicroPython 可运行的 `unittest` 子集，覆盖设备端可跑的协议、状态、driver adapter、配置或轻量文件系统行为；不要生成 pytest、`unittest.mock`、`pathlib`、`tempfile`、`typing` 等 CPython-only 测试代码。
- 不把 Wi-Fi 密码、API Key 或 token 写入 `conf.py`。
- 不静默修改 `board.py` pinout；发现引脚问题输出 structured error。

## MicroPython-aware 校验

MicroPython 官方文档说明其标准库是面向嵌入式的精简子集，且不同 port/固件可能裁剪模块；因此不能只依赖 CPython `flake8`。生成后必须运行完整质量门禁。优先使用统一脚本：

```text
python scripts/update_session_state.py --session-dir <session_root> --checkpoint tests_generated --step quality_gates --status running --idempotency-key <stable-key>
python scripts/run_quality_gates.py --project-dir <project_root> --session-dir <session_root>
```

该脚本应覆盖：

```text
ensure .pylintrc
check_generate_plan.py
py_compile
check_conf_contract.py
driver source compile
flake8
pylint
PC unittest
check_mpy_imports.py
check_mpy_imports.py --include-lib
check_dead_config.py
check_task_no_machine_import.py
check_device_unittest_subset.py
check_runtime_dependencies.py
check_doc_evidence.py
check_skeleton_compliance.py
check_generated_semantics.py
check_cloud_integrations.py
update_session_state.py --check
check_final_review_consistency.py
check_phase_complete_consistency.py
```

`.flake8` 优先复用 scaffold 生成的配置，只做项目级补充，不覆盖上游。`.pylintrc` 如果 scaffold 未生成，generate 必须通过 `scripts/ensure_pylintrc.py` 写入或请求写入，不能跳过 pylint。pylint 强门禁作用于 generate 负责的 `firmware/main.py`、`firmware/drivers/**/*.py`、`firmware/tasks/*.py`；默认只把 fatal/error/usage bit 当强失败，warning/refactor/convention 记录为 warnings，除非显式使用 `--strict-pylint`。`firmware/lib` 和 scaffold 框架库只做 compile/import 风险检查，不因风格噪声阻断 success。

MicroPython import 检查必须区分真实运行时导入和 PC fallback。允许：

```python
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
```

此类 fallback 只能作为 `MPY_IMPORT_CPYTHON_FALLBACK` warning；直接 `import asyncio`、`typing`、`dataclasses`、`pathlib`、CPython `logging` 仍然是强失败。

`check_generated_semantics.py` 是强门禁。它必须拦截 runtime placeholder、每 tick 重置状态机、async 同步网络调用、硬件数据读取后丢弃、共享 I2S/SPI/UART 资源无 `generate.resource_plan` 等问题。命中这些问题时不得输出 deploy-ready success。生成的 `main.py` 若安装 rotating logger，必须有顶层启动 fatal guard：异常同时 `sys.print_exception()` 到串口并通过 `logger.exception()` 写入设备日志。生成的 `Scheduler(...)` 必须传入 `error_cb`，task 异常也要 `print + logger.exception` 双写。

## fix 模式

fix 模式可来自 `upy-autofix-plugin`，也可来自 deploy 后用户人工反馈。规则：

1. 只做最小修改，不重写整个项目。
2. 输入必须带 `error_context`，包括 traceback、文件路径、设备观察、用户反馈、triage_json 或 previous_attempts。
3. 修改前读取 `generate_fix_history.json` 和上次 commit。
4. 修改后重新运行 lint/check。
5. 通过后 git commit。
6. 输出 `code_diff`、`changed_files`、`attempts[]`、`knowledge_refs[]`。

边界：

| 问题类型 | 处理 |
|---|---|
| 业务逻辑、驱动 API 调用、阈值、日志 | generate fix |
| 引脚接错、I2C 地址变更、总线冲突 | structured error，建议 select-hw 或人工确认 |
| 新增/替换硬件 | 回退 analyze/select-hw/scaffold |
| 烧录、串口、上传失败 | deploy 重试或设备排查 |
| 驱动不存在 | partial，触发 gen-driver 或 simulate |

## phase_complete 输出

成功输出必须包含：

- `manifest_content.phase="generate"`。
- `manifest_content` 保留完整上游 manifest：`requirements`、非空 `devices`、`mcu`、`pinout`、`scaffold`/`scaffold_mode` 等字段不得被 `generate` 摘要替代。
- `project/project-manifest.json` 已同步更新为 `phase="generate"`。
- `generate.behavior_spec`。
- `generate.deploy_plan`。
- `generate.simulation_hints`。
- `generate.cloud_integrations`（如果涉及云 API/LLM/IoT/Webhook）。
- `generate.git.commit`。
- `lint.flake8` / `lint.pylint` / `tests.pc_unittest` / `checks`。
- `file_manifest`，且必须包含 `project-manifest.json` 的 manifest role 条目。
- `file_manifest` 应包含 `generate_plan.json` 的 `role="plan"` 条目。
- `session_state.upy_generate_plugin.json` artifact、`checks.session_state_checkpoint.ok=true`、`checkpoint`。
- `permissions`。
- `optional_next_phases`。
- `review_findings.blocking=[]`。

`manifest_content` 必须是完整更新后的项目 manifest，不能只包含 `phase/schema_version/project_name/updated_at` 这类摘要字段。`phase_complete.result=success` 之前必须通过 `scripts/check_phase_complete_consistency.py`。

默认：

```json
{
  "payload": {
    "phase": "generate",
    "result": "success",
    "next_phase": "upy-deploy-plugin",
    "optional_next_phases": [
      {"phase": "upy-diagram-plugin"},
      {"phase": "upy-wiring-plugin"}
    ],
    "manifest_content": {
      "phase": "generate"
    }
  }
}
```

partial/failed 时 `next_phase=null`，并带：

```json
{
  "structured_errors": [
    {
      "code": "lint_failed",
      "severity": "error",
      "phase_step": "lint",
      "retryable": true,
      "message": "flake8 failed"
    }
  ]
}
```

## 本地验证

运行：

```bash
python -X utf8 upy-generate-plugin/test/smoke_tests.py
```

本地 runner：

```bash
python -X utf8 upy-generate-plugin/test/run_local_mock_session.py --session-dir <session_root> --write-phase-complete
```

本地 runner 只用于 mock/验证插件协议，不代表真实 LLM 已完成所有业务代码生成。
