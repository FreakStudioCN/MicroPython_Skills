---
name: upy-flash-mpy-firmware-plugin
description: 插件化工作流版 MicroPython 固件解析、下载、烧录或手动确认。用于 Codex 收到 next_phase=upy-flash-mpy-firmware-plugin 的 phase_complete(select-hw) 时；消费 select-hw manifest_content，从 micropython.org/download 解析最新固件，协助 ESP32 esptool 烧录，引导 Pico UF2 复制，或为其他板卡提供手动烧录链接，最后输出 next_phase=upy-scaffold-plugin。
---

# MicroPython 固件烧录阶段

## 角色定位

`upy-flash-mpy-firmware-plugin` 是 `select-hw` 后的插件化阶段。它只消费 `phase_complete.select_hw.json`，不重新分析需求、不重新选板卡、不生成业务代码。

输入事实源：

```text
sessions/<session_id>/phase_complete.select_hw.json
```

成功输出：

```text
phase_complete(payload.phase="upy-flash-mpy-firmware-plugin", payload.next_phase="upy-scaffold-plugin")
```

## 板卡分支

| 分支 | 条件 | 行为 |
| --- | --- | --- |
| ESP32 | `firmware_board_name` 以 `ESP32_` 开头、`firmware.port == "esp32"`，或 `chip_family` 以 `esp32` 开头 | 解析最新 `.bin`，从 MicroPython 板卡页面解析安装命令，扫描/选择真实串口，并且只在用户确认后运行 `esp32_flash.py`。 |
| Pico | `firmware_board_name` 以 `RPI_PICO` 开头 | 解析最新 `.uf2`，提示用户按住 BOOTSEL 并复制 UF2，然后等待用户确认。 |
| Manual | 其他 MicroPython 板卡 | 解析 MicroPython 下载/安装链接并展示手动烧录说明。不要执行 `dfu-util`、`teensy-loader`、ESP8266 esptool 或其他工具，只等待用户确认。 |

Only mock/sample tests may use a fixed `serial_port="COM3"` to validate JSON and command planning. Claude Code live use and real plugin use must scan real serial ports and require user selection. 上面这两个英文短语是本地测试契约；含义是只有 mock/sample 测试可用固定串口（例如 Windows `COM3`、Linux `/dev/ttyUSB0` 或 macOS `/dev/cu.usbmodem1101`），真实 Claude Code 或插件运行必须扫描真实串口并由用户选择。

## 输入契约

推荐的 `start_phase` payload：

```json
{
  "protocol_version": "1.0",
  "msg_id": "uuid",
  "session_id": "<session_id>",
  "phase": "upy-flash-mpy-firmware-plugin",
  "timestamp": "<runtime-utc-now>",
  "type": "start_phase",
  "idempotency_key": "upy-flash-mpy-firmware-plugin:<session_id>:start:v1",
  "retry_of": null,
  "payload": {
    "phase": "upy-flash-mpy-firmware-plugin",
    "source_phase": "select-hw",
    "source_phase_complete_path": "sessions/<session_id>/phase_complete.select_hw.json",
    "runtime_context": {
      "artifact_root": ".",
      "artifact_root_mode": "cwd",
      "session_root": "sessions/<session_id>",
      "resource_root": "<runtime-provided>"
    },
    "capabilities": {
      "protocol_versions": ["1.0"],
      "approval_request": true,
      "script_run": true,
      "file_operation": true,
      "network_access": {
        "allowed": true,
        "domains": ["micropython.org", "docs.micropython.org"]
      },
      "web_search": true,
      "serial_port_scan": true,
      "device_flash": true,
      "relative_paths": true,
      "artifact_root": true
    },
    "firmware_action": null,
    "firmware_override": null
  }
}
```

