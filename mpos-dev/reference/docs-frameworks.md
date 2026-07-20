# MicroPythonOS Framework 参考

本文件基于 2026-07-14 重新读取的 `docs.micropythonos.com` sitemap/search index 生成，并结合 `/home/leeqingshui/MicroPythonOS/AGENTS.md` 修正。

## 什么时候读取

生成使用系统服务、持久化、网络、音频、传感器、相机、后台任务、App 启动/安装流程、UI/系统设置的代码前读取本文件。

## 来源覆盖

- `architecture/frameworks/`
- `frameworks/app-manager/`
- `frameworks/appearance-manager/`
- `frameworks/audiomanager/`
- `frameworks/battery-manager/`
- `frameworks/build-info/`
- `frameworks/connectivity-manager/`
- `frameworks/device-info/`
- `frameworks/display-metrics/`
- `frameworks/download-manager/`
- `frameworks/file-explorer-activity/`
- `frameworks/focus/`
- `frameworks/font-manager/`
- `frameworks/input-activity/`
- `frameworks/input-manager/`
- `frameworks/lights-manager/`
- `frameworks/notification-manager/`
- `frameworks/number-format/`
- `frameworks/preferences/`
- `frameworks/sensor-manager/`
- `frameworks/service/`
- `frameworks/setting-activity/`
- `frameworks/settings-activity/`
- `frameworks/task-manager/`
- `frameworks/time-zone/`
- `frameworks/webserver/`
- `frameworks/widget-animator/`
- `frameworks/wifi-service/`

## 导入策略

docs 推荐从根 `mpos` 模块导入 framework：

```python
from mpos import AppManager, DownloadManager, TaskManager
```

或者：

```python
import mpos
mpos.AppManager.get_app_list()
```

新代码避免新增子模块导入，除非当前正在编辑的文件已有这种局部惯例，或某个符号没有 re-export。

## 核心 Framework

### AppManager

用于 app discovery、app registry、`.mpk` 安装、卸载用户 App、启动 App、版本管理、intent resolution、重启 launcher、注册/启动 service。

常见用法：

- `AppManager.get_app_list()`
- `AppManager.get("<fullname>")`
- `AppManager.start_app("<fullname>")`
- `AppManager.install_mpk(temp_zip_path, dest_folder)`
- `AppManager.refresh_apps()`

使用本地脚本把 App 安装到物理设备后，先调用 `AppManager.refresh_apps()`，再期待 `start_app()` 能找到它。

### DownloadManager

用于 HTTP 下载。支持下载到 memory、file、stream callback；支持 retry、progress callback、range/resume、chunked download。

App/网络功能应优先使用它，不要手写临时 socket 下载逻辑。

### TaskManager

用于 App 中的 async/background work：

- `TaskManager.create_task(coro)`
- `TaskManager.sleep(seconds)`
- `TaskManager.sleep_ms(milliseconds)`
- `TaskManager.wait_for(coro, timeout=...)`
- event notification helpers

后台任务影响 widget 时，使用 Activity 提供的前台安全 UI 更新路径。

### SharedPreferences

用于 App 级持久化。Activity 中优先使用 `SharedPreferences(self.appFullName)`，不要硬编码 package name。

普通 App 偏好设置不要直接写自定义 JSON 配置文件，除非有明确理由。

### Service

Service 用于无 UI 的长期运行任务或启动时任务。Service 有 `onCreate`、`onStart`、`onDestroy`，可订阅 `boot_completed`。

## 硬件和系统 Manager

- `AudioManager`：播放和录音；协调音频优先级和硬件输出。
- `BatteryManager`：电池/电压状态。
- `CameraManager`：相机访问；相机功能要检查 C module 是否可用。
- `ConnectivityManager`：网络感知 App 行为和重连流程。
- `InputManager`、`InputActivity`、focus helpers：键盘、触摸、按钮和焦点导航。
- `LightsManager`：LED/NeoPixel 类设备灯光。
- `SensorManager`：传感器访问和读数。
- `NotificationManager`：通知和状态 UI。
- `AppearanceManager`、`DisplayMetrics`、`FontManager`、`WidgetAnimator`：UI 尺寸、主题、字体和动画。
- `WebServer`、`WifiService`：网络服务。
- `BuildInfo`、`DeviceInfo`、`TimeZone`、`NumberFormat`：系统元数据和工具。

## 来自 AGENTS 的 UI/LVGL 规则

- `import lvgl as lv`；通过 `lv.` 使用 API。
- 使用 `lv.screen_active()`，不要用 `lv.scr_act()`。
- 使用 `button`、`image`、`lv.EVENT.VALUE_CHANGED`、`lv.obj.FLAG.*`、`lv.buttonmatrix.CTRL.*` 这些名称。
- event callback 需要 event 参数，并用 `obj.add_event_cb(callback, lv.EVENT.CLICKED, None)` 注册。
- 使用 `event.get_target_obj()`，不要用 `event.get_current_target()`。
- 不硬编码屏幕分辨率。
- 新 label 不能保留默认 `"Text"`。
- setter 前必须先 `style = lv.style_t(); style.init()`。
- LVGL object wrapper 不接受任意 Python 属性；使用 closure 或并行状态结构。
- `lv.buttonmatrix.set_map()` 参数是 `list[str]`；行分隔使用单独的 `"\n"` 元素，末尾使用 `""` 终止符，例如 `["1", "2", "\n", "3", "4", ""]`。
- `lv.buttonmatrix.set_map()` 可能异步触发 value-changed；按时间 debounce。
- SDL keyboard 没有 key-up event；长按用 timeout 建模。

## 来自 AGENTS 的兼容性说明

- 当前 stack 的 soft reset 有问题；使用 `machine.reset()`。
- 部分 build 没有 `random.Random` 和 `random.shuffle`；需要时实现 Fisher-Yates 或小型本地 LCG。
- 避免在渲染路径中写 `except Exception: pass`；它会隐藏真实错误。

## 测试入口

UI 验证优先使用：

- `mpos.ui.testing.GraphicalTestCase`
- `KeyboardTestCase`
- `scripts/mpos_controller.py`
- widget tree 和 visible text extraction
- screenshots 加 pixel check 做视觉回归

已有 `internal_filesystem/lib/mpos/ui/testing.py` 能扩展时，不要在测试里写临时 helper。
