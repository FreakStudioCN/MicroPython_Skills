---
name: upy-deploy-plugin
description: 插件化工作流版 MicroPython 项目部署和运行验证阶段。消费 upy-generate-plugin 的 phase_complete，支持 upload_only、clean_then_upload、erase_then_upload，上传 firmware、软复位、捕获 REPL 输出、读取设备日志、运行设备端测试、展示部署结果，并根据用户反馈进入 generate fix、autofix 或项目库上传。
---

# upy-deploy-plugin 插件化工作流

`upy-deploy-plugin` 是“一句话造硬件”流水线的项目部署与运行验证阶段。它不覆盖旧 `G:\MicroPython_Skills\upy-deploy`，也不重新烧录 MicroPython 解释器固件；解释器固件阶段仍由 `upy-flash-mpy-firmware-plugin` 负责。

本 phase 的正式名称完全统一为：

```text
upy-deploy-plugin
```

所有协议消息、`phase_complete.payload.phase`、`manifest_content.phase` 都必须使用这个值，不要混用 `deploy` 或 `upy-deploy`。

## 上游与下游

正式主链路：

```text
upy-analyze-plugin
-> upy-select-hw-plugin
-> upy-flash-mpy-firmware-plugin
-> upy-scaffold-plugin
-> upy-generate-plugin
-> upy-deploy-plugin
```

上游 `upy-generate-plugin` 成功且 deploy-ready 时必须输出 `next_phase="upy-deploy-plugin"`。如果 `next_phase=null`，必须有明确的 `next_phase_decision` 说明用户选择停止或存在 blocker，不能让 deploy 主链路靠人工修补。

部署完成后不直接静默结束，必须展示部署结果选项卡并读取用户反馈：

| 用户选择 | 行为 |
| --- | --- |
| 重新生成 | `upy-generate-plugin(mode=fix, source=user_feedback_after_deploy)` |
| 自动化调试 | `upy-autofix-plugin` |
| 结束并上传项目库 | 进入项目库上传/发布流程 |

FAIL 时优先进入 `upy-autofix-plugin`。如果 `upy-autofix-plugin` 未落地，可回到 `upy-generate-plugin(mode=fix, source=deploy_fail)`。

## 输入契约

启动消息：

```json
{
  "protocol_version": "1.0",
  "type": "start_phase",
  "phase": "upy-deploy-plugin",
  "session_id": "uuid",
  "idempotency_key": "upy-deploy-plugin:<session_id>:deploy:v1",
  "payload": {
    "phase": "upy-deploy-plugin",
    "source_phase": "upy-generate-plugin",
    "source_phase_complete_path": "sessions/<session_id>/phase_complete.upy_generate_plugin.json",
    "deploy_strategy": "clean_then_upload",
    "runtime_context": {
      "artifact_root": ".",
      "artifact_root_mode": "cwd",
      "session_root": "sessions/<session_id>",
      "project_root": "sessions/<session_id>/project",
      "resource_root": "<runtime-provided>"
    },
    "capabilities": {
      "approval_request": true,
      "file_operation": true,
      "script_run": true,
      "device_command": true,
      "serial_port_scan": true,
      "checkpoint_resume": true,
      "cancellation": true
    }
  }
}
```

上游 `phase_complete` 必须满足：

```text
type == "phase_complete"
payload.result == "success"
payload.next_phase == "upy-deploy-plugin"
payload.manifest_content.phase == "generate"
```

## 部署策略

`deploy_strategy` 支持：

| 值 | 含义 |
| --- | --- |
| `upload_only` | 不清理设备文件，直接上传当前项目 |
| `clean_then_upload` | 常规清理旧项目文件和业务目录，然后上传 |
| `erase_then_upload` | 清理设备端可列出的全部文件/目录后再上传；必须 dry-run 和二次确认 |

`erase_then_upload` 不等同于重新烧录 MicroPython 解释器固件。它只清理 MicroPython 文件系统中的文件/目录。

## 工作流程