字段规则：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `source_phase_complete_path` | 文件模式必填 | 上游 `phase_complete.select_hw.json` 的相对路径。 |
| `payload.source_phase_complete` | 可选 | 完整上游消息信封；宿主直接传 JSON 而不是路径时使用。 |
| `runtime_context.artifact_root` | 是 | 用于解析相对产物路径的产物根目录。 |
| `runtime_context.artifact_root_mode` | 是 | `cwd` 或 `session_root`；同一个 `phase_complete` 内不要混用路径口径。 |
| `runtime_context.session_root` | 是 | 相对会话目录，通常是 `sessions/<session_id>`。 |
| `runtime_context.resource_root` | 是 | 已安装技能/资源所在根目录；用它定位本技能脚本。 |
| `capabilities.script_run` | 是 | 宿主可运行白名单技能脚本。 |
| `capabilities.network_access` | 是 | 宿主可访问 MicroPython 下载页面。 |
| `capabilities.serial_port_scan` | ESP32 真实烧录时必填 | 宿主可枚举串口。 |
| `capabilities.device_flash` | ESP32 真实烧录时必填 | 宿主允许用户确认后执行擦除/写入。 |
| `firmware_action` | 可选 | `download_and_flash`、`download_only`、`already_flashed`、`use_local_firmware`、`save_partial` 或 `cancel`。 |
| `firmware_override` | 可选 | 用户提供的 `local_path`、`url`、`file_type` 和 `source`。 |

必须校验上游消息信封：

```text
protocol_version == "1.0"
type == "phase_complete"
phase == "select-hw"
payload.phase == "select-hw"
payload.result == "success"
payload.next_phase == "upy-flash-mpy-firmware-plugin"
payload.manifest_content.phase == "select-hw"
```

仅迁移期本地测试可在显式传入 `--allow-legacy-next-phase` 时接受旧值 `payload.next_phase == "flash-mpy-firmware"`；正式输出不得再写旧值。

## 板卡事实

只从 `phase_complete.select_hw.json.payload.manifest_content` 读取板卡事实。

字段优先级：

| 取值 | 优先来源 | 兜底来源 |
| --- | --- | --- |
| 固件 URL | `hardware_selection.selected_board.firmware.url` | `mcu.firmware_url`；如果都缺失，才用固件板卡名到 MicroPython 下载索引匹配真实下载页。 |
| 固件板卡名 | `hardware_selection.selected_board.firmware.board_name` | `mcu.firmware_board_name` |
| 固件 port | `hardware_selection.selected_board.firmware.port` | 从板卡名推断 |
| 芯片族 | `hardware_selection.selected_board.chip_family` | `mcu.chip_family` |
| 烧录工具提示 | `mcu.flash_tool` | 从板卡族推断 |
| 展示名称 | `hardware_selection.selected_board.display_name` | `mcu.display_name` |

不要信任缓存的 `latest_version`。运行时必须优先使用上游 `hardware_selection.selected_board.firmware.url`，其次使用 `mcu.firmware_url`，访问该 MicroPython 官方板卡页解析真实 `(latest)` 固件和安装说明。只有当上游 URL 缺失或无效时，才使用 `firmware_board_name` 到 `https://micropython.org/download/` 首页匹配真实下载页 slug。不要用 `display_name`、`board_id` 或 MCU 型号直接拼 URL。

固件页相关字段含义：

| 字段 | 用途 |
| --- | --- |
| `firmware.url` / `mcu.firmware_url` | MicroPython 官方固件页 URL，正常主路径。 |
| `firmware.board_name` / `mcu.firmware_board_name` | MicroPython 固件板卡名，用于展示和 URL 缺失时的兜底匹配。 |
| `display_name` | 给用户看的板卡名，不用于拼下载 URL。 |
| `board_id` | 本地板卡库 ID，不用于拼下载 URL。 |
| `download_slug` | 从固件 URL path 提取或从下载首页匹配出的真实 MicroPython 下载页 slug。 |
| `board_url` | 规范化后的 MicroPython 板卡页 URL。 |

## JSON 输出语言约定

`SKILL.md` 的说明段落、规则解释和字段含义表必须尽量使用中文；JSON 示例必须按 `upy-analyze-plugin`、`upy-select-hw-plugin` 的 sample 和真实 session 产物保持英文/中文混合格式。

