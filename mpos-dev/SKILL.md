---
name: mpos-dev
description: MicroPythonOS 基础开发知识库。提供代码架构、App/MPK 约束、LVGL 编程约定、MPY API reference、官方 docs 专题 reference、AGENTS 本地强约束。mpos-plan-app / mpos-analyze-app / mpos-prepare-deps / mpos-gen-app / mpos-debug-app / mpos-test-app / mpos-package-app / mpos-deploy-app / mpos-publish-app 均依赖此 skill。
---

# MicroPythonOS 基础开发知识库

## 角色定位

这是 mpos-* skill 家族的共享基础层。不要直接调用此 skill——请使用 `mpos-plan-app`（对话编排）、`mpos-analyze-app`（需求分析）、`mpos-prepare-deps`（依赖准备）、`mpos-gen-app`（生成 App）、`mpos-debug-app`（调试 App）、`mpos-test-app`（测试 App）、`mpos-package-app`（打包）、`mpos-deploy-app`（部署/仿真/安装/烧录）、`mpos-publish-app`（发布指导）。

## 用户语言连续性

所有 mpos-* skill 的用户可见输出应延续当前 workflow 的起始语言：如果用户先用中文描述需求，后续解释、计划、确认和总结继续用中文；如果用户先用英文描述需求，后续继续用英文。代码、命令、路径、API 名、JSON 字段名和 manifest 字段名保持英文。

## 统一项目日志

先确定当前 MicroPythonOS 仓库根目录 `<repo-root>`：

- 用户明确给出 repo 路径时，必须使用该路径。
- 否则，当前工作目录包含 `internal_filesystem/apps` 和 `scripts` 时，把当前工作目录作为 `<repo-root>`。
- 在隔离 clone/worktree/临时副本中测试时，绝不能把 artifact 写回 `/home/leeqingshui/MicroPythonOS` 主仓库。
- build、simulator、desktop-preview、web-preview 默认应在隔离 clone/worktree/临时副本中执行；除非用户明确允许，不要让这些流程修改主 MicroPythonOS checkout。

所有面向单个 App 的 mpos-* skill 都应维护同一个项目状态目录，便于中断恢复和 AI 调试：

```text
<repo-root>/tmp/mpos-plan-app/<fullname>/
  plan_state.json
  activity_log.jsonl
```

阶段 skill 完成后把产物登记给 `mpos-plan-app`，不要只把结果散落在各自 `tmp/mpos-*` 目录：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill <mpos-skill-name> \
  --phase <phase> \
  --result <result> \
  --artifact <artifact_key>=<path> \
  --next-skill <next-skill-or-null> \
  --event "<short summary>"
