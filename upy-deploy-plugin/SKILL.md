---
name: upy-deploy-plugin
description: 插件化工作流版 MicroPython 项目部署和运行验证阶段。消费 upy-generate-plugin 的 phase_complete，支持 upload_only、clean_then_upload、erase_then_upload，上传 firmware、软复位、捕获 REPL 输出、读取设备日志、展示部署结果，并根据用户反馈进入 generate fix、autofix 或项目库上传。
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
8. 运行项目工具：
   - `project/tools/flash_device.py --compile --upload --no-reset --port <port> --json-summary`
   - `--json-summary` 是必需接口，deploy-plugin 只消费结构化结果。
9. 软复位并等待重连：
   - `device_command(soft_reset)` 或白名单脚本。
   - `scripts/wait_for_device.py --port <port> --output-json ...`
10. 使用独立 `scripts/capture_repl.py` 捕获持久 REPL 输出。
11. 读取设备端日志：
   - `project/tools/read_device_log.py`
   - `project/tools/log_report.py`
12. 运行 `scripts/deploy_result.py` 生成结构化 deploy 判定。
13. 展示结果选项卡：
   - PASS: `approval_request(deploy_result_feedback)`
   - FAIL: `approval_request(deploy_fail_next_action)`
14. 输出 `phase_complete`。

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

### deploy_result_feedback

PASS 后展示：

- 串口/设备。
- 部署策略。
- 清理结果。
- `flash_device.py --json-summary`。
- soft reset / wait result。
- REPL 输出摘要。
- 设备端日志报告。
- 初判 PASS。

用户选择下一步：重新生成、自动化调试、结束并上传项目库。

### deploy_fail_next_action

FAIL 后展示同样的诊断摘要，并允许进入 `upy-autofix-plugin`、`upy-generate-plugin(mode=fix)` 或保存 checkpoint。

## 脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/check_environment.py` | 检查 `mpremote`、可选 `pyserial` 和安装提示 |
| `scripts/mpremote_runtime.py` | deploy 插件内唯一 `mpremote` 进程适配层；解析 `UPY_MPREMOTE`、PATH、`python -m mpremote` |
| `scripts/list_serial_ports.py` | deploy 插件内串口扫描入口，薄包装到公共串口扫描脚本 |
| `shared-plugin-scripts/mpremote/list_serial_ports.py` | 公共串口扫描实现，供 flash/deploy 共同引用 |
| `scripts/deploy_manifest.py` | 校验 start/upstream/phase_complete |
| `scripts/clean_device_project.py` | dry-run/execute 清理设备文件 |
| `scripts/wait_for_device.py` | soft reset 后等待设备恢复 |
| `scripts/capture_repl.py` | 持久 REPL 输出采集 |
| `scripts/deploy_result.py` | 汇总 upload/serial/log report，判定 PASS/FAIL |
| `scripts/requirements-runtime.txt` | 运行时 pip 依赖清单：`mpremote`、`pyserial` |

## mpremote 约束

- 不把 pip 安装的 `mpremote` 包源码 vendor 到插件里；插件封装的是“如何发现、调用、报错和提示安装”。
- 所有 deploy 插件内脚本必须经由 `scripts/mpremote_runtime.py` 调用 `mpremote`，不要在各脚本里散落 `["mpremote", ...]`。
- `mpremote` 解析顺序：`UPY_MPREMOTE` 环境变量、PATH 中的 `mpremote`、当前 Python 的 `python -m mpremote`。缺失时返回 `action_required` 和 `python -m pip install mpremote`。
- 串口枚举统一调用 `scripts/list_serial_ports.py`；该脚本薄包装到 `shared-plugin-scripts/mpremote/list_serial_ports.py`，不再复制实现。
- 上传与文件系统操作必须优先使用 `mpremote connect <port> resume fs ...`，避免文件传输前隐式 soft reset。
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