- JSON key、协议字段、枚举值、动作值、错误码、文件名、脚本参数和路径保持英文或原样，例如 `payload`、`result`、`download_and_flash`、`firmware_action_select`、`missing_firmware_url`。
- 用户可见 UI 文案使用中文，例如 `header`、`question`、`actions[].label`、`steps[]`、`links[].label`。
- 项目语义文本优先中文，例如 `summary`、`description`、`message`、`warnings[]`、`notes`、`manual_flash_instructions` 中展示给用户的说明。
- 机器分类和来源保持英文，例如 `source`、`status`、`action`、`file_type`、`flash_method`、`reason`、`structured_errors[].code`。
- 上游 `source_phase_complete.payload.manifest_content` 必须原样保留 `select-hw` 阶段输出语言，不要为了统一文案而翻译项目名、器件名、驱动包名、API 名称或用户输入。
- `errors[]` 可以保留脚本/校验器英文原始错误；`structured_errors[].message` 如果由插件/LLM 面向用户生成，优先中文，若直接透传脚本原始错误可保留英文。

## 工作流程

1. 发送 `status_update(upstream_select_hw_loaded)`。
2. 加载并校验上游 `phase_complete.select_hw.json`。
3. 发送 `status_update(firmware_board_resolved)`。
4. 如果缺少 `firmware_action`，发送 `approval_request(firmware_action_select)` 并等待用户输入。
5. 如果用户选择 `already_flashed`，输出 `success`，并设置 `firmware.status="skipped_user_confirmed"`。
6. 如果用户选择 `save_partial`、超时或取消，输出带 checkpoint 的 `partial`。
7. 使用 `scripts/firmware_page_resolve.py` 解析 MicroPython 板卡页面；正常从上游固件 URL 传 `--board-url`，只有 URL 缺失时才用 `--download-index-url` 和 `--board-name` 兜底匹配下载页。
8. 除非提供 `firmware_override.local_path` 或分支是 manual-only，否则用 `scripts/firmware_download.py` 下载固件。
9. 进入选定板卡分支。
10. 使用 `scripts/flash_mpy_firmware_manifest.py` 校验阶段输出。
11. 输出最终 `phase_complete`。

## approval_request: firmware_action_select