1. 校验 `start_phase` 和上游 `phase_complete`。
2. 读取 `project_root`、`project-manifest.json`、`firmware/`、`tools/`。
3. 先运行 `scripts/check_environment.py` 检查 `mpremote` 运行时；如缺失，返回 `action_required` 和安装提示，不继续碰设备。
4. 使用插件内包装脚本 `scripts/list_serial_ports.py` 扫描串口；该脚本只转调公共实现 `shared-plugin-scripts/mpremote/list_serial_ports.py`，不复制维护串口扫描逻辑。
5. 发送 `approval_request(deploy_port_select)`，用户选择真实端口。
6. 发送 `approval_request(deploy_strategy_select)`，用户选择部署策略。
7. 如果选择清理：
   - `clean_then_upload`：运行 `scripts/clean_device_project.py --mode project_files --dry-run`。
   - `erase_then_upload`：运行 `scripts/clean_device_project.py --mode erase_all --dry-run`。
   - 展示待删除列表并等待确认。
   - 确认后再运行 `--execute`。
   - `project_files` 清理必须覆盖旧的生产禁止产物，包括 `conf.mpy`、`boot.mpy`、`main.mpy`、`board.mpy` 和 `drivers/**/mock.py|mock.mpy`，否则新上传即使过滤正确，设备仍可能运行旧文件。
8. 安装 generate 声明的运行时依赖：
   - 读取 `project-manifest.json` 或上游 `phase_complete.payload.manifest_content.runtime_dependencies.mip`。
   - 调用 `scripts/install_mip_dependencies.py --project-root <project_root> --manifest <phase_complete_or_manifest> --port <port> --output-json ...`。
   - 只使用 `mpremote mip install` 安装 MicroPython/micropython-lib 包；不要在 deploy 阶段把库源码 vendor 到项目。
   - 安装后必须用 `mpremote fs ls` 校验目标目录和包目录确实存在，例如 `:lib`、`:lib/unittest`，并把 `fs_verify` 写入结果。mip 可能安装预编译 `__init__.mpy` 而不是 `__init__.py`，这是合法落盘形式；校验脚本应接受 `.py` 或 `.mpy`，但必须保留 `matched_files` 证据。
   - 如果 `mip install` 因网络、代理或翻墙环境不可用失败，标记 `runtime_dependency_install_network_unavailable`，提示用户修复网络后重试，不要把它误判为 generate 代码错误。
   - 安装失败、导入验证失败或设备空间不足必须作为独立错误写入 `mip_install_result.json`，并交给 `deploy_result.py --mip-install-json ...` 汇总。
9. 上传项目文件：
   - `script_run` only resolves bundled plugin/shared scripts; do not call `project/tools/flash_device.py` through generic `script_run`. A project flash runner requires a dedicated plugin action.
   - In the current plugin loop, upload with bundled deploy scripts and `scripts/mpremote_runtime.py`; treat scaffold-rendered `project/tools/flash_device.py` as a user-facing convenience script for manual restore/debug outside the generic `script_run` resolver.
   - Upload with one bundled command: `python scripts/mpremote_runtime.py --run --port <port> --output-json upload_summary.json -- resume fs cp -r <source1> <source2> ... :`. Put all sources before the single final `:` target; do not generate `cp -r a : b : c :`.
   - 上传步骤必须输出结构化 `upload_summary.json`，deploy-plugin 只消费结构化结果。
   - 上传 summary 必须记录 `compiled_files`、`uploaded_files`、`skipped_files`。`conf.py`、`boot.py`、`main.py` 应作为 `.py` 上传，不得部署 `:conf.mpy` 或 `:boot.mpy`；`firmware/drivers/**/mock.py`/`mock.mpy` 是测试替身，不得部署到设备。
   - 即使项目工具返回 success，若 upload summary 或 `mpremote fs cp` 命令显示上传了 `:conf.mpy`、`:boot.mpy`、`:drivers/*/mock.py` 或 `:drivers/*/mock.mpy`，`deploy_result.py` 必须判 `FAIL`。
10. 软复位并等待重连：
   - `device_command(soft_reset)` 或白名单脚本。
   - `scripts/wait_for_device.py --port <port> --output-json ...`
11. 使用独立 `scripts/capture_repl.py` 捕获持久 REPL 输出。推荐在上传后调用 `scripts/capture_repl.py --reset-first --duration-ms <ms>`，让脚本等 mpremote attach 后先用 Ctrl-C interrupt 正在运行的 `main.py`，再发送 Ctrl-D soft reset，并持续读取启动期输出；不要先 reset/wait 再开始监听，否则会错过 `main.py` 启动期 traceback。
12. 读取设备端日志：
   - 部署前应提供日志策略选项：保留旧日志、读取并下载旧日志、清除旧日志后部署。
   - `project/tools/read_device_log.py`
   - `project/tools/log_report.py`
   - 清除日志只能在用户确认后调用项目工具的 `--clear` 或清理脚本的 `--include-logs`；默认不要静默删除旧日志。
