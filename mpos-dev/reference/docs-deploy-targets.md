# MicroPythonOS 部署目标参考

本文件基于 2026-07-14 重新读取的 `docs.micropythonos.com`、`https://install.micropythonos.com/`、`https://web.micropythonos.com/` 和 `/home/leeqingshui/MicroPythonOS/AGENTS.md` 生成。

## 什么时候读取

处理桌面仿真、浏览器/WebAssembly 预览、安装 App 到设备、固件烧录、目标选择时读取本文件。OS 构建内部细节读取 `docs-os-development.md`。

## 来源覆盖

- `getting-started/running/`
- `getting-started/supported-hardware/`
- `os-development/running-on-desktop/`
- `os-development/installing-on-esp32/`
- `os-development/linux/`
- `os-development/macos/`
- `os-development/windows/`
- `os-development/emulating-esp32-on-desktop/`
- `https://install.micropythonos.com/`
- `https://web.micropythonos.com/`
- 本地 `AGENTS.md`

## 目标类型

MicroPythonOS 可运行在：

- ESP32 和 ESP32-S3 设备。
- 通过 SDL 运行的 Linux/macOS 桌面端。
- Raspberry Pi 和 WSL2 类 Linux 环境。
- Browser/WebAssembly。
- 用于更深层 OS 开发和 CI 类测试的 QEMU ESP32 emulator。

## 本地桌面仿真

本地 AGENTS 规则优先：

```bash
make build-mpos-unix
timeout -s 9 30 ./scripts/run_desktop.sh
```

自动化调试使用 `scripts/mpos_controller.py`。`MPOSController()` 不会自动启动进程；需要调用 `mpos.start()`，并等待约 8 到 10 秒，再调用 `startapp()` 或 REPL 操作。

清理残留 simulator 进程时使用 `killall`，不要用 `pkill -f`：

```bash
killall lvgl_micropy_unix run_desktop.sh
```

controller/debug 脚本写到仓库 `tmp/` 下。

## Browser/WebAssembly 预览

`https://web.micropythonos.com/` 是浏览器 runtime，不是 installer，也不是 app 发布站点。

已观察到的页面行为：

- 加载 `micropython.js`。
- 使用 `["-X", "heapsize=16M", "-m", "main"]` 运行。
- 显示 `320x240` LVGL canvas。
- 提供 Log 和 Reset storage 控件。
- 模拟 NeoPixels、joystick、MENU、START、X/Y/A/B。
- 通过 IndexedDB/IDBFS 挂载 `/data` 和 `/apps`，让 preferences 和用户 App 在刷新后保留。

它适合快速用户预览和 Web port smoke check。硬件行为相关时，不要用它替代 Linux SDL 仿真或物理设备验证。

## 安装 App 到物理设备

安装 App 不是烧录固件。普通 Python App 迭代使用：

```bash
./scripts/install.sh com.micropythonos.appname
```

开始真机 App 安装前先确认设备已安装 MicroPythonOS、目标板型号和串口。如果设备未安装 OS 或状态不明，先使用 `https://install.micropythonos.com/` 安装/确认固件。

安装后：

```python
from mpos import AppManager
AppManager.refresh_apps()
```

必要时也可以 reboot/reset 设备。

部署单个文件：

```bash
python3 lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py cp local.py :/remote.py
```

如果 `mpos_controller.py` / AIOREPL 探针失败，但串口文件系统可访问，可以用直接 App 目录拷贝作为 `device-copy` 记录：

```bash
python3 lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py connect /dev/ttyACM0 fs mkdir :/apps
python3 lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py connect /dev/ttyACM0 fs cp -r internal_filesystem/apps/<fullname> :/apps/
python3 lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py connect /dev/ttyACM0 fs ls :/apps/<fullname>
```

这只能证明文件已复制到设备；发布验证仍应优先使用可调用 `AppManager.install_mpk()` 的 MPK install 路径。

然后使用 `machine.reset()` 并等待启动。

## 固件安装和烧录

只有在下面情况才使用固件烧录：

