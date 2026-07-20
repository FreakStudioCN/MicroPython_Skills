# MicroPythonOS App 模型参考

本文件基于 2026-07-14 重新读取的 `docs.micropythonos.com` sitemap/search index 生成，并结合 `/home/leeqingshui/MicroPythonOS/AGENTS.md` 和当前本地仓库事实修正。

## 什么时候读取

生成、修改、审查或分析 MicroPythonOS App 时读取本文件。打包规则读取 `docs-packaging.md`。framework API 读取 `docs-frameworks.md`。

## 来源覆盖

- `apps/`
- `apps/creating-apps/`
- `apps/app-lifecycle/`
- `apps/appstore/`
- `apps/built-in-apps/`
- `apps/native-apps/`
- `architecture/intents/`

## 本地优先规则：App 目录结构

当前本地仓库和 `tests/test_apps_manifest.py` 以扁平结构为默认：

```text
internal_filesystem/apps/<fullname>/
  MANIFEST.JSON
  icon_64x64.png
  assets/<entrypoint>.py
```

旧嵌套结构仍可被当前 App loader 和安装测试兼容，但应视为 legacy，并在新生成 App 时避免使用：

```text
internal_filesystem/apps/<fullname>/
  META-INF/MANIFEST.JSON
  assets/<entrypoint>.py
  res/mipmap-mdpi/icon_64x64.png
```

`mpos-gen-app` 默认生成根目录 `MANIFEST.JSON` 和根目录 `icon_64x64.png`。entrypoint 默认放在 `assets/main.py`，便于 `mpos-prepare-deps` 放入 `assets/` 的 runtime 文件被直接 import。

## App 身份与 Manifest

每个 App 位于 `internal_filesystem/apps/<fullname>/`，并且 `<fullname>` 必须与 `MANIFEST.JSON` 中的 `fullname` 字段一致。兼容旧 App 时可读取 `META-INF/MANIFEST.JSON`，但新生成 App 不应使用旧路径。

本地测试要求的 manifest 字段：

- `fullname`：必须和目录名一致。
- `name`：显示名称。
- `publisher`：发布者/组织标识，必须是非空字符串；默认可从 `fullname` 前缀派生，例如 `com.example.app` -> `com.example`。
- `version`：规范的整数点号版本，例如 `1.0.0`，不要写成 `01.0` 或 `1.0-beta`。
- `activities`：可选列表，但每个条目都必须有存在的 `.py` entrypoint，并且源码中必须包含对应 classname。
- `services`：可选列表，entrypoint/classname 校验规则相同。

Activity/Service 元数据使用完整对象：

```json
{
  "classname": "ExampleActivity",
  "entrypoint": "assets/main.py",
  "intent_filters": [
    {"action": "main", "category": "launcher"}
  ]
}
```

不要使用某些 storefront seed 数据中出现的字符串型 `activities` 结构。

## Activity 模型

Activity 是由 activity stack 管理的单个 UI screen。生命周期方法：

- `onCreate()`：创建状态，构建或准备 UI。
- `onStart(screen)`：screen 即将可见。
- `onResume(screen)`：进入前台，可交互。
- `onPause(screen)`：另一个 activity 即将切到前台。
- `onStop(screen)`：不再可见。
- `onDestroy(screen)`：从 stack 移除前清理资源。

最小模式：

```python
import lvgl as lv
from mpos import Activity


class ExampleActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        label = lv.label(screen)
        label.set_text("Hello")
        label.center()
        self.setContentView(screen)
```

`self.appFullName` 由 `ActivityNavigator` 设置。用于 App 级偏好设置，例如 `SharedPreferences(self.appFullName)`。

## Service 模型

Service 是没有 UI 的后台组件。适合启动时任务和长期运行任务，例如 WiFi 自动连接、web server 启动、async REPL 任务、周期检查、通知等。

生命周期：

- `onCreate()`：初始化资源。
- `onStart(intent=None)`：执行或调度工作。
- `onDestroy()`：清理资源。

Service 可以在 manifest 中订阅 `boot_completed`：

```json
{
  "classname": "ExampleBootService",
  "entrypoint": "assets/service.py",
  "intent_filters": [{"action": "boot_completed"}]
}
```

## Intent 与导航

使用 `Intent` 做解耦的 Activity 通信。

- 显式 intent 指向已知 activity。
- 隐式 intent 指定 action/category，由系统解析处理者。
- 使用 intent 传递数据、接收结果，并让 App 处理文件/action 路由，避免直接依赖其他 App。

新代码优先从主 `mpos` 模块导入：

```python
from mpos import Activity, Intent
```

已有本地代码可能从子模块导入；不要为了统一导入而无意义改动无关文件。

## 内置 App 与 AppStore 上下文

内置 App 在设备上的 `/builtin/apps/` 下，包括 launcher、WiFi、AppStore、OSUpdate、Settings、File Manager。用户安装的 App 在 `/apps/` 下。

AppStore 会把 `.mpk` 包安装到 `/apps/`，并支持多个 backend。发布和 MPK 校验是独立环节，见 `docs-packaging.md`。

## Native 模块

大多数 App 应使用 MicroPython 编写。只有纯 MicroPython 不够时才使用 C/C++ native module，例如高频 game loop、信号处理、调用 C 库等。

Native module 会增加构建复杂度，并且和架构相关。如果功能需要 C module，应先进入依赖准备和部署/构建阶段，再承诺设备端支持。

## 来自 AGENTS 的本地 App 代码规则

- 有等价入口时优先使用根目录 `Makefile` target。
- 每次代码修改后必须通过 `make lint`。
- 不修改 `AGENTS.md` 或 `ruff.toml`。
- 按 `ruff.toml` 使用双引号。
- 临时 debug 文件放项目 `tmp/`，不要放 `/tmp`。
- 不硬编码屏幕分辨率；使用 `lv.pct(100)`、flex 或 align。
- 新 label 必须显式调用 `set_text("")` 或设置最终文本。
- `lv.style_t()` 后必须先 `init()` 再调用 setter。
- Activity 的 `__init__` 必须调用 `super().__init__()`。
- 设备 reset 使用 `machine.reset()`；当前 stack 的 soft reset 有问题。
