---
name: mpos-test-app
description: Test a specific MicroPythonOS App after mpos-gen-app using MicroPythonOS built-in desktop simulator/controller tools. Use when Codex needs to smoke-test or interactively exercise one generated MPOS app in the MPOS runtime with AppManager.start_app, visible text/widget-tree checks, screenshots, or scripted UI input. Does not own static gates such as make lint, flake8, pylint, manifest checks, syntax checks, packaging, deployment, device debugging, firmware rebuilds, or full OS regression testing.
---

# MicroPythonOS App 运行测试

## 角色

对 `mpos-gen-app` 已生成的目标 App 做 MPOS runtime 级冒烟测试和轻量交互测试。默认只测目标 App，不跑全量 OS tests。

静态门禁属于 `mpos-gen-app`：`make lint`、manifest、CPython/mpy syntax、MicroPython import、API 交叉校验、flake8、pylint、App-only 变更检查必须在生成/修复后立即执行。本 skill 只复核 `generation_result.json` 中这些门禁已记录通过；不要重复定义或替代它们。

## 用户可见语言

遵守 `mpos-dev` 的语言连续性规则：当前 workflow 从中文开始，测试摘要、失败归因和下一步建议继续用中文；从英文开始则继续用英文。代码、命令、路径、API 名和 JSON 字段名保持英文。

## 统一项目日志

完成 runtime smoke 或可选 Web Port 验证并产出 `app_test_result.json` 后，必须登记到项目状态目录：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill mpos-test-app \
  --phase test-app \
  --result <success|partial|failed|blocked> \
  --artifact app_test_result=<app_test_result.json> \
  --next-skill <handoff.next_skill-or-null> \
  --event "Ran MPOS runtime smoke test"
```

如果失败属于 App 自身，`handoff.next_skill` 指向 `mpos-gen-app` repair；如果是 OS/tooling 外部阻塞，只记录 blocked/warning，不让 `mpos-gen-app` 修无关 OS 文件。

必须使用 MicroPythonOS 仓库内置工具：

- `mpos-dev/reference/mpos_api_summary.json`
- `mpos-dev/reference/lvgl_api_summary.json`
- `<repo-root>/scripts/mpos_controller.py`
- `<repo-root>/scripts/run_desktop.sh`
- `<repo-root>/tests/unittest.sh`
- `<repo-root>/internal_filesystem/lib/mpos/ui/testing.py`
- `<repo-root>/internal_filesystem/lib/mpos/testing/`

先完整读取两个 API summary JSON，再读取测试工具源码。测试阶段即使不改 App，也要用它们判断 traceback 是否来自不存在/变更的 MPOS 或 LVGL API。

设备调试、串口日志和硬件排障不属于本 skill 默认范围。

不要直接修改 MicroPythonOS OS/build 源码来修测试环境。遇到缺 `_webrepl`、缺 desktop binary、缺 `libffi-dev`、缺 `libv4l-dev` 等本机 simulator/tooling 问题时，默认只标记 external/tooling blocking。只有用户明确要求修本机 simulator 时，才运行本 skill 的 helper：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-test-app/scripts/prepare_desktop_tooling.py \
  --repo <repo-root> \
  --build
```

`prepare_desktop_tooling.py` 不编辑 OS 源码；它只创建临时 build shim：用 fake `pkg-config` 指向用户态静态 `libffi.a`，并在缺 `libv4l2.a` 时提供仅供 desktop link 的空静态库，然后调用现有 `<repo-root>/scripts/build_mpos.sh unix`。运行结束后临时 shim 会随临时目录删除；构建产物仍由原 build 脚本生成。

如果用户要打开完整桌面模拟器，优先在隔离 clone/worktree 中使用 release ELF 快速路径：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-test-app/scripts/prepare_desktop_binary.py \
  --repo <repo-root> \
  --run-app <fullname>
```

`prepare_desktop_binary.py` 从 `https://api.github.com/repos/MicroPythonOS/MicroPythonOS/releases/latest` 选择最新 Linux amd64 `.elf`，写入 `<repo-root>/lvgl_micropython/build/lvgl_micropy_unix` 并加执行位，然后可选调用 `scripts/run_desktop.sh <fullname>`。如果必须严格匹配本地源码，保留本地 build 路径：

```bash
cd <repo-root>
scripts/build_mpos.sh unix
scripts/run_desktop.sh <fullname>
```

每次用户可见测试总结都必须给出人工复现命令，至少包括：

```bash
cd <repo-root>
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-test-app/scripts/run_app_smoke.py \
  --repo <repo-root> \
  --app-fullname <fullname> \
  --generation-result <generation_result.json> \
  --screenshot

scripts/run_desktop.sh <fullname>
```

如果用户通过 Claude Code 测试，应提示使用 slash command 形态，例如：

