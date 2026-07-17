# MicroPythonOS Web Port 参考

本文件基于 2026-07-14 重新读取的 `docs.micropythonos.com/web-port/*`、`https://web.micropythonos.com/` 和 `/home/leeqingshui/MicroPythonOS/AGENTS.md` 生成。

## 什么时候读取

处理 browser/WebAssembly 预览、web-port smoke test、解释浏览器限制、或修改 `web` build target 时读取本文件。普通桌面仿真读取 `docs-deploy-targets.md`。

## 来源覆盖

- `web-port/using/`
- `web-port/developer/`
- `https://web.micropythonos.com/`
- 本地 `AGENTS.md`

## Web Port 是什么

Web port 通过 WebAssembly 在现代浏览器中完整运行 MicroPythonOS。它适合不烧录硬件就快速试用 OS，也适合做快速视觉 smoke check。

它不是：

- Firmware installer。
- App store 发布入口。
- 调试本地源码变化时 Linux SDL 仿真的替代品。
- 涉及硬件行为时物理设备验证的替代品。

## 线上页面事实

`https://web.micropythonos.com/` 在 2026-07-14 返回 `200`。

页面行为：

- Title：`MicroPythonOS Web`。
- 加载 `micropython.js`。
- 使用 `320x240` LVGL canvas。
- 通过 `["-X", "heapsize=16M", "-m", "main"]` 启动 MicroPythonOS。
- 提供可切换的 Log panel。
- 提供 Reset storage。
- 模拟 NeoPixels、joystick、MENU、START、X/Y/A/B。
- 使用 `Module.__webio` 模拟 badge peripherals。
- 使用 IndexedDB/IDBFS 挂载 `/data` 和 `/apps`。
- 首次运行时把 bundled apps seed 到 `/apps`。

## 持久化

浏览器把可写的 `/data` 和 `/apps` 存到 IndexedDB。这意味着 preferences 和已安装 App 会在页面刷新后保留。

强制清空状态：

- 页面有 Reset storage 按钮时直接使用。
- 或在浏览器开发者工具中清理 site data/IndexedDB。

重置后，bundled demo apps 会在首次运行时重新 seed。

## 开发者构建流程

docs 描述的流程：

```bash
scripts/build_mpos.sh web
scripts/run_web.sh
scripts/run_web.sh --no-build
PORT=9000 scripts/run_web.sh
```

产物位于 `web/`，包括 `micropython.html`、`micropython.js`、`micropython.wasm`、`micropython.data` 以及复制的 web entry 文件。

构建需要 Emscripten SDK。如果环境按 docs 配置，build 可以自动激活附近的 `emsdk` checkout。

## 集成说明

Web port 自包含在主 MicroPythonOS 仓库中。web target 需要的 submodule 修改存放在 `scripts/web_port/`，构建时自动应用。除非任务明确要求修改这些项目，否则不要在嵌套的 `lvgl_micropython`、`micropython` 或 `lvgl` 中留下持久改动。

## 测试建议

Web port 检查适合：

- 快速用户预览。
- 浏览器特有 input/storage 回归。
- 确认 WebAssembly boot 和 bundled app seeding。
- 检查 `/data` 和 `/apps` 持久化行为。

本地自动化 App 调试仍应使用 Linux SDL 桌面仿真和 `mpos_controller.py`。硬件特有行为使用物理设备验证。

## 来自 AGENTS 的本地规则

- 桌面工作优先使用 `make build-mpos-unix`；只有目标是 browser/WebAssembly 时才使用 web build。
- 临时脚本和 debug artifact 放 repository `tmp/`。
- 每次代码修改后必须通过 `make lint`。
- 不修改 `AGENTS.md` 或 `ruff.toml`。
- 清理本地桌面进程时使用 `killall`，不要用 `pkill -f`。