除非 `start_phase.payload.firmware_action` 已经存在，否则任何下载或烧录动作前都必须先发这个审批。

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "firmware_action_select",
    "header": "MicroPython 固件准备",
    "question": "请选择本次固件阶段要执行的操作",
    "summary": {
      "board_name": "ESP32_GENERIC_C3",
      "display_name": "ESP32-C3-DevKitM-1",
      "firmware_page": "https://micropython.org/download/ESP32_GENERIC_C3/"
    },
    "actions": [
      {"label": "下载并烧录", "value": "download_and_flash", "primary": true},
      {"label": "只下载固件", "value": "download_only"},
      {"label": "我已自行烧录，跳过", "value": "already_flashed"},
      {"label": "使用本地固件文件", "value": "use_local_firmware"},
      {"label": "稍后继续", "value": "save_partial"},
      {"label": "取消", "value": "cancel"}
    ]
  }
}
```

## Claude Code 本地运行注意事项

插件协议中的 `approval_request.actions` 可以保留完整动作集合；但 Claude Code 的 `AskUserQuestion` 每个问题最多只能传 4 个 `options`。在 Claude Code 本地运行时，不要把上面的 6 个动作直接映射到一个 `AskUserQuestion`。

本地运行 `firmware_action_select` 时优先展示 4 个主动作：

```text
download_and_flash
download_only
already_flashed
use_local_firmware
```

`save_partial` 和 `cancel` 在插件 approval UI 中保留；Claude Code 本地运行可通过二次确认、普通对话或后续 checkpoint 写入处理。

Windows 下用临时 Python one-liner 读取 JSON 时，必须显式指定 UTF-8，例如 `open(path, encoding="utf-8")`，或在运行环境设置 `PYTHONUTF8=1`。不要用默认 `open(path)` 读取包含中文的 JSON。

调用 `firmware_download.py` 时必须传 `--out-dir`；`--output-json` 和 `--out-json` 只是输出 manifest 参数别名，不能替代下载目录。

`phase_complete.payload.artifacts` 必须写成数组，且数组中包含 `type="file_list"` 的对象；不要写成 `{ "file_list": [...] }` 对象，也不要写成扁平文件数组。

辅助脚本如果为了执行保留本机绝对路径，也必须同时输出可移植的相对产物字段，供下游协议消费：
- `firmware_download.py` 传入 `--artifact-root <artifact_root>` 时，输出 `downloaded_artifact_path`，相对该 artifact root。
- `esp32_flash.py` 传入 `--artifact-root <artifact_root>` 时，输出 `firmware_artifact_path`；执行日志本身的 artifact 路径由最终 `phase_complete.payload.firmware.flash_result.log` 声明。
- 下游插件只能消费相对 artifact 字段和最终 `phase_complete`，不要读取 helper JSON 中的本机绝对执行路径作为项目事实。

## ESP32 流程

必须先解析 MicroPython 页面中的安装说明。不要把硬编码 offset 作为主要来源；例如 `ESP32_GENERIC_C5` 当前使用 `write_flash 0x2000`，所以固定 C 系列 offset 是错误的。

脚本顺序：

```text
script_run(firmware_page_resolve.py --board-family esp32 --out-json ...)
script_run(firmware_download.py --resolved-json ... --out-dir ... --output-json ...)
script_run(list_serial_ports.py --output-json ...)  # 真实/插件模式
approval_request(esp32_flash_confirm)
script_run(bootstrap_esptool.py --output-json ...)  # 检查；status=missing 表示需要安装许可，不是失败
script_run(bootstrap_esptool.py --install --output-json ...)  # 只在需要安装且获得许可后运行
script_run(esp32_flash.py --plan-only --output-json ...)
script_run(esp32_flash.py --execute --output-json ...)  # 只允许在用户明确确认后执行
```

`approval_request(esp32_flash_confirm)` 必须包含：

- 固件文件名和 MicroPython 板卡页面。
- 从页面解析出的擦除/写入命令和 `write_offset`。
- 真实/插件模式下从真实扫描得到的串口选项。
- 下载模式提示：通常按住 BOOT，按 EN/RESET，再松开 BOOT；如果板卡说明不同，提醒用户按板卡说明操作。
- 明确警告：烧录会擦除并重写 MicroPython 固件。

期望的审批响应：

```json
{
  "type": "approval_response",
  "payload": {
    "approval_id": "esp32_flash_confirm",
    "action": "flash_now",
    "serial_port": "COM3",
    "baud": 460800
  }
}
```

上面的 `COM3` 只是 Windows 示例；Linux 常见值类似 `/dev/ttyUSB0` 或 `/dev/ttyACM0`，macOS 常见值类似 `/dev/cu.usbmodem1101` 或 `/dev/cu.usbserial-0001`。真实使用必须用扫描到且由用户选择的串口，不要按操作系统写死端口名。

## Pico 流程

解析并下载最新 `.uf2`；不要运行烧录命令。

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "pico_uf2_drag_drop",
    "header": "复制 Pico UF2 固件",
    "question": "请按住 BOOTSEL 连接 Pico，把 UF2 文件复制到 RPI-RP2 磁盘，完成后确认",
    "summary": {
      "board_name": "RPI_PICO_W",
      "firmware_file": "sessions/<session_id>/firmware/<file>.uf2"
    },
    "steps": [
      "断开 Pico USB",
      "按住 BOOTSEL 并重新连接 USB",
      "把 UF2 文件复制到 RPI-RP2 磁盘",
      "等待开发板自动重启"
    ],
    "actions": [
      {"label": "已复制并重启", "value": "copied_uf2", "primary": true},
      {"label": "稍后继续", "value": "save_partial"},
      {"label": "取消", "value": "cancel"}
    ]
  }
}
```

V0 中，用户确认 `copied_uf2` 即可视为成功。

跨平台挂载路径只作为提示和可选辅助发现，不改变 V0 手动复制契约：

- Windows 通常显示为卷标 `RPI-RP2` 的可移动磁盘。
- macOS 通常是 `/Volumes/RPI-RP2`。
- Linux 常见路径是 `/media/$USER/RPI-RP2`、`/run/media/$USER/RPI-RP2` 或 `/mnt/RPI-RP2`。
- 可选运行 `scripts/find_uf2_mount.py --output-json ...` 帮助定位挂载点；不得因为未找到挂载点就自动判定 Pico 流程失败，除非用户也没有确认 `copied_uf2`。

## 手动板卡流程