```

不要手写 `plan_state.json` 或 `activity_log.jsonl`；必须调用 `update_plan_state.py record/discover/invalidate`，保证 `plan_state.json` 使用 `mpos-plan-app-v1` schema，并在更新后用 `validate_plan_state.py` 校验。

标准 artifact key：`analysis_result`、`dependency_handoff`、`generation_result`、`app_test_result`、`package_result`、`deploy_result`、`publish_result`。

如果用户中断后说“继续/恢复/下一步”，先让 `mpos-plan-app` 读取或重建 `plan_state.json`，不要从头开始。

## 代码库架构

```
MicroPythonOS/
├── c_mpos/src/              ← native MicroPython 模块实现源码
│   ├── webcam.c             ← webcam.init(...) 返回 Webcam handle；模块函数操作该 handle
│   ├── pdm_mic.c            ← PDM_Mic(clk, data, rate, bufsize)/start/stop/readinto/deinit
│   ├── adc_mic.c            ← adc_mic.read(...) 函数
│   ├── quirc_decode.c       ← qrdecode.qrdecode(buffer,width,height) / qrdecode_rgb565(...)
│   └── rvswd_module.c       ← RVSWD(swdio, swclk) 调试/烧录接口
├── internal_filesystem/
│   ├── lib/mpos/            ← 核心框架（Python）
│   │   ├── app/             ← Activity/App/Service 基类
│   │   ├── content/         ← AppManager, Intent, streaming_unzip
│   │   ├── ui/              ← topmenu, keyboard, testing, appearance_manager, input_manager
│   │   ├── audio/           ← AudioManager, stream_wav, stream_rtttl, stream_record_*
│   │   ├── net/             ← wifi_service, download_manager, connectivity_manager
│   │   ├── config.py        ← SharedPreferences（持久化键值存储）
│   │   ├── camera_manager.py← CameraManager 单例
│   │   ├── battery_manager.py← BatteryManager
│   │   ├── gps_manager.py   ← GPSManager
│   │   ├── activity_navigator.py ← ActivityNavigator（路由）
│   │   └── ...
│   ├── apps/                ← 已安装的 App（每个一个目录）
│   └── main.py              ← 系统启动入口
├── lvgl_micropython/        ← LVGL + MicroPython 子模块
└── scripts/                 ← 构建/烧录/部署脚本
```

## 参考文件路由（按需查阅）

在编写任何 MicroPythonOS 代码前，**必须先查阅**以下 API 参考文件了解可用 API：

| 参考文件 | 内容 | 生成方式 |
|---------|------|---------|
| `reference/mpos-api-reference.md` | MicroPythonOS 用户可调用 API 的人读版：native MicroPython 模块、`mpos.__all__`、全源码 public API 索引 | `python3 scripts/extract_mpos_api.py` |
| `reference/mpos_api_summary.json` | MicroPythonOS 用户可调用 API 的机器可读版，含 `generated_at`、`counts`、`source_index`、`symbols[]` | `python3 scripts/extract_mpos_api.py` |
| `reference/lvgl-api-reference.md` | 从 `lvgl_micropython/lvgl.pyi` 解析的 LVGL MicroPython API 人读版 | `python3 scripts/extract_lvgl_api.py` |
| `reference/lvgl_api_summary.json` | 从 `lvgl_micropython/lvgl.pyi` 解析的 LVGL MicroPython API 机器可读版，含 `generated_at`、`counts`、`symbols[]` | `python3 scripts/extract_lvgl_api.py` |

如果参考文件不存在或过期，运行提取脚本：

```bash
python3 /home/leeqingshui/MicroPython_Skills/mpos-dev/scripts/extract_mpos_api.py
python3 /home/leeqingshui/MicroPython_Skills/mpos-dev/scripts/extract_lvgl_api.py --lvgl-micropython-dir /home/leeqingshui/lvgl_micropython
```

### API reference 使用规则

- MPOS API reference 只表示 MicroPython 用户可 import/call 的接口。native 模块只按 `adc_mic`、`pdm_mic`、`qrdecode`、`rvswd`、`webcam` 的 MPY 调用形态使用，不从 `c_mpos` 推断 C 函数。
- LVGL 代码生成以 `lvgl_api_summary.json` 的 `symbols[]` 为主，优先使用 `kind == "enum"`、`kind == "enum_member"`、`kind == "widget"`、`kind == "function"` 的符号。
- `type_aliases[]` 只解释签名类型。`runtime_api: false` 表示不能生成 `lv.<alias>`；有 `runtime_enum` 时生成对应 enum class member，例如 `event_code_t -> lv.EVENT.CLICKED`、`display_render_mode_t -> lv.DISPLAY_RENDER_MODE.PARTIAL`、`grad_dir_t -> lv.GRAD_DIR.VER`、`fs_whence_t -> lv.FS_SEEK.SET`。
- 方法签名里出现 `"display_render_mode_t"`、`"event_code_t"`、`"grad_dir_t"` 是类型注解，不是 runtime API。`lv.area_t()`、`lv.style_t()`、`lv.anim_t()` 这类 `*_t` data class/constructor 则是真实 MPY API，不能按后缀一刀切排除。
- `description` 为空时不要编造语义；需要解释时读取 docs reference、当前仓库代码或具体源码上下文。

按任务再读取这些 docs/reference 文件，避免把全部文档塞进上下文：

| 任务 | 读取 |
|------|------|
| 生成/修改 App、需求分析、Activity/Service/Intent | `reference/docs-app-model.md` |
| 使用系统 managers、持久化、下载、后台任务、通知、音频、传感器 | `reference/docs-frameworks.md` |
| 打包 `.mpk`、校验 manifest、生成 app_index、准备 upystore/BadgeHub | `reference/docs-packaging.md` |
| Linux 桌面仿真、安装 App 到设备、固件烧录、目标设备选择 | `reference/docs-deploy-targets.md` |
| 修改 OS 内核、构建系统、测试基础设施、板级移植、发布流程 | `reference/docs-os-development.md` |
| 浏览器/WebAssembly 运行、`web.micropythonos.com`、web target | `reference/docs-web-port.md` |
| 审计 docs 61 个页面是否已纳入 reference 路由 | `reference/docs-site-index.md` |

这些 reference 已结合 `<repo-root>/AGENTS.md` 的本地规则；当官方 docs 示例与本地仓库测试冲突时，优先遵守当前仓库和 AGENTS。

## App 与 MPK 基本契约

新建 App 时使用当前仓库的新扁平结构：

```text
internal_filesystem/apps/<fullname>/
  MANIFEST.JSON
  icon_64x64.png
  assets/<entrypoint>.py