13. 可选运行设备端契约测试：
   - 先发 `approval_request(run_device_tests)`。
   - 用户选择运行时调用 `scripts/run_device_tests.py --project-root <project_root> --port <port> --output-json ... --log-file ...`。
   - 测试文件来源为 `project/device/tests/test_*.py` 和 `project/test/device/test_*.py`。
   - 如果设备测试需要 `firmware/drivers/**/mock.py`，只能由 `run_device_tests.py` 作为临时测试 artifact 上传到设备、运行后删除，并用 `mpremote fs ls` 校验删除；不要把 mock 纳入生产 upload summary。
14. 上传和设备测试都会通过 raw REPL 控制设备，结束后必须再次让设备运行刚部署的应用。调用 `scripts/capture_repl.py --reset-first --no-resume --duration-ms <ms> --output-json final_reset_capture.json --log-file final_reset_capture.log`，把 Ctrl-C interrupt + Ctrl-D soft reset 后的启动输出保存为 final reset 证据。deploy success 表示“文件已上传且板子正在跑新应用”，不是只表示 `main.py` 存在于设备文件系统。final reset evidence accepts `final_reset_capture.json.observed_soft_reboot=true` or `final_reset_capture.json.observed_fresh_boot=true`；`reset_first=true` 只表示脚本尝试了 interrupt + soft reset，不表示设备真的 reboot。
   - The final reset restarts a board that is already running an app by sending Ctrl-C and then Ctrl-D, after mpremote has attached. Ctrl-D alone only reboots an IDLE REPL, so a running `main.py` swallows it, and keystrokes sent before the connect banner are echoed into nothing. `--no-resume` does not affect this: `mpremote resume` only suppresses the auto soft reset that raw-REPL commands perform, and the capture uses the friendly REPL either way.
   - The final reset is the last device operation in the deploy phase. Do not run `fs ls`, `resume exec`, another capture, or another test after it; those actions enter raw REPL and can stop `main.py` again. Use `upload_summary.json` and script artifacts for verification instead.
   - Do not verify startup with `resume exec import main` or `run_on_device.py --file main.py`; an application loop may never return, so those commands can only hang or stop the app.
15. 运行 `scripts/deploy_result.py` 生成结构化 deploy 判定；只传脚本支持的 flags：`--upload-json`、`--clean-json`、`--serial-json`、`--final-reset-json`、`--log-report-json`、`--device-tests-json`、`--mip-install-json`、`--strategy`、`--port`、`--output-json/--out-json`。Do not pass `--wait-json`、`--probe-json`、`--feedback-json`、`--phase` 或 `--manifest`。
16. 展示结果选项卡：
   - PASS 或 PASS_WITH_WARNINGS: `approval_request(deploy_result_feedback)`
   - FAIL 或 NEEDS_USER_CONFIRMATION: `approval_request(deploy_fail_next_action)`
17. 输出 `phase_complete` 前必须运行 `scripts/deploy_manifest.py --input <phase_complete> --validate-phase-complete`；失败时不得把 deploy 判为 success。

## approval_request

### deploy_port_select

必须展示扫描到的端口列表。真实运行不得固定 `COM3`；固定端口只能用于 sample/mock。

### deploy_strategy_select

必须包含：

```text
upload_only
clean_then_upload
erase_then_upload
save_partial
```

推荐默认选择 `clean_then_upload`。

### confirm_clean_device_project

展示 `clean_device_project.py --mode project_files --dry-run` 的待删除文件列表。

### confirm_erase_device_fs

展示 `clean_device_project.py --mode erase_all --dry-run` 的完整待删除文件/目录列表。用户必须二次确认。

### run_device_tests

上传、软复位、等待设备恢复和读取设备日志后，推荐询问是否运行设备端契约测试。默认建议运行，但必须允许跳过，因为部分项目的 device tests 可能触摸真实硬件，或者用户只想快速上传观察。

该请求至少提供：

```text
run_device_tests
skip_device_tests
save_checkpoint
```

运行结果保存为：

```text
device_tests_result.json
device_tests_output.log
```

### deploy_result_feedback

PASS 或 `PASS_WITH_WARNINGS` 后展示：

- 串口/设备。
- 部署策略。
- 清理结果。
- upload summary / `scripts/mpremote_runtime.py` 文件上传结果；不要把 `project/tools/flash_device.py` 当作插件循环里的 `script_run` 目标。
- soft reset / wait result。
- REPL 输出摘要。
- 设备端日志报告。
- device tests 结果。
- 初判 PASS 或 `PASS_WITH_WARNINGS`。