- 用户明确要求烧录固件。
- 固件缺失或版本不对。
- C module、LVGL binding、board support、filesystem image 或 OS 内部发生变化。

当前 web installer 事实：

- `install.micropythonos.com` 提供 WebSerial installer。
- 需要 USB 和支持 WebSerial 的浏览器，例如 Chrome 或 Edge。
- 页面使用 `esp-web-install-button`，提供 ESP32 与 ESP32-S3 目标。
- 当前列出 `0.10.x`、`0.11.x`、`0.12.x`、`0.13.x`、`0.14.x`、`0.15.x` 共 12 个 ESP32/ESP32-S3 manifest。
- 最新 `0.15.x` manifest 对应 `0.15.1`，固件路径分别是 `/firmware_images/esp32/MicroPythonOS_esp32_0.15.1.bin` 和 `/firmware_images/esp32s3/MicroPythonOS_esp32s3_0.15.1.bin`。
- 已读取的 installer manifest 中 `new_install_prompt_erase` 都为 true。

本地烧录路径：

```bash
./scripts/build_mpos.sh <target>
./scripts/flash_over_usb.sh
```

不要在没有用户明确确认的情况下执行 destructive erase/flash 动作。

### 本地 ESP32-S3 整包烧录失效模式

固件构建、烧录、启动和实机验证必须分开记录。`build_mpos.sh` 成功只说明镜像生成；`esptool` 写入成功只说明 flash 内容已校验；设备还必须退出 BOOT/下载模式并实际启动新固件。

检查 USB 状态时先看 `lsusb`：

- `303a:4001` 通常表示 Espressif Device 运行态 CDC 设备。
- `303a:1001` 通常表示 ESP32-S3 USB JTAG/serial 下载模式。

在 Linux/VMware 环境中，自动复位策略可能不稳定：

- `--before default_reset` 或 `--before usb_reset` 可能因底层串口 ioctl 报错。
- `--before no_reset_no_sync` 不是通用替代，可能无法完成 ROM 同步。
- 更稳的路径是手动让板子进入 BOOT/下载模式，确认 `lsusb` 显示 `303a:1001`，然后使用 `--before no_reset` 烧录。
- `mpremote bootloader` 不能当作唯一进入下载模式的方法；失败时要求手动 BOOT。

ESP32-S3 手动 BOOT 后的整包烧录示例：

```bash
LC_ALL=C.UTF-8 LANG=C.UTF-8 \
python -m esptool --chip esp32s3 -p /dev/ttyACM0 -b 460800 \
  --before no_reset --after hard_reset \
  write_flash --flash_mode dio --flash_size 16MB --flash_freq 80m \
  --erase-all 0x0 lvgl_micropython/build/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin
```

必须保留的证据：

- 构建日志中固件路径和 freezefs 刷新记录。
- 烧录日志中的 chip/flash 信息和 `Hash of data verified`。
- 烧录后 USB 枚举状态；如果仍是 `303a:1001`，提示松开 BOOT、按 RESET 或拔插 USB。
- 启动后的串口日志、实机截图或实际交互结果。模拟器截图不能替代真机证据。

## QEMU ESP32 仿真

docs 描述了 ESP32 QEMU 路径，用于更深层 OS 测试，可模拟 WiFi、storage、ULP/deepsleep、GPIO/touch button、ST7789V display。把它视为 OS-development 基础设施，不是默认 App 开发路径。

## 支持硬件说明

docs 列出多个 ESP32/ESP32-S3 设备以及 browser/desktop target。App 依赖 sensor、button、camera、display、LED 或 radio hardware 时，进入依赖准备阶段；目标设备未知时要询问用户。

## 来自 AGENTS 的安全规则

- 有等价入口时优先使用 `make build-mpos-unix`、`make syntax-tests`、`make unittest-tests`、`make tests`、`make lint`、`make lint-fix`。
- 每次代码修改后必须通过 `make lint`。
- 使用 `timeout -s 9 30 ./scripts/run_desktop.sh`。
- 使用 `killall`，不要用 `pkill -f`。
- 临时文件放项目 `tmp/`。
- 不要混淆 App 安装、MPK 安装和固件烧录。
