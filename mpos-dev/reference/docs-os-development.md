# MicroPythonOS OS 开发参考

本文件基于 2026-07-14 重新读取的 `docs.micropythonos.com` 和 `/home/leeqingshui/MicroPythonOS/AGENTS.md` 生成。

## 什么时候读取

修改 MicroPythonOS 内部、C module、构建脚本、board support、测试基础设施、release 流程、文件格式支持、低层 LVGL/MicroPython 集成时读取本文件。普通 App 生成应使用 `docs-app-model.md` 和 `docs-frameworks.md`。

## 来源覆盖

- `os-development/`
- `os-development/compiling/`
- `os-development/automated-testing/`
- `os-development/porting-guide/`
- `os-development/linux/`
- `os-development/macos/`
- `os-development/windows/`
- `other/merge-checklist/`
- `other/release-checklist/`
- `other/supported-file-formats/`
- 本地 `AGENTS.md`

## 仓库结构

主代码位于 `internal_filesystem/`，对应目标设备上的 filesystem 布局。OS 构建基于 `lvgl_micropython`，其中包含 LVGL、MicroPython、平台 port 和 display/input driver。MicroPython C binding 位于 `c_mpos/`。

## 构建入口

有等价入口时优先使用根目录 `Makefile`：

```bash
make build-mpos-unix
make syntax-tests
make unittest-tests
make tests
make lint
make lint-fix
```

低层构建脚本：

```bash
./scripts/build_mpos.sh <target>
```

docs 提到的 target 包括 `esp32`、`esp32s3`、`unix`、`macOS`、`web`。本地 AGENTS 还提到 `esp32-small`、`unphone`、`lilygo_t4` 等附加 target。

重要本地注意事项：`build_mpos.sh` 会在 patch 构建输入时修改 tracked files。除非明确 revert，否则这些改动会保留。

## Builtin / Freezefs 构建验证铁律

修改 `internal_filesystem/builtin/`、OS framework、board support、filesystem image、C/native module、LVGL binding 或构建脚本后，不能用工作区 `.py` 源码直接判断设备运行结果。MicroPythonOS 的 builtin 内容会在构建时先复制到临时目录，再由 `mpy-cross` 编译成 `.mpy`，随后生成 `freezefs_mount_builtin.py` 并打进固件镜像；设备运行的是固件里的 frozen/freezefs 产物。

必须按完整链路验证：

1. 清理旧产物：检查并删除相关 `__pycache__`、旧 `.mpy`、以及 ESP32 frozen build 目录，避免旧编译产物污染判断。
2. 重新构建：运行 `./scripts/build_mpos.sh esp32s3` 或对应 target。
3. 在构建日志中确认出现 `Refreshing freezefs`，并看到 builtin `.py` 被 `mpy-cross` 以正确 `-march` 编译。
4. 确认生成新的固件镜像，例如 `lvgl_micropython/build/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin`。
5. 按部署文档整包烧录固件；只烧 `internal_filesystem.bin` 或只复制 App 目录不能证明 builtin/freezefs 变更生效。
6. 启动新固件后再做实机交互、串口日志或截图验证。

常见误判：

- 源码已经修改，但设备仍运行旧 `.mpy` / 旧 freezefs。
- build 成功，但没有烧录到设备。
- 烧录成功，但设备仍停在 BOOT/下载模式，没有运行新固件。
- 模拟器现象被误当成真机证据；硬件行为必须用物理设备验证。

## 测试

本地 AGENTS 规则：

- Syntax test 通过 `./tests/syntax.sh` 运行。
- Unit test 通过 `./tests/unittest.sh [test_file] [--ondevice]` 运行。
- `make tests` 运行 syntax 和 unit test。
- `mpy-cross` 位于 `./lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross`。
- 文件名包含 `graphical` 的测试会被识别为 graphical test。
- 非 graphical test 不注入 LVGL boot/main。
- on-device test 不要手动重复运行 boot/main；runner 会处理。
- 添加新测试前先读 `tests/README.md`。

图形/UI 修改：

- 使用 `mpos.ui.testing.GraphicalTestCase`。
- 扩展本地 test helper，不要写临时 ad hoc helper。
- 使用 widget tree、visible text、screenshot 和 pixel check 验证。

## 移植

设备特定 Python 代码应位于 `internal_filesystem/lib/mpos/board/<boardname>.py`。

移植流程：

1. 为设备构建或配置 `lvgl_micropython`。
2. 确认 MicroPython REPL 可以启动。
3. 添加或调整 board-specific MicroPythonOS 代码。
4. 验证 display、input、storage、reset、WiFi 和可用 manager。
5. 添加测试或手动验证记录。

不要在未检查本地文件的情况下，把官方 LVGL binding 的假设套用到本仓库的 `lvgl_micropython` fork。

## Release 和 Merge 检查

merge 或 release 前检查：

- `CHANGELOG.md` 是否需要更新？
- 被修改的 App 是否需要在 `MANIFEST.JSON` 中 bump version？
- docs 是否需要更新？
- 新 board 是否需要更新 `MAINTAINERS.md`？
- 是否为行为变化添加或扩展测试？
- 功能改动是否和批量格式化/generated diff 分开？

Release 流程包括更新 OS version、changelog JSON、GitHub builds、OTA artifacts、installer firmware files 和 metadata。

## 支持的文件格式

docs 列出：

- 图片：BMP、PNG、baseline JPEG、部分 RAW 命名模式。
- 不支持 progressive JPEG。
- 音频：PCM WAV 和 IMA ADPCM WAV。

生成 App 时优先使用这些格式，除非明确要求新增 decoder。

## 来自 AGENTS 的开发规则

- 每次代码修改后必须通过 `make lint`。
- 不修改 `AGENTS.md` 或 `ruff.toml`。
- 临时文件放项目 `tmp/`。
- 使用 `killall`，不要用 `pkill -f`。
- 使用 hard reset（`machine.reset()`），不要用 soft reset。
- 桌面运行命令必须用 `timeout -s 9 30` 包装 `./scripts/run_desktop.sh`。
- 按 ruff config 使用双引号。
- 避免静默 `except Exception: pass`，尤其在渲染路径中。

## 什么时候从 App 工作升级到 OS 工作

除非任务需要下面内容，否则停留在 App 级 skill：

- C module 或 native module。
- LVGL binding 修改。
- 新 board/display/touch support。
- Firmware image 修改。
- Filesystem image 修改。
- WebAssembly runtime 修改。
- AppStore backend 实现修改。

否则，普通 App 生成、MPK 打包、桌面仿真、设备 App 安装就足够。