对非 ESP32/Pico 板卡，只解析 MicroPython 板卡链接并展示手动说明。不要执行 `dfu-util`、`teensy-loader`、ESP8266 esptool 等工具提示。

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "manual_firmware_flash_confirm",
    "header": "请按说明手动烧录 MicroPython 固件",
    "question": "请打开下面链接，按官方说明完成固件烧录；完成后点击确认。",
    "summary": {
      "board_name": "PYBV11",
      "firmware_page": "https://micropython.org/download/PYBV11/",
      "latest_firmware_url": "https://micropython.org/resources/firmware/<file>",
      "flash_method": "manual"
    },
    "links": [
      {"label": "MicroPython 固件下载页", "url": "https://micropython.org/download/PYBV11/", "source": "micropython_official"}
    ],
    "steps": [
      "下载页面中标记为 latest 的固件。",
      "按官方说明让开发板进入固件烧录模式。",
      "使用页面或厂商说明推荐的工具完成烧录。",
      "设备重启后回到插件窗口点击确认。"
    ],
    "actions": [
      {"label": "确认固件已烧录完毕", "value": "confirm_flashed", "primary": true},
      {"label": "稍后继续", "value": "save_partial"},
      {"label": "取消", "value": "cancel"}
    ]
  }
}
```

手动烧录审批字段含义：

| 字段 | 含义 |
| --- | --- |
| `approval_id` | 固定为 `manual_firmware_flash_confirm`。 |
| `summary.board_name` | 上游固件板卡名。 |
| `summary.download_slug` | 实际解析到的 MicroPython 下载页 slug，可选。 |
| `summary.firmware_page` | MicroPython 官方板卡页 URL。 |
| `summary.latest_firmware_url` | 页面中标记为 latest 的主固件链接。 |
| `summary.latest_version` | latest 固件版本，例如 `v1.28.0`。 |
| `summary.latest_date` | latest 固件日期，例如 `2026-04-06`。 |
| `summary.file_type` | 固件类型，例如 `dfu`、`uf2`、`bin`、`hex` 或 `zip`。 |
| `summary.flash_method` | 固定为 `manual`。 |
| `summary.tool_hint` | 页面说明中提取的工具或方式，例如 `dfu-util`、`st-flash`、`uf2-drag-drop`、`teensy-loader`、`ftp-copy` 或 `manual`。 |
| `links[]` | 下载页、latest 固件、官方文档、工具文档等链接。 |
| `steps[]` | 面向用户的中文步骤，来自官方安装说明摘要。 |
| `commands[]` | 可选；只展示页面命令，不自动执行；每项必须标记 `execute_allowed=false`。 |
| `warnings[]` | 手动烧录风险提示。 |
| `actions[]` | `confirm_flashed`、`save_partial`、`cancel`。 |

## 脚本

允许的白名单脚本：

| 脚本 | 用途 |
| --- | --- |
| `scripts/firmware_page_resolve.py` | 解析 MicroPython 下载页、最新固件 URL 和安装说明；支持 `--html-file` 用于 mock 测试。 |
| `scripts/firmware_download.py` | 下载已解析的固件产物，或输出不下载的计划。 |
| `scripts/list_serial_ports.py` | 为 ESP32 真实/插件模式枚举串口；优先使用 pyserial，失败时在 Windows/macOS/Linux 使用平台兜底。 |
| `scripts/find_uf2_mount.py` | 可选发现 Pico/RP2040 UF2 挂载点；只报告 `RPI-RP2` 等候选路径，不自动复制固件。 |
| `scripts/bootstrap_esptool.py` | 创建/检查技能内 `.venv-esptool`，并在获得许可后安装固定版本 esptool。 |
| `scripts/esptool_runner.py` | 运行技能内 `python -m esptool`，不依赖全局 PATH。 |
| `scripts/esp32_flash.py` | 使用从 MicroPython 页面解析出的命令规划或执行 ESP32 擦除/写入。 |
| `scripts/flash_mpy_firmware_manifest.py` | 校验 start/state/phase_complete 消息信封和产物路径。 |

最小校验模式：

```text
flash_mpy_firmware_manifest.py --validate-start-phase --input <start_phase.json>
flash_mpy_firmware_manifest.py --validate-upstream --input <phase_complete.select_hw.json>
flash_mpy_firmware_manifest.py --validate-state --input <flash_mpy_firmware_state.json>
flash_mpy_firmware_manifest.py --validate-phase-complete --input <phase_complete.json> --artifact-root <artifact_root>
```

`scripts/requirements-esptool.txt` 固定 esptool 包版本。不要要求插件直接调用全局 `esptool`。

脚本参数约定：

| 脚本 | 必填输入 | 输出参数 |
| --- | --- | --- |
| `firmware_page_resolve.py` | `--board-name`、`--board-family`，通常还要 `--board-url` | `--out-json`；也兼容 `--output-json`。 |
| `firmware_download.py` | `--resolved-json`、`--out-dir` | `--output-json`；也兼容 `--out-json`；建议传 `--artifact-root` 以输出相对 `downloaded_artifact_path`。 |
| `list_serial_ports.py` | 无；mock 测试可加 `--mode mock --mock-port COM3`、`--mock-port /dev/ttyUSB0` 或 `--mock-port /dev/cu.usbmodem1101` | `--output-json`；也兼容 `--out-json`。 |
| `find_uf2_mount.py` | 可选；默认查找 `RPI-RP2`，测试可加 `--candidate <path>` | `--output-json`；也兼容 `--out-json`。 |
| `bootstrap_esptool.py` | 无；需要安装时加 `--install` | `--output-json`；也兼容 `--out-json`。 |
| `esp32_flash.py` | `--resolved-json`、`--firmware`、`--port` | `--output-json`；也兼容 `--out-json`；建议传 `--artifact-root` 以输出相对 `firmware_artifact_path`。 |

调用时优先使用上表的 canonical 输出参数；兼容别名只用于容错，不要在文档新示例中混用。

## 产物

产物写入 `sessions/<session_id>/` 下：

```text
flash_mpy_firmware_state.json
firmware_page_resolved.json
firmware_download.json
firmware/<downloaded-file>
serial_ports.json
esptool_plan.json
flash_esp32_log.json
manual_flash_instructions.json
phase_complete.upy_flash_mpy_firmware_plugin.json
```

调试时可以额外写入 `flash_mpy_firmware_phase_log.md`，用于本机复盘完整执行过程；它不是必须产物，不要求写入 `phase_complete.payload.artifacts`。

`esptool_bootstrap.json` 是本地辅助调试文件，用于记录技能内 esptool 环境检查或安装结果；它不是正式阶段产物，除非后续协议明确要求，否则不写入 `phase_complete.payload.artifacts`。

`phase_complete.payload.artifacts` 必须包含 `file_list`，并列出当前分支产生的全部正式产物。固件文件、烧录日志、checkpoint state 等被 `firmware.file`、`firmware.flash_result.log` 或 `checkpoint.state_file` 引用的文件必须在 artifacts 中声明。产物路径必须相对 `artifact_root`；不要把本机技能安装路径写入正式 artifact 路径。

`phase_complete.payload.artifacts[].files[].description` 中的阶段名必须使用正式插件名 `upy-flash-mpy-firmware-plugin`。不要写旧名称 `flash-mpy-firmware`，例如 state 文件说明应写 `upy-flash-mpy-firmware-plugin 阶段状态文件`。

`bootstrap_esptool.py` 不带 `--install` 时是检查模式；如果技能内 `.venv-esptool` 不存在，脚本输出 `status="missing"`、`action_required="install"` 并返回 0。这是可恢复状态，不要当作阶段失败。只有用户确认允许安装后，才运行 `bootstrap_esptool.py --install`。ESP32 分支推荐顺序是：确认烧录 -> bootstrap 检查/安装 -> `esp32_flash.py --plan-only` -> `esp32_flash.py --execute`，这样 `esptool_plan.json.tool_version` 能反映真实环境。

## state 文件

`flash_mpy_firmware_state.json` 用于恢复、重试和排错，不是阶段完成消息。不要把 `status` 写成 `phase_complete`；阶段完成由最终 `type="phase_complete"` 文件表达。

state 顶层字段必须包含：

| 字段 | 含义 |
| --- | --- |
| `protocol_version` | 固定为 `1.0`。 |
| `msg_id` | 可选但建议写入，唯一消息 ID。 |
| `session_id` | 当前会话 ID。 |
| `phase` | 固定为 `upy-flash-mpy-firmware-plugin`。 |
| `status` | `in_progress`、`partial`、`success`、`failed` 或 `cancelled`。 |
| `type` | 可选但建议写入 `state`。 |
| `source_phase_complete_path` | 上游 `phase_complete.select_hw.json` 的相对路径。 |
| `payload` | 当前阶段事实，建议把板卡、固件、串口、烧录结果放在这里。 |
| `checkpoint` | `partial`/`failed` 且可恢复时写入。 |

成功态示例：

```json
{
  "protocol_version": "1.0",
  "msg_id": "uuid",
  "session_id": "<session_id>",
  "phase": "upy-flash-mpy-firmware-plugin",
  "status": "success",
  "timestamp": "<runtime-utc-now>",
  "type": "state",
  "source_phase_complete_path": "sessions/<session_id>/phase_complete.select_hw.json",
  "payload": {
    "phase": "upy-flash-mpy-firmware-plugin",
    "firmware_action": "download_and_flash",
    "board_name": "ESP32_GENERIC_C3",
    "board_url": "https://micropython.org/download/ESP32_GENERIC_C3/",
    "download_slug": "ESP32_GENERIC_C3",
    "chip_family": "esp32c3",
    "firmware_file": "sessions/<session_id>/firmware/ESP32_GENERIC_C3-20260406-v1.28.0.bin",
    "firmware_version": "v1.28.0",
    "firmware_date": "2026-04-06",
    "file_type": "bin",
    "serial_port": "COM88",
    "flash_result": {
      "tool": "esptool",
      "tool_version": "4.11.0",
      "port": "COM88",
      "baud": 460800,
      "write_offset": "0",
      "erased_first": true,
      "chip": "esp32c3",
      "log": "sessions/<session_id>/flash_esp32_log.json"
    }
  }
}
```

## 断点与错误

当用户选择稍后继续/取消、审批超时、选择只下载、网络暂时不可用、未选择串口或手动烧录未确认时，使用 `result=partial`、`next_phase=null`，并写入 checkpoint。

checkpoint 结构：

```json
{
  "checkpoint": {
    "resume_step": "confirm_esp32_flash",
    "reason": "waiting_user_approval",
    "state_file": "sessions/<session_id>/flash_mpy_firmware_state.json"
  }
}
```

`resume_step` 取值：

```text
load_upstream_select_hw
select_firmware_action
resolve_firmware_page
download_firmware
scan_serial_ports
confirm_esp32_flash
run_esp32_flash
wait_pico_uf2_copy
manual_firmware_flash_confirm
phase_complete_validation
```

结构化错误字段：

| 字段 | 含义 |
| --- | --- |
| `code` | 稳定、机器可读的错误码。 |
| `message` | 给用户或开发者看的错误说明；插件/LLM 生成时优先中文，直接透传脚本原始错误时可保留英文。 |
| `severity` | `info`、`warning`、`error` 或 `fatal`。 |
| `recoverable` | 是否可以重试/恢复。 |
| `retryable` | 是否可以用同一动作和参数重试。 |
| `source` | 产生错误的脚本或阶段步骤。 |
| `field` | 可选 JSON 字段路径。 |

建议错误码：

```text
invalid_upstream_phase
missing_firmware_url
firmware_page_lookup_failed
latest_firmware_not_found
download_failed
user_saved_partial
user_cancelled
serial_port_missing
esptool_failed
pico_copy_not_confirmed
manual_flash_not_confirmed
artifact_missing
absolute_path_in_artifact
phase_complete_invalid
```

## `phase_complete`

成功 payload 必须同时包含 `firmware` 和完整的 `manifest_content`：

- `firmware` 是本阶段摘要，保留给 UI、日志和轻量校验使用。
- `manifest_content` 必须从上游 `select-hw` 的完整 `payload.manifest_content` 复制而来，不要丢弃 `project_name`、`requirements`、`devices`、`mcu`、`hardware_selection` 等项目事实。
- 成功时必须在复制后的 `manifest_content` 上追加/覆盖：
  - `phase="upy-flash-mpy-firmware-plugin"`
  - `firmware_flash=<payload.firmware 的同等固件事实>`
  - `final_status="firmware_ready"`
  - `updated_at="<runtime-utc-now>"`
- `manifest_content.firmware_flash` 必须和 `payload.firmware` 的关键字段一致，至少包括 `status`、`action`、`board_name`、`board_url`、`source`、`flash_method`；如果已解析或生成 `latest_url`、`file`、`file_type`、`flash_result`，也要一并保留并保持一致。
- 成功 payload 必须带来源链路：`source_phase="select-hw"` 和 `source_phase_complete_path="sessions/<session_id>/phase_complete.select_hw.json"`。
- 已解析 latest 固件时，`payload.firmware` 与 `manifest_content.firmware_flash` 必须带 `latest_version` 和 `latest_date`。
- ESP32 成功烧录时，`payload.firmware.flash_result` 与 `manifest_content.firmware_flash.flash_result` 必须包含 `baud`、`chip` 和统一的 `write_offset`；`write_offset` 使用 MicroPython 页面解析到的命令参数原值，例如 `"0"`，不要在同一阶段内混用 `"0"` 和 `"0x0"`。
- `partial` 和 `failed` 可以不输出 `manifest_content`，但如果输出，不得把 `next_phase` 写成 `upy-scaffold-plugin`。

```json
{
  "phase": "upy-flash-mpy-firmware-plugin",
  "result": "success",
  "summary": "MicroPython 固件烧录阶段完成",
  "next_phase": "upy-scaffold-plugin",
  "firmware": {
    "status": "flashed",
    "action": "download_and_flash",
    "board_name": "ESP32_GENERIC_C5",
    "board_url": "https://micropython.org/download/ESP32_GENERIC_C5/",
    "latest_url": "https://micropython.org/resources/firmware/ESP32_GENERIC_C5-20260406-v1.28.0.bin",
    "file": "sessions/<session_id>/firmware/ESP32_GENERIC_C5-20260406-v1.28.0.bin",
    "file_type": "bin",
    "source": "micropython_latest",
    "flash_method": "esptool.py",
    "flash_result": {
      "tool": "esptool",
      "tool_version": "4.11.0",
      "port": "COM3",
      "write_offset": "0x2000",
      "erased_first": true,
      "log": "sessions/<session_id>/flash_esp32_log.json"
    }
  },
  "manifest_content": {
    "schema_version": "1.0",
    "phase": "upy-flash-mpy-firmware-plugin",
    "project_name": "esp32-c5-demo",
    "requirements": {
      "mcu_specified": "ESP32-C5",
      "network": "wifi"
    },
    "devices": [],
    "mcu": {
      "model": "ESP32-C5",
      "board_id": "esp32-c5-devkitc",
      "display_name": "ESP32-C5 DevKit",
      "firmware_url": "https://micropython.org/download/ESP32_GENERIC_C5/",
      "firmware_board_name": "ESP32_GENERIC_C5",
      "flash_tool": "esptool.py",
      "chip_family": "esp32c5"
    },
    "hardware_selection": {
      "selected_board": {
        "id": "esp32-c5-devkitc",
        "display_name": "ESP32-C5 DevKit",
        "chip_family": "esp32c5",
        "firmware": {
          "url": "https://micropython.org/download/ESP32_GENERIC_C5/",
          "board_name": "ESP32_GENERIC_C5",
          "port": "esp32"
        }
      }
    },
    "firmware_flash": {
      "status": "flashed",
      "action": "download_and_flash",
      "board_name": "ESP32_GENERIC_C5",
      "board_url": "https://micropython.org/download/ESP32_GENERIC_C5/",
      "latest_url": "https://micropython.org/resources/firmware/ESP32_GENERIC_C5-20260406-v1.28.0.bin",
      "file": "sessions/<session_id>/firmware/ESP32_GENERIC_C5-20260406-v1.28.0.bin",
      "file_type": "bin",
      "source": "micropython_latest",
      "flash_method": "esptool.py",
      "flash_result": {
        "tool": "esptool",
        "tool_version": "4.11.0",
        "port": "COM3",
        "write_offset": "0x2000",
        "erased_first": true,
        "log": "sessions/<session_id>/flash_esp32_log.json"
      }
    },
    "final_status": "firmware_ready",
    "updated_at": "<runtime-utc-now>"
  }
}
```

`firmware.status` 取值：

```text
downloaded
flashed
uf2_copied
manual_confirmed
skipped_user_confirmed
partial_download_only
failed
```

对于 `partial` 和 `failed`，`next_phase` 必须为 null。