```

- 旧 `META-INF/MANIFEST.JSON` 和 `res/mipmap-mdpi/icon_64x64.png` 仅作为兼容布局保留；新生成 App 不使用旧布局。
- App 目录名必须等于 manifest 的 `fullname`。
- `version` 必须是规范整数点号字符串，例如 `1.0.0`。
- activity/service 的 `entrypoint` 必须以 `.py` 结尾、文件必须存在，并且源码中必须包含对应 `classname`。
- 新生成的 activity/service metadata 使用完整对象：`classname`、`entrypoint`、`intent_filters`；不要使用 storefront seed 数据里的字符串型 `activities`。
- `.mpk` 是 ZIP，第一条 local header 必须是 `<fullname>/` 目录 entry，且所有文件都在该唯一顶层目录下。打包细节读取 `reference/docs-packaging.md`。

## LVGL 编程约定（必须逐条遵守）

以下规则来自 AGENTS.md，**写 LVGL UI 代码时必须逐条遵守**：

### 导入与全局
- `import lvgl as lv`，使用 `lv.` 访问所有 API
- `lv.screen_active()` 不是 `lv.scr_act()`
- 不要硬编码显示分辨率，使用 `lv.pct(100)` 做自适应
- `button` 不是 `btn`，`image` 不是 `img`
- `*_t = int` 是 `lvgl.pyi` 的类型别名，不是 runtime enum；写代码用 `lv.EVENT.CLICKED`、`lv.COLOR_FORMAT.RGB565`、`lv.DISPLAY_RENDER_MODE.PARTIAL`、`lv.GRAD_DIR.VER`

### 事件
- `lv.EVENT.VALUE_CHANGED` 不是 `lv.EVENT_VALUE_CHANGED`
- 事件处理器需要 3 个参数：`obj.add_event_cb(callback, lv.EVENT.CLICKED, None)`
- 方法作为事件回调必须接受 event 参数：`def callback(self, event)`
- 同时被直接调用和作为事件回调的方法需要默认值：`def method(self, event=None)`
- 使用 `event.get_target_obj()` 不是 `event.get_current_target()`

### Flag 与 State
- `lv.obj.FLAG.CLICKABLE` 不是 `lv.OBJ_FLAG.CLICKABLE`
- `.add_flag(lv.obj.FLAG.HIDDEN)` / `.remove_flag(lv.obj.FLAG.HIDDEN)` 不是 `.set_hidden()`
- `.remove_flag()` 不是 `.clear_flag()`
- `obj.remove_state(...)` 不是 `obj.clear_state(...)`
- `lv.obj.FLAG.FLOATING` — 从 flex layout 中移除 widget

### 样式
- `style_obj = lv.style_t()` 然后 `style_obj.init()` — **必须先 init 再 setter**，否则设备可能死机
- LVGL 9.x: style setter 只接受 value，selector 在 `add_style()` 中：`obj.add_style(style, lv.PART.ITEMS | lv.STATE.CHECKED)`
- 颜色：`lv.palette_main(lv.PALETTE.RED)` 或 `lv.color_hex(0xEC048C)`
- `lv.OPA` 枚举只有 10 步：`TRANSP(0)`, `_10`, `_20`, ..., `_100`, `COVER(255)`。不存在 `_5` 等值

### 控件特定
- label: 新创建的 label 默认显示 "Text"，必须 `label.set_text("")` 显式置空
- label: `label.set_long_mode(lv.label.LONG_MODE.WRAP)` 不是 `lv.label.LONG.WRAP`
- msgbox: `msgbox = lv.msgbox()` 然后 `msgbox.add_title("title")`
- buttonmatrix: `lv.buttonmatrix.CTRL.CHECKABLE` / `lv.buttonmatrix.CTRL.CHECKED`
- buttonmatrix: `set_map()` 会异步触发 `LV_EVENT_VALUE_CHANGED`，需用时间防抖 `time.ticks_diff(now, last_ts) < 50`
- buttonmatrix: 没有 `set_button_text()` / `set_button_ctrl()`，更新文本需重建 map
- dropdown: 使用 `lv.dropdown(lst, lv.DROPDOWN.DIR.BOTTOM)`（大写 DIR）
- anim: `lv.anim_t.path_ease_in_out` 不是 `lv.anim_path_ease_in_out`
- 无 `get_child_by_type()`，用全局变量保存子对象引用
- LVGL 对象不支持任意 Python 属性赋值（`btn.idx = 5` 报错），用闭包/lambda 或平行列表

### 键盘输入（SDL/桌面端）
- SDL 键盘驱动每个按键产生瞬时 press+release 对
- SDL_KEYUP 被完全忽略
- 检测按键释放：用超时机制，首次按下设长 deadline（~600ms），重复事件设短延期（~100ms）

### 图片与快照
- `lv.snapshot_take()` 在隐藏的 obj 上仍可能捕获非透明像素（主题样式泄漏）
- 缩放图片快照：将 image 放入 container，设置 container 大小，快照 container
- `lv.image_dsc_t()` 手动构造空图：
  ```python
  buf = bytearray(4)
  dsc = lv.image_dsc_t()
  dsc.data = buf
  dsc.header.w = 1
  dsc.header.h = target_height
  dsc.header.cf = lv.COLOR_FORMAT.ARGB8888
  ```

## Native MicroPython 模块速查

### webcam 模块
```python
import webcam