必须收集可选用户反馈文本，例如设备实际现象、mpremote 输出、串口报错、手动观察到的问题和设备日志摘要。用户选择重新生成时，必须传递 `error_context`。

### deploy_fail_next_action

FAIL 后展示同样的诊断摘要，并允许进入 `upy-autofix-plugin`、`upy-generate-plugin(mode=fix)` 或保存 checkpoint。进入 generate fix 时必须携带完整 `error_context`。

推荐 payload：

```json
{
  "mode": "fix",
  "source": "user_feedback_after_deploy",
  "error_context": {
    "user_feedback": "<user feedback text>",
    "deploy_result_path": "sessions/<session_id>/phase_complete.upy_deploy_plugin.json",
    "serial_excerpt": "<REPL or serial excerpt>",
    "device_log_excerpt": "<device log excerpt>",
    "device_tests_result_path": "sessions/<session_id>/device_tests_result.json",
    "deploy_errors": [],
    "previous_generate_commit": "<commit>"
  }
}
```

## 结果判定

`scripts/deploy_result.py` 必须综合 upload summary、clean result、REPL/serial capture、device log report、mip install result 和 device tests result。用户人工反馈属于 `deploy_result_feedback` / `deploy_fail_next_action` 的 `error_context`，不要作为 `deploy_result.py` 参数传入。

硬 FAIL 信号：

| 信号 | 结果 |
| --- | --- |
| upload failed | `FAIL` |
| clean failed | `FAIL` |
| mip dependency install/verify failed | `FAIL` |
| forbidden runtime upload (`:conf.mpy`, `:boot.mpy`, `:drivers/*/mock.py`, `:drivers/*/mock.mpy`) | `FAIL` |
| wait/probe failed | `FAIL` |
| REPL Traceback/panic/MemoryError/ValueError/OSError/ImportError/AttributeError | `FAIL` |
| log_report.error_count > 0 | `FAIL` |
| device tests failed | `FAIL` |
| upload/device tests 后缺少 final reset evidence、final reset 未观察到 soft reboot、final reset 捕获为空或卡住 | `FAIL` |

上传后串口/REPL 捕获为空不能作为 success 证据。如果已经上传代码但 `serial_capture` 或 `final_reset_capture` 为空、卡住，或者 device tests 后没有执行 `capture_repl.py --reset-first`，必须判 `FAIL` 或 `partial`，不能只凭设备上存在 `main.py` 报 PASS。对于 DHT11 等偶发读数超时，单次 timeout 可作为 warning；只有反复 timeout 且整段 capture 中没有任何成功读数时，才用 `device_io_timeout` 判 FAIL。

## 设备工具区

除主流程外，UI 可提供独立“设备工具”区域：

- 扫描串口。
- 连接/监听输出。
- 执行探测命令。
- 读取设备日志。
- 运行设备测试。
- 清理项目文件 dry-run。
- 全量 erase dry-run。

这些按钮不一定推进主链路，但输出都应该能附加到 `deploy_result_feedback`、`deploy_fail_next_action` 和 `upy-generate-plugin(mode=fix).error_context`。

## 脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/check_environment.py` | 检查 `mpremote`、可选 `pyserial` 和安装提示 |
| `scripts/mpremote_runtime.py` | deploy 插件内唯一 `mpremote` 进程适配层；解析 `UPY_MPREMOTE`、PATH、`python -m mpremote` |
| `scripts/list_serial_ports.py` | deploy 插件内串口扫描入口，薄包装到公共串口扫描脚本 |
| `shared-plugin-scripts/mpremote/list_serial_ports.py` | 公共串口扫描实现，供 flash/deploy 共同引用 |
| `scripts/deploy_manifest.py` | 校验 start/upstream/phase_complete |
| `scripts/clean_device_project.py` | dry-run/execute 清理设备文件 |
| `scripts/install_mip_dependencies.py` | 根据 `runtime_dependencies.mip` 执行 `mpremote mip install` 并验证 import |
| `scripts/wait_for_device.py` | soft reset 后等待设备恢复 |
| `scripts/capture_repl.py` | 持久 REPL 输出采集 |
| `scripts/run_device_tests.py` | 通过 `mpremote run` 执行设备端 unittest 文件并输出 JSON |
| `scripts/deploy_result.py` | 汇总 upload/mip install/serial/log/device tests report，判定 PASS/FAIL |
| `scripts/requirements-runtime.txt` | 运行时 pip 依赖清单：`mpremote`、`pyserial` |