```text
/mpos-test-app 在 /home/leeqingshui/tmp/mpos-skill-cc-test-20260717 中测试 com.example.cc_skill_smoke，读取 generation_result.json，运行桌面 smoke，并给出 PNG 截图和完整模拟器打开命令
```

## 默认测试

硬件相关测试先读 `mpos-dev/reference/docs-hardware-capabilities.md`。对每个 `required_capabilities[]` 记录 probe、`available|unavailable|emulated|unsupported_in_preview|not_tested`、fallback 结果和证据。`portable_api=false` 不能用桌面 mock 冒充支持。

静态测试必须拒绝普通 App 中的 `mpos.board.*` 和直接 GPIO/I2C/SPI/UART/I2S/ADC/NeoPixel 构造。交互 App 至少验证 pointer 路径和 focus/keypad 路径；硬件 Activity 退出后验证 Launcher 输入和另一 App 仍可使用。

默认运行目标 App 桌面模拟器冒烟测试，分两层：

1. 必须先尝试内置 desktop runner：

```bash
<repo-root>/scripts/run_desktop.sh <fullname>
```

`run_desktop.sh` 是人工/真实桌面启动路径，会设置 `auto_start_app_early` 并启动 desktop MPOS。自动化脚本必须用有界超时执行它：如果超时前没有 OS/tooling boot marker，并且输出包含 `run_desktop.sh: running app <fullname>`，则把长驻运行视为启动成功。`Error importing mpos.main`、缺 `_webrepl`、脚本/二进制缺失等属于 OS/tooling 外部阻塞；boot 后的普通 traceback/import error 只说明 desktop runner 看到运行期错误，必须继续用 `mpos_controller.py` 定位是否属于目标 App。探测前后必须恢复 `prefs/com.micropythonos.settings/config.json`，避免自启动配置污染后续测试。

2. 再运行结构化 controller smoke：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-test-app/scripts/run_app_smoke.py \
  --repo <repo-root> \
  --app-fullname <fullname> \
  --generation-result <generation_result.json> \
  --screenshot
```

`run_app_smoke.py` 默认包含以上 `run_desktop.sh` 启动探测，然后通过 `scripts/mpos_controller.py` 启动 `lvgl_micropy_unix`，先确认 `mpos.main` 已成功 boot，再在 MPOS runtime 中执行：

```python
from mpos.content.app_manager import AppManager
from mpos.ui.testing import wait_for_render
AppManager.start_app("<fullname>")
wait_for_render()
```

然后采集：

- `run_desktop.sh <fullname>` 的启动输出、returncode、超时状态和错误摘要。
- `AppManager.start_app()` 结果和 traceback。
- 可见文本 `get_visible_text()`。
- widget tree 摘要 `get_widget_tree()`。
- 可选 screenshot：保留 BMP raw artifact，并默认转换出 PNG publish-ready artifact。

如果用户给出期望文本，用 `--expected-text "<text>"` 增加强断言。没有期望文本时，只要 App 能启动且 runtime 没抛异常即可通过；空文本不能自动判失败，因为游戏、Canvas、图像类 App 可能没有 label 文本。

## 可选测试

### 目标测试文件

只有用户要求写/运行测试文件，或生成 App 明确包含测试需求时，才创建目标 App 专用测试文件。不要跑全量 `./tests/unittest.sh`。

可用模式：

```bash
cd <repo-root>
./tests/unittest.sh tests/test_graphical_<app>.py
```

图形测试使用 `mpos.ui.testing.GraphicalTestCase`、`KeyboardTestCase`、`simulate_click`、`wait_for_render`、`capture_screenshot`。硬件相关逻辑使用 `mpos.testing` mocks。测试文件必须只覆盖目标 App 行为，避免改 OS/framework 回归测试。

### Web Port

`https://web.micropythonos.com/` 是 MicroPythonOS WebAssembly Web Port 的在线运行入口。官方文档说明 Web Port 可在浏览器中运行 OS，`/data` 和 `/apps` 存在浏览器 IndexedDB，HTTP 走浏览器 `fetch()`，并受 CORS、无 Bluetooth/ADC/IMU/camera 等浏览器限制影响。

Web Port 只作为可选浏览器验证，不是默认 gate：

