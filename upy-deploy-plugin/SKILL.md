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
   - 安装后必须用 `mpremote fs ls` 校验目标目录和包目录确实存在，例如 `:lib`、`:lib/unittest`，并把 `fs_verify` 写入结果。
   - 如果 `mip install` 因网络、代理或翻墙环境不可用失败，标记 `runtime_dependency_install_network_unavailable`，提示用户修复网络后重试，不要把它误判为 generate 代码错误。
   - 安装失败、导入验证失败或设备空间不足必须作为独立错误写入 `mip_install_result.json`，并交给 `deploy_result.py --mip-install-json ...` 汇总。
9. 运行项目工具：
   - `project/tools/flash_device.py --compile --upload --no-reset --port <port> --json-summary`
   - `--json-summary` 是必需接口，deploy-plugin 只消费结构化结果。
   - 上传 summary 必须记录 `compiled_files`、`uploaded_files`、`skipped_files`。`conf.py`、`boot.py`、`main.py` 应作为 `.py` 上传，不得部署 `:conf.mpy` 或 `:boot.mpy`；`firmware/drivers/**/mock.py`/`mock.mpy` 是测试替身，不得部署到设备。
   - 即使项目工具返回 success，若 upload summary 或 `mpremote fs cp` 命令显示上传了 `:conf.mpy`、`:boot.mpy`、`:drivers/*/mock.py` 或 `:drivers/*/mock.mpy`，`deploy_result.py` 必须判 `FAIL`。
10. 软复位并等待重连：
   - `device_command(soft_reset)` 或白名单脚本。
   - `scripts/wait_for_device.py --port <port> --output-json ...`
11. 使用独立 `scripts/capture_repl.py` 捕获持久 REPL 输出。推荐在上传后调用 `scripts/capture_repl.py --reset-first --duration-ms <ms>`，让脚本先进入 REPL、发送 Ctrl-D 软复位并持续读取启动期输出；不要先 reset/wait 再开始监听，否则会错过 `main.py` 启动期 traceback。
12. 读取设备端日志：
   - 部署前应提供日志策略选项：保留旧日志、读取并下载旧日志、清除旧日志后部署。
   - `project/tools/read_device_log.py`
   - `project/tools/log_report.py`
   - 清除日志只能在用户确认后调用项目工具的 `--clear` 或清理脚本的 `--include-logs`；默认不要静默删除旧日志。
13. 可选运行设备端契约测试：
   - 先发 `approval_request(run_device_tests)`。
   - 用户选择运行时调用 `scripts/run_device_tests.py --project-root <project_root> --port <port> --output-json ... --log-file ...`。
   - 测试文件来源为 `project/device/tests/test_*.py` 和 `project/test/device/test_*.py`。
14. 运行 `scripts/deploy_result.py` 生成结构化 deploy 判定。
15. 展示结果选项卡：
   - PASS 或 PASS_WITH_WARNINGS: `approval_request(deploy_result_feedback)`
   - FAIL 或 NEEDS_USER_CONFIRMATION: `approval_request(deploy_fail_next_action)`
16. 输出 `phase_complete`。

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
- `flash_device.py --json-summary`。
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

`scripts/deploy_result.py` 必须综合 upload summary、clean result、wait/probe result、REPL capture、device log report、device tests result 和用户人工反馈。

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

REPL 空输出不应直接判 FAIL。如果 serial 捕获为空，但上传/清理成功、日志报告 `error_count=0` 且 device tests 未失败，则输出 `PASS_WITH_WARNINGS` 并加入 warning，例如 `serial capture produced no output`。这是因为应用可能只写 rotating file logger，或运行时没有 stdout。

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
- mip 安装不能只靠 import probe 判断完成。安装后必须使用 `mpremote fs ls` 校验目标目录和包目录，例如 `fs ls :lib`、`fs ls :lib/unittest`，确认 `__init__.py` 等关键文件落盘；递归子目录需要逐层列出。文件系统校验结果必须写入 `mip_install_result.json.records[].fs_verify`。
- 串口枚举统一调用 `scripts/list_serial_ports.py`；该脚本薄包装到 `shared-plugin-scripts/mpremote/list_serial_ports.py`，不再复制实现。
- 上传与文件系统操作必须优先使用 `mpremote connect <port> resume fs ...`，避免文件传输前隐式 soft reset。
- `scripts/mpremote_runtime.py` 支持人工调试 passthrough，例如 `mpremote_runtime.py --run --port <port> -- resume exec "print('hello')"`。
- 长时间监听、运行后输出采集和多轮交互必须使用持久会话模型；`scripts/capture_repl.py` 是 deploy 阶段的独立入口。
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

## 强约束

- 不覆盖旧 `upy-deploy`。
- 不重刷 MicroPython 解释器固件。
- 不修改生成代码；修复交给 generate/autofix。
- 不在真实运行固定 `COM3`。
- 所有本地动作走 `script_run`、`device_command`、`file_operation` 或 `approval_request`。
- `erase_then_upload` 必须 dry-run 和二次确认。
- 长时间串口输出采集必须用持久会话思路，避免反复 `resume exec`。