## mpremote 约束

- 不把 pip 安装的 `mpremote` 包源码 vendor 到插件里；插件封装的是“如何发现、调用、报错和提示安装”。
- 所有 deploy 插件内脚本必须经由 `scripts/mpremote_runtime.py` 调用 `mpremote`，不要在各脚本里散落 `["mpremote", ...]`。
- `mpremote` 解析顺序：`UPY_MPREMOTE` 环境变量、PATH 中的 `mpremote`、当前 Python 的 `python -m mpremote`。缺失时返回 `action_required` 和 `python -m pip install mpremote`。
- MicroPython 运行时包必须使用 `mpremote mip install`，来源通常是 `micropython-lib` 或官方 mip 索引；deploy 不默认抓取源码到本地项目。
- `scripts/install_mip_dependencies.py` 先 probe `verify_import`，缺失时安装，安装后再次 probe。结果必须进入 `deploy_result.py --mip-install-json`。
- `mpremote mip install` 可能因为网络、代理或翻墙环境不可用而失败。此类失败必须分类为 `runtime_dependency_install_network_unavailable`，保留 stdout/stderr 摘要，并让 `deploy_result.py` 明确提示网络/代理/VPN 问题，而不是把它混同为普通 device test 失败。
- mip 安装不能只靠 import probe 判断完成。安装后必须使用 `mpremote fs ls` 校验目标目录和包目录，例如 `fs ls :lib`、`fs ls :lib/unittest`，确认 `__init__.py` 或 `__init__.mpy` 等关键文件落盘；递归子目录需要逐层列出。文件系统校验结果必须写入 `mip_install_result.json.records[].fs_verify`。
- 串口枚举统一调用 `scripts/list_serial_ports.py`；该脚本薄包装到 `shared-plugin-scripts/mpremote/list_serial_ports.py`，不再复制实现。
- 上传与文件系统操作必须优先使用 `mpremote connect <port> resume fs ...`，避免文件传输前隐式 soft reset。
- `scripts/mpremote_runtime.py` 支持人工调试 passthrough，例如 `mpremote_runtime.py --run --port <port> -- resume exec "print('hello')"`。
- 长时间监听、运行后输出采集和多轮交互必须使用持久会话模型；`scripts/capture_repl.py` 是 deploy 阶段的独立入口。
- `capture_repl.py` 默认等待 `MPYHW_READY` 或 `starting scheduler`。scaffold 模板会打印这两个标记；如果被部署的 `main.py` 两者都不打印，采集只会一直等到超时，此时的 `stalled` 并不能证明板子没跑起来。遇到这种情况用 `--stop-pattern` 指定该 `main.py` 真正会打印的字符串，不要把 `stalled` 直接当成部署失败。
- `mpremote resume exec` 只用于短探测或部署前清理这类一次性动作；不要用反复 `resume exec` 代替持久 REPL 监听。
- Windows 使用显式 `COMn`；macOS 使用 `/dev/tty.usbmodem*` 或 `/dev/tty.usbserial*`；Linux 优先 `/dev/serial/by-id/*` 或 mpy-dev 解析出的稳定路径。

## phase_complete

成功 payload 必须包含：

- `phase="upy-deploy-plugin"`
- `result="success"`
- `deploy_result`
- `manifest_content.phase="upy-deploy-plugin"`
- `manifest_content.deploy` 或 `manifest_content.deploy_result`
- `artifacts[]`
- `next_phase` 根据用户反馈选择

`manifest_content` 必须保留完整上游 manifest，再追加 deploy 事实，不得只写摘要。

`phase_complete.payload.deploy_result` 必须来自 `scripts/deploy_result.py` 的结构化结果或与其逐字段一致。LLM 可以总结结果，但不得把底层 `mip_install_result.json`、upload summary、device tests、log report 或 REPL capture 的 blocking failure 手工改写成 PASS。

success 的 `payload.artifacts` 必须引用独立原始证据文件：`deploy_result.json`、`upload_summary.json`、`clean_result.json`、`mip_install_result.json`、`device_tests_result.json`、`final_reset_capture.json`，以及串口/REPL capture 和设备日志报告。只把叙述性摘要或 `phase_complete` 自身列为 artifact 不合格。
Evidence JSON files must be emitted by their scripts, not written by `file_operation`: `deploy_result.json`, `upload_summary.json`, `clean_result.json`, `mip_install_result.json`, `device_tests_result.json`, and `final_reset_capture.json` are tool evidence, not model-authored summaries.
Each evidence artifact records `evidence_mode` as the exact literal `live` or `mock`. `clean_result.json.mode` remains the clean scope such as `project_files` or `erase_all`; do not infer whether evidence is mocked from that field.