- 仅当用户明确要求 Web Port 验证时运行；给 `run_app_smoke.py` 加 `--web-port-check`。
- 当前最新本地代码已包含 `scripts/run_web.sh` 和 `scripts/web_port/`；如果缺失，记录为 `skipped_missing_local_web_tooling`。
- `run_app_smoke.py --web-port-check` 只调用 `scripts/run_web.sh --no-build` serve 已存在的 `web/` 产物，并用 HTTP GET 检查 `http://127.0.0.1:<port>/`。
- 如果 `web/index.html`、`web/micropython.js`、`web/micropython.wasm` 或 `web/micropython.data` 不存在，记录为 `skipped_missing_web_artifacts`；不要自动 rebuild，除非用户另行要求。
- `scripts/run_web.sh` 默认会先执行 `scripts/build_mpos.sh web`，需要 Emscripten `emcc` 或可自动 source 的 `../emsdk`/`../../emsdk`。
- 如果 `emcc` 不可用，记录为 `skipped_missing_emscripten`，不要把它当 App 失败。
- 如果 Web build/link 报 `machine_timer_type` 等符号或工具链错误，归类为 OS/Web port tooling 问题；先提示安装或修复 Web build 依赖/工具链，不要让 `mpos-gen-app` 修改目标 App，也不要把它误判为普通 Python 依赖缺失。
- 只有用户明确要求浏览器自动化时加 `--web-port-browser-check`；Chrome/Chromium 缺失、headless 启动失败或超时只记录 skipped/warning，不让目标 App 失败。
- 不用 Web Port 代替 `scripts/mpos_controller.py` desktop smoke。

当前最新代码和官方 Web Port 文档一致，本地命令是：

```bash
scripts/build_mpos.sh web
scripts/run_web.sh
```

可选 smoke 命令：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-test-app/scripts/run_app_smoke.py \
  --repo <repo-root> \
  --app-fullname <fullname> \
  --web-port-check
```

每次用户可见测试总结都必须把 Web Port 明确标为“可选”，并给出本地命令：

```bash
cd <repo-root>
scripts/build_mpos.sh web
scripts/run_web.sh
```

`scripts/build_mpos.sh web` 会把 `internal_filesystem` staging 到 `web/.preload_internal_filesystem`，注入 web-only `_thread`、`socket`、`aiorepl`、`_webrepl`、`websocket`、`aiohttp`、`machine.Timer` 等 shim，并输出 `web/micropython.{html,js,wasm,data}` 与 `web/index.html`。这验证的是浏览器/WASM 端兼容性；默认 App smoke 仍优先用本地 desktop simulator。

## 批量截图 / 最终证据模式

批量生成、演示 App 库、或用户明确说“中间文件不需要”时，`app_test_result.json` 可以不作为最终交付文件展示，但截图不能省略。必须为每个 App 生成 PNG/JPEG/WebP 这种 upystore 可接受的截图，并写出截图清单：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-test-app/scripts/capture_batch_screenshots.py \
  --repo <repo-root> \
  --app-prefix <fullname-prefix> \
  --output-dir <repo-root>/tmp/<batch-name>/screenshots
```

该脚本只输出 PNG 截图和 `screenshot_manifest.json`，不要求补齐每个 App 的 `app_test_result.json`。如果用户需要可恢复的单 App 测试链路，继续使用 `run_app_smoke.py --screenshot --output <repo-root>/tmp/mpos-test-app/<fullname>/app_test_result.json`。

不要在缺少截图时把批量 App 报告为 demo-ready、publish-ready 或 `100/100 OK`；必须列出缺失截图的 App。

## 失败处理

失败时输出结构化结果并交回 `mpos-gen-app repair`，包含：

- 失败阶段：`generation_result_static_gates`、`desktop_runner_launch`、`desktop_boot`、`app_start`、`expected_text`、`screenshot`。
- command、cwd、returncode 或异常类型。
- stdout/stderr/traceback 关键片段。
- 可见文本和 widget tree 摘要。
- screenshot 路径（如果生成成功）。
- `manual_preview_commands`：release ELF 快速桌面命令、本地 build 桌面命令、可选 Web Port 命令。
- 涉及的 App 文件和是否允许修复。

只把 App 自身启动/渲染/交互失败交给 `mpos-gen-app repair`。如果失败原因是缺少 `lvgl_micropy_unix`、`mpos.main` boot 失败、缺少 `_webrepl`、缺少本地 web tooling、缺少 Emscripten、缺少 web build 产物、全量 OS tests 失败、硬件不可用或外部服务不可达，标记为外部阻塞或 warning，不让 `mpos-gen-app` 修改无关 OS 文件，也不要直接改 OS 源码。

## 输出 JSON

使用 `templates/app_test_result.json` 作为字段模板，并用脚本校验：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-test-app/scripts/validate_app_test_result.py \
  /path/to/app_test_result.json
```

成功时：

- `schema_version` 为 `mpos-test-app-v1`。
- `phase` 为 `test-app`。
- `app.fullname` 指向目标 App。
- `checks[]` 至少包含 `generation_result_static_gates`、`desktop_runner_launch` 和 `desktop_smoke`。
- 如果运行 `--web-port-check`，`checks[]` 追加 `web_port`，且 `required` 必须为 `false`。
- `handoff.next_skill` 为 `null`，或用户要继续修复时为 `"mpos-gen-app"`。
- `artifacts[]` 中发布截图优先使用 PNG；BMP 只能作为 `screenshot_raw`。