cam = webcam.init(width=320, height=240)          # 或 webcam.init("/dev/video1", width=640, height=480)
frame = webcam.capture_frame(cam, "grayscale")    # -> memoryview (1 byte/pixel)
frame = webcam.capture_frame(cam, "rgb565")       # -> memoryview (2 bytes/pixel)
webcam.reconfigure(cam, width=640, height=480)    # 运行时切换分辨率
webcam.free_buffer(cam)                           # 释放内部缓冲区
webcam.deinit(cam)                                # 关闭设备
```

### pdm_mic 模块
```python
from pdm_mic import PDM_Mic

mic = PDM_Mic(clk=42, data=41, rate=16000, bufsize=4096)
mic.start()
buf = bytearray(1024)
mic.readinto(buf)
mic.stop()
mic.deinit()
```

### adc_mic 模块
```python
from adc_mic import read
buf = read(chunk_samples=512, unit_id=1, adc_channel_list=[0,1],
           adc_channel_num=2, sample_rate_hz=16000, atten=3)
```

### qrdecode 模块
```python
from qrdecode import qrdecode, qrdecode_rgb565
result = qrdecode(grayscale_buffer, width, height)         # 灰度图解码
result = qrdecode_rgb565(rgb565_buffer, width, height)     # RGB565 图解码
# 返回 decoded payload bytes；未识别时会抛出异常
```

### rvswd 模块
```python
from rvswd import RVSWD

prog = RVSWD(39, 42)                          # RVSWD(swdio, swclk)
prog.reset()
prog.halt()
prog.resume()
vendor = prog.read_vendor_bytes()
prog.read_reg(reg) / prog.write_reg(reg, value)
prog.read_memory(addr) / prog.write_memory(addr, value)
# CH32X03x / CH32V20x 系列
prog.x03x_program(firmware, progress_callback)  # callback(msg, pct)
prog.v20x_program(firmware, progress_callback)
```

## 强约束

- **优先查阅 API 参考文件**：人读用 `reference/mpos-api-reference.md` / `reference/lvgl-api-reference.md`，机器检索用 `reference/mpos_api_summary.json` / `reference/lvgl_api_summary.json`；信息不足或过期时运行提取脚本
- **所有 LVGL 代码必须遵守上文 LVGL 编程约定**，逐条对照
- **Activity.__init__ 必须调用 super().__init__()**
- **新 label 必须显式 set_text("")**
- **style_t() 后必须先 init() 再 setter**
- **不硬编码屏幕分辨率**，使用 `lv.pct(100)`
- **不绕过框架 API**：持久化用 SharedPreferences，不要直接操作 json 文件
- **不修改 AGENTS.md 或 ruff.toml**
- **不污染主仓库**：除新增/修改目标 App 或用户明确允许外，不修改 `/home/leeqingshui/MicroPythonOS` 的 OS/build 源码；build、simulator、desktop-preview、web-preview、联调测试默认使用隔离 clone/worktree/临时副本
- **用户可见输出延续起始语言**：中文开始就继续中文，英文开始就继续英文；代码、命令、路径、API 名和 JSON 字段名保持英文
- **临时文件放 tmp/，不放 /tmp**
- **杀死进程用 killall，不用 pkill -f**
- **遵循 ruff.toml 的代码格式**（双引号）