`scripts/run_device_tests.py` 和 `scripts/deploy_result.py` 必须在本阶段真实执行过，然后才允许发 `phase_complete`。没有跑 `deploy_result.py` 就没有判定，这个阶段没有可以结束的依据，只会一路烧到 turn 上限。把脚本打印到 stdout 的内容再抄进同名文件，看起来一样，但证据链已经断了：时间戳、返回码、失败分类全部变成模型手写的值，校验对着这种文件只能全部通过，却什么都没有证明。脚本缺少落盘参数时，报 `action_required` 说明缺哪个参数，不要用手写文件替代。

## 强约束

- 不覆盖旧 `upy-deploy`。
- 不重刷 MicroPython 解释器固件。
- 不修改生成代码；修复交给 generate/autofix。
- 不在真实运行固定 `COM3`。
- 所有本地动作走 `script_run`、`device_command`、`file_operation` 或 `approval_request`。
- `erase_then_upload` 必须 dry-run 和二次确认。
- 长时间串口输出采集必须用持久会话思路，避免反复 `resume exec`。
- 证据文件一律由脚本落盘，不用 `file_operation write` 手工写；`run_device_tests.py` 与 `deploy_result.py` 未执行则不得 `phase_complete`。
- 不用 `resume exec` 导入应用入口（`import main` 等）；确认运行状态只用 `capture_repl.py --reset-first`。

## Final Boundary Addendum

- Treat `runtime_context.session_root`, `runtime_context.project_root`, and explicit `source_phase_complete_path` as the `workflow_session_root`. A separate session containing logs is a `diagnostic_log_session` and must not receive deploy artifacts unless the user explicitly makes it the workflow target.
- Deploy success means deployment-observation success, not code-generation correctness. A PASS requires upload/clean/mip/device probes/log report/device tests to have no blocking errors. A PASS does not authorize manual source edits during deploy.
- Deploy must not fix generated source code or mark success after ad-hoc debugging changes. Runtime code fixes go through `upy-autofix-plugin` or `upy-generate-plugin(mode=fix)` with a structured `error_context`.
- Deploy must not add broad Timer or peripheral semantic preflight. Timer and peripheral API correctness are generate gates. Deploy records evidence from upload summary, REPL capture, device logs, device tests, and user observation.
- Empty REPL output after upload is observation-incomplete, not proof that the deployed app is running. A deploy success path must have non-empty startup/final-reset evidence; otherwise return `FAIL` or `partial` and record the observation limitation. COM re-enumeration or user unplug/replug events should be recorded separately instead of being treated as successful runtime evidence.
- Forbidden runtime uploads are blocking even if the project upload tool says success: `:main.mpy`, `:boot.mpy`, `:conf.mpy`, `:firmware/**`, `__pycache__`, `*.pyc`, and `drivers/**/mock.py|mock.mpy`.
- Before upload, project_files clean must remove old deploy artifacts such as `main.mpy`, `boot.mpy`, `conf.mpy`, `board.mpy`, stale `drivers/**/mock.py|mock.mpy`, and old wrong-root `firmware/**` paths when present on device.
- MicroPython runtime packages from micropython-lib must be installed with `mpremote mip install`, then verified with import probes and `mpremote fs ls` on the relevant target folders such as `:lib` and `:lib/unittest`. Network/proxy/VPN failure is `runtime_dependency_install_network_unavailable`, not a generate code bug.
- `runtime_dependencies.mip[].asset_files` must also be checked during filesystem verification; for example, BMA423's uPyPi package must leave `bma423conf.bin` in `/lib` after `mpremote mip install`.
- Device-side unittest mocks are temporary test artifacts only. `scripts/run_device_tests.py` must record upload, cleanup, and cleanup verification for `firmware/drivers/**/mock.py`; production upload must still reject mocks.
- REPL capture should prefer reset-first capture when safe so startup tracebacks are visible. After device tests, run a final `capture_repl.py --reset-first` and include `final_reset_capture.json`; device file logs supplement REPL output but do not prove the board is running `main.py`.
- `deploy_fail_next_action` and `deploy_result_feedback` must carry `error_context` with deploy result path, serial excerpt, device log excerpt/report, device tests result path, mip install result, forbidden upload list, user observation, and previous generate commit when available.
