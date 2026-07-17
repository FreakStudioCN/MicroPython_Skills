# MicroPythonOS 对话式 Skill 拆分分析

日期：2026-07-14

本文只做分析和设计建议，不创建或改写 skill。依据包括本地
`/home/leeqingshui/MicroPythonOS`、`/home/leeqingshui/MicroPython_Skills`、
`/home/leeqingshui/lvgl_micropython` 的当前内容，以及 2026-07-14 对
`https://upystore.io/`、`https://install.micropythonos.com/`、
`https://docs.micropythonos.com/`、`https://web.micropythonos.com/`
的正文、公开 API、安装 manifest 和 docs `search_index.json` 的读取。

## 结论

MicroPythonOS 的对话式开发不适合做成一个超大的 skill。正确形态应是：

1. 一个用户入口编排 skill，负责对话、阶段切换、状态交接。
2. 多个阶段性专用 skill，分别做需求分析、驱动/依赖准备、API 资料刷新、App 生成、测试仿真、MPK 打包、设备安装/烧录、发布指导。
3. 一个共享基础 skill/reference 层，沉淀 MicroPythonOS、LVGL、MPK、mpremote、仿真器等项目事实。
4. 把高确定性、易出错、重复执行的动作做成脚本，例如 API 提取、manifest 校验、单 app MPK 打包、MPK 结构验证、设备端安装检查。

建议的拆分是 8 个用户可感知 skill + 1 个共享基础 skill：

| 建议 skill | 类型 | 主要职责 | 现状 |
|---|---|---|---|
| `mpos-dev` | 共享基础 | MicroPythonOS/LVGL/API 约束、API 提取脚本入口 | 已有，reference 路由、LVGL 独立仓库路径、API MD/JSON 双格式已补齐 |
| `mpos-plan-app` | 用户入口/编排 | 对话式需求澄清、阶段状态、调用下游 skill | 建议新增 |
| `mpos-analyze-app` | 阶段 skill | 需求分析、App 类型、功能边界、manifest 初稿、硬件/网络/存储风险 | 建议新增 |
| `mpos-prepare-deps` | 阶段 skill | 驱动/依赖下载、资料检索、缺失驱动处理、资源准备 | 建议新增 |
| `mpos-gen-app` | 阶段 skill | 生成或修改 MPOS App 代码、manifest、资源 | 已有，但需要补强 |
| `mpos-test-app` | 阶段 skill | 语法、单元、图形化测试、截图/控制器验证 | 已有，可保留扩展 |
| `mpos-package-app` | 阶段 skill | 单 App MPK 打包、app_index 片段、MPK 格式校验 | 建议新增 |
| `mpos-deploy-app` | 阶段 skill | Linux 端仿真、安装 App 到设备、必要时烧录固件 | 建议新增，部分能力在 `mpos-debug-app`/mpremote skills |
| `mpos-publish-app` | 阶段 skill | 发布前检查、upystore 上传指导、上传后验证建议 | 建议新增，上传本身给链接 |

本轮重新读取本地仓库、四个 API reference、`upystore.io`、`install.micropythonos.com` 和 docs 全站后，这个拆分不需要改变；需要补强的是下游 skill 对 API reference 的使用规则，尤其是 LVGL 的 `type_aliases[]` 只能解释签名、不能当 runtime API 生成代码。

这套拆分比直接复用旧 `upy-*` 流水线更合适。`upy-*` 主要面向“自然语言生成普通 MicroPython 硬件项目”，MicroPythonOS 的核心对象是 App、Activity、MANIFEST、MPK、AppStore、桌面仿真和系统镜像，生命周期和交付物不同。

## 已查看到的关键事实

### 本地 MicroPythonOS 事实

- `MicroPythonOS/AGENTS.md` 说明项目是带 AppStore、OTA、内置 App 的 MicroPythonOS，主代码在 `internal_filesystem/`，构建基于 `lvgl_micropython/`，native MicroPython 模块实现源码在 `c_mpos/`。
- 推荐命令入口包括 `make build-mpos-unix`、`make syntax-tests`、`make unittest-tests`、`make tests`、`make lint`、`make lint-fix`。
- 桌面仿真入口是 `scripts/run_desktop.sh`，AGENTS 要求调试运行时使用 `timeout -s 9 30 ./scripts/run_desktop.sh`。
- 固件构建入口是 `scripts/build_mpos.sh <target>`，支持 `unix`、`macOS`、`esp32`、`esp32-small`、`esp32s3`、`unphone`、`lilygo_t4` 等目标。
- 设备安装 App 的入口是 `scripts/install.sh com.micropythonos.<appname>`，底层使用 `lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py`。
- 固件 USB 烧录入口是 `scripts/flash_over_usb.sh`，默认写入 `lvgl_micropython/build/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin`。
- App 打包入口是 `scripts/bundle_apps.sh`，会从 `internal_filesystem/apps` 生成 `../apps/app_index.json`、MPK 和图标 URL。
- App 目录实际形态通常是：

```text
internal_filesystem/apps/com.example.app/
  META-INF/MANIFEST.JSON
  assets/main.py
  res/mipmap-mdpi/icon_64x64.png
```

现有 `com.micropythonos.helloworld/META-INF/MANIFEST.JSON` 的 `entrypoint` 是 `assets/hello.py`，这比现有 `mpos-gen-app` 中“Activity 文件在 app 根目录”的示意更贴近仓库事实。
- 在线 docs 的 `Creating Apps` 页面当前示例是扁平结构 `MANIFEST.JSON`、`icon_64x64.png`、`hello.py`；但本地仓库 `internal_filesystem/apps/*` 和 `tests/test_apps_manifest.py` 当前强制 `META-INF/MANIFEST.JSON`，入口文件也普遍在 `assets/*.py`。因此 skill 生成时必须以当前仓库测试和现有 app 为准，同时在 `mpos-dev` reference 中记录“docs 示例与仓库现状不一致”。

### App 与 MPK 约束

- `tests/test_apps_manifest.py` 会校验：
  - App 目录名必须等于 `MANIFEST.JSON` 里的 `fullname`。
  - `name`、`version` 必填。
  - `version` 必须是规范整数点号形式，例如 `0.1.6`。
  - 每个 activity/service 的 `entrypoint` 必须以 `.py` 结尾且文件存在。
  - `classname` 必须能在 entrypoint 源码中找到。
- `internal_filesystem/lib/mpos/content/streaming_unzip.py` 对 MPK 很严格：
  - 第一个 ZIP local header 必须是 `{fullname}/` 目录。
  - 只有一个顶层目录，所有文件都必须在该目录下。
  - 支持 `ZIP_STORED` 和 `ZIP_DEFLATED`。
  - 不允许 data descriptor flag。
  - 不符合会直接 `RuntimeError`。
- `tests/test_streaming_unzip.py` 覆盖了正确 MPK、无顶层目录、错误顶层目录、混合顶层目录、空间不足等情况。

因此 `mpos-package-app` 不能只“zip 一下目录”。它必须稳定地产生以 `{fullname}/` 为第一条目录 entry 的 MPK，并排除 `__MACOSX/`、`._*`、`.git/` 等无关文件。

### API 提取脚本现状

`mpos-dev` 已有两个关键脚本：

- `mpos-dev/scripts/extract_mpos_api.py`
  - 扫描 native MicroPython 模块并输出 MPY 用户可调用接口形态。
  - 扫描 `internal_filesystem/lib/mpos/` 的 Python 框架类、方法、函数和 docstring。
  - 输出 `reference/mpos-api-reference.md`。
- `mpos-dev/scripts/extract_lvgl_api.py`
  - 默认读取 `lvgl_micropython/lvgl.pyi`，必要时才重新生成 stub。
  - 解析 LVGL Python API，输出结构化 summary。

这说明“代码生成需要脚本提取 MicroPythonOS 和 lvgl_micropython API”的需求已经有基础，不应在 `mpos-gen-app` 里重复写一遍。建议把 API 刷新作为 `mpos-dev` 的共享脚本能力，由 `mpos-plan-app` 或 `mpos-gen-app` 在需要时调用。

2026-07-14 复核结果：`extract_lvgl_api.py` 当前默认候选已经包含 `~/lvgl_micropython` 和 `/home/leeqingshui/lvgl_micropython`，并且 `reference/lvgl_api_summary.json` 的 `source.path` 已指向 `/home/leeqingshui/lvgl_micropython/lvgl.pyi`。这个缺口已经补上，不应继续列为待办。

2026-07-14 后续更新：`extract_mpos_api.py` 已输出 `reference/mpos-api-reference.md` 和 `reference/mpos_api_summary.json`，覆盖 native MicroPython modules、`mpos.__all__` root exports、`internal_filesystem/lib/mpos/**/*.py` 全源码 public API 索引；native modules 在 JSON/MD 中只展示 MPY import/call 形态，不暴露实现源文件路径或底层签名。`extract_lvgl_api.py` 已输出 `reference/lvgl-api-reference.md` 和 `reference/lvgl_api_summary.json`，LVGL 非 widget 对象统一标为 `data_classes` / `data_class`，真实 enum class/member 进入 `symbols[]`，`*_t = int` stub 类型别名单独放入 `type_aliases[]` 并尽量映射到 runtime enum class。两个 JSON 都包含 `generated_at`、`generator`、`counts`、`symbols[]`，后续 skill 可以据此判断 reference 是否过期。

2026-07-14 API reference 复核更新：`mpos_api_summary.json` 当前由 `extract_mpos_api.py v3` 生成，统计为 5 个 native MicroPython module、1206 个 symbols、`root_export_missing=0`；`lvgl_api_summary.json` 当前由 `extract_lvgl_api.py v5` 生成，source 指向 `/home/leeqingshui/lvgl_micropython/lvgl.pyi`，统计为 60 个 `type_aliases`、90 个 enum class、873 个 enum member、79 个 data class、41 个 widget class、247 个 standalone function、3715 个 symbols。已复核两边 reference/JSON 中没有 `mp_obj_t`、`mp_map_t`、`c_binding`、`C type`、`c_mpos` 等 C/C++ 实现细节泄漏；也没有 `lv.display_render_mode_t`、`lv.grad_dir_t`、`lv.event_code_t`、`lv.fs_whence_t` 这类误导性 runtime API 符号。

### 四个 API 总结文档复核

这四个文件是后续自然语言生成 MicroPythonOS App 的核心事实源：

- `reference/mpos-api-reference.md`
- `reference/mpos_api_summary.json`
- `reference/lvgl-api-reference.md`
- `reference/lvgl_api_summary.json`

当前判断：这四个文件可以继续作为 `mpos-gen-app` / `mpos-analyze-app` / `mpos-test-app` 的 API 依据，但下游 skill 必须按 JSON schema 读取，而不是只做字符串搜索。

使用约束：

- MPOS 侧只当作 MicroPython 用户可 import/call 的接口索引。native 模块只使用 `adc_mic`、`pdm_mic`、`qrdecode`、`rvswd`、`webcam` 的 MPY 调用形态，不从 `c_mpos` 反推 C 函数。
- LVGL 侧把 `symbols[]` 作为可生成 API 的主索引，尤其是 `kind == "enum"` / `kind == "enum_member"` / `kind == "widget"` / `kind == "function"`。
- LVGL 的 `type_aliases[]` 只用于解释签名类型。`runtime_api: false` 表示不能生成 `lv.<alias>`；如果有 `runtime_enum`，应生成对应 enum class 的成员，例如 `event_code_t -> lv.EVENT.CLICKED`、`display_render_mode_t -> lv.DISPLAY_RENDER_MODE.PARTIAL`、`grad_dir_t -> lv.GRAD_DIR.VER`、`fs_whence_t -> lv.FS_SEEK.SET`。
- 方法签名里继续出现 `"display_render_mode_t"`、`"event_code_t"`、`"grad_dir_t"` 是正常的类型注解，不代表这些名字是 runtime API。反过来，`lv.area_t()`、`lv.style_t()`、`lv.anim_t()` 这类 `*_t` data class 是真实 MPY class/constructor，不能因为后缀 `_t` 一刀切删除。
- `description` 为空时，下游 skill 不应编造语义；需要解释时先看 docs reference、当前仓库代码或具体源码上下文。
- 生成代码前优先运行或检查 `generated_at`/`generator`，发现 API reference 过期时调用 `mpos-dev/scripts/extract_mpos_api.py` 与 `mpos-dev/scripts/extract_lvgl_api.py --lvgl-micropython-dir /home/leeqingshui/lvgl_micropython`。

对 skill 拆分的影响：

- `mpos-dev` 保留 API 提取脚本和四个 reference，不再把大段 API 表塞进 `SKILL.md`。
- `mpos-analyze-app` 使用 API JSON 判断是否已有 manager/framework 能满足需求，避免过早进入驱动下载。
- `mpos-gen-app` 生成前必须读取或查询四个 API reference，尤其是 LVGL enum/member，避免生成旧式 `lv.OBJ_FLAG.*`、`lv.EVENT_VALUE_CHANGED`、`lv.scr_act()`、`lv.display_render_mode_t` 之类错误代码。
- `mpos-test-app` 与 `mpos-debug-app` 可用 API JSON 做错误修复的候选 API 检索，但不能把 JSON 里的类型注解当运行时属性。

### lvgl_micropython 事实

`/home/leeqingshui/lvgl_micropython/README.md` 说明：

- 这是独立于旧 `lv_micropython` 的 LVGL binding，构建通过 `python3 make.py <target> ...`。
- 不应使用官方 binding 的信息套用到这个 binding。
- 不应手动加 submodule init 命令。
- 支持 unix/macOS 的 SDL2 特殊驱动，以及多类 display/touch IC。

MicroPythonOS 的 skill 必须优先使用本仓库生成的 `lvgl_api_summary.json`、独立 `/home/leeqingshui/lvgl_micropython/lvgl.pyi` 和项目内 AGENTS 规则，而不是泛化的 LVGL/MicroPython 记忆。

不建议把 `/home/leeqingshui/lvgl_micropython` 单独做成用户入口 skill；它更适合作为 `mpos-dev` 的 API/reference 来源，以及在涉及 display/touch driver、board port、binding 构建时由 `mpos-prepare-deps` 或 `mpos-deploy-app` 定向读取。

### 公开站点访问状态

2026-07-14 重新读取结果：

- `https://upystore.io/` 主站返回 `200`；`https://upystore.io/apps` 返回 `200`，抓取 30373 bytes；`https://upystore.io/developer` 未登录时显示 Developer Console 登录/发布页，返回 `200`，抓取 8267 bytes，并包含 `submit MPK` 文案；`https://upystore.io/app_index.json` 返回 `200`，抓取 5946 bytes；`https://upystore.io/api/v1/apps` 返回 `200`，抓取 10843 bytes。
- `upystore.io/app_index.json` 当前仍是 10 个 app 的 list，字段包括 `activities`、`category`、`download_url`、`fullname`、`icon_url`、`long_description`、`name`、`publisher`、`short_description`、`version`。`api/v1/apps` 当前返回 `apps`、`filters`、`pagination`，分页显示 `total=10`、`total_pages=1`，并额外包含 `slug`、`revision`、`tags`、`hardware_tags`、`min_os_version`、`min_api_level`、`screenshots`、`installs_count`、`downloads_count`、`stars_count`、`released_at` 等 storefront 字段。
- 本轮还按 `api/v1/apps` 的 10 个 `slug` 逐个读取公开 app detail 页面，结果为 `UPYSTORE_DETAIL_OK=10/10`；详情页包含对应 `fullname`、`name`、`version`，可用于发布后人工核对，但不应替代本地 MPK/manifest 校验。
- `https://install.micropythonos.com/` 当前 HTTPS 可直接返回 `200`，抓取 17558 bytes。页面使用 `esp-web-install-button`，包含 `WebSerial`、`USB`、`ESP32`、`ESP32-S3`、`0.15.x` 等信息；此前记录的本 VM `SSL_ERROR_SYSCALL` 状态已经过期。
- Installer 当前列出 ESP32-S3 与 ESP32 的 `0.10.x`、`0.11.x`、`0.12.x`、`0.13.x`、`0.14.x`、`0.15.x` 共 12 个 manifest。已逐个读取所有 manifest，均返回 `200` 且 `new_install_prompt_erase=true`；最新 `0.15.x` 对应版本 `0.15.1`，固件路径分别指向 `/firmware_images/esp32s3/MicroPythonOS_esp32s3_0.15.1.bin` 与 `/firmware_images/esp32/MicroPythonOS_esp32_0.15.1.bin`。
- `https://docs.micropythonos.com/` 当前 HTTPS 可直接返回 `200`，抓取 39201 bytes；`https://docs.micropythonos.com/sitemap.xml` 返回 `200`，抓取 10794 bytes；`https://docs.micropythonos.com/search/search_index.json` 返回 `200`，抓取 775522 bytes。此前记录的本 VM `SSL_ERROR_SYSCALL` 状态已经过期。
- docs sitemap 中页面 `lastmod` 为 `2026-07-13`。本轮按 sitemap 逐页读取了全部 61 个页面，结果为 `DOCS_FETCH_OK=61/61 failed=0`；重新抓取的 `search_index.json` 解析出 977 个文档/小节条目，覆盖 `Apps`、`App Lifecycle`、`Bundling Apps`、`AppStore`、`Frameworks`、`Running`、`Supported Hardware`、`DownloadManager`、`TaskManager`、`SharedPreferences`、`AppManager`、`Service` 等与 skill 拆分直接相关的内容。
- `https://web.micropythonos.com/` 返回 `200`，抓取 18555 bytes，标题是 `MicroPythonOS Web`；页面加载 `micropython.js`，在浏览器中运行 MicroPythonOS，默认 LVGL canvas 为 `320x240`，并提供 Log、Reset storage、joystick、MENU/START、X/Y/A/B、NeoPixel 模拟等控件。

### docs.micropythonos.com 事实

2026-07-14 读取 docs 首页、sitemap 和 `search_index.json` 后，与 skill 拆分直接相关的事实是：

- docs 首页把 MicroPythonOS 定义为完全由 MicroPython 构建的轻量操作系统，面向 ESP32、桌面和浏览器，包含 Android-inspired UI、App ecosystem、App Store、OTA updates。
- `Getting Started / Running` 说明预构建固件安装走 `install.micropythonos.com` 的 WebSerial installer；桌面端可以运行预构建 binary、用源码 checkout 做 app 开发，或从源码构建；Web 端可打开 `web.micropythonos.com` 或 main branch WebAssembly build。
- `Supported Hardware` 覆盖 ESP32、ESP32-S3、WebAssembly、Linux/macOS/Windows WSL2/Raspberry Pi 等目标，这支持把“Linux 端仿真”和“固件烧录”放在同一个 `mpos-deploy-app` 下、但作为不同路径处理。
- `Apps / Creating Apps` 讲 apps 安装在 `/apps/`，manifest 声明 `activities` 和 `services`，service 可用 `boot_completed` 在启动后自动运行；但该页的扁平目录示例与当前本地仓库不一致，skill 需要优先遵守本地测试。
- `Apps / App Lifecycle` 明确 Activity 生命周期包括 `onCreate`、`onStart`、`onResume`、`onPause`、`onStop`、`onDestroy`，Activity 是一个 UI screen；Service 是无 UI 的后台组件。这支持把需求分析、代码生成和测试分别识别 Activity/Service。
- `Apps / Bundling Apps` 明确 `.mpk` 是 ZIP archive，第一条 entry 必须是 app fullname 顶层目录且只能有一个顶层目录；这与本地 `StreamingUnzip` 和 `tests/test_streaming_unzip.py` 一致。
- `Apps / AppStore` 说明 AppStore 可从多个 backend 拉取 app，并把 apps 作为 `.mpk` 安装到 `/apps/`。这支持 `mpos-publish-app` 只准备和验证包，不把 upystore 上传混进设备端安装逻辑。
- `Frameworks` 文档推荐应用直接从主 `mpos` 模块导入 framework，例如 `from mpos import AppManager, DisplayMetrics`，避免从 `mpos.ui`、`mpos.content` 等子模块导入；`DownloadManager`、`TaskManager`、`SharedPreferences`、`AppManager`、`Service` 等页面给出了代码生成阶段需要查阅的 API 类型。

说明：本轮已经按 sitemap 逐页读取 docs 的 61 个页面，并同时用 `search_index.json` 的 977 个页面/小节条目做覆盖校验；但没有把 61 个页面逐字全文转存成离线 reference 文件。对 skill 来说，这种“全站全文直接塞入 SKILL.md”的方式也不合适。

当前已经把 docs 内容拆成 `mpos-dev/reference/` 下的专题参考文件，而不是做一个巨大 reference：

```text
mpos-dev/reference/
  docs-app-model.md          # apps/creating-apps, app-lifecycle, appstore
  docs-packaging.md          # bundling-apps, MPK, AppStore packaging
  docs-frameworks.md         # framework overview + manager 索引
  docs-deploy-targets.md     # running, supported-hardware, desktop, ESP32, web port
  docs-os-development.md     # compiling, testing, porting, release checklist
  docs-web-port.md           # web-port/using, web-port/developer, web.micropythonos.com
  docs-site-index.md         # sitemap 覆盖和 reference 路由审计
```

其中 `SKILL.md` 只保留“什么时候读哪个 reference”的路由规则。这样符合 progressive disclosure：生成 App 时只读 app model 和 framework 摘要，打包时只读 packaging，部署/仿真时只读 deploy targets 和 web port。

### web.micropythonos.com 事实

`https://web.micropythonos.com/` 是 MicroPythonOS 的浏览器/WebAssembly 运行入口，不是安装站点，也不是 app 发布站点。2026-07-14 读取到的页面事实是：

- 页面标题为 `MicroPythonOS Web`，加载 `micropython.js`，通过 Emscripten 在浏览器中运行 MicroPythonOS。
- 页面默认显示 `320x240` LVGL canvas，对应 MicroPythonOS 默认显示 profile。
- 页面提供模拟 badge 外设：NeoPixel 指示灯、joystick、MENU、START、X/Y/A/B 按钮；这些通过 `Module.__webio` 与 Python 侧 `_webio`/fake WebExpander 交互。
- 页面把 `/data` 和 `/apps` 挂载到 IndexedDB/IDBFS，使 app preferences 和用户安装的 apps 在刷新后保留。
- 页面提供 `Reset storage`，会删除持久化的 `/data` 和 `/apps` 并重载页面。
- 运行参数是 `["-X", "heapsize=16M", "-m", "main"]`，即用 16MB heap 启动 frozen `main` 模块。
- 该入口适合写入 `mpos-deploy-app`/`mpos-test-app` 的参考资料：用于浏览器端 smoke test、用户快速预览、Web port 限制说明；不应替代 Linux SDL 桌面仿真或真实设备验证。

### upystore.io 事实

2026-07-14 读取到的主站、Apps 页、Developer 登录页、`app_index.json` 和 `api/v1/apps` 显示：

- upystore 是面向 MicroPython/uPyOS 硬件的 app store，主站导航包含 Home、Apps、Developer Console、Log in、Sign up、英文/中文切换。
- 首页强调 Browse、Install、Publish 三步，面向 D-Shell/uPyOS 设备，支持应用分类、版本历史、硬件画像/匹配、安装统计、发布者信息、图标、截图、release notes 和 hardware requirements。
- Apps 页当前显示 10 个 app，分类包括 IoT、Motor Control、AI、Communication、Games、Media、Education、Development Tools、Utilities，并提供搜索、分类过滤、下载量、安装量、stars、版本号等字段。
- Developer Console 未登录时进入登录页，页面文案明确需要 developer account 才能 submit MPK packages、manage apps、review app statistics。因此 `mpos-publish-app` 不应自动登录或请求账号密码，只应给上传链接和发布前/发布后验证清单。
- `app_index.json` 当前字段包括 `name`、`publisher`、`short_description`、`long_description`、`icon_url`、`download_url`、`fullname`、`version`、`category`、`activities` 等，格式总体贴近 MicroPythonOS AppStore 需要。
- 当前 upystore 数据存在两种 `activities` 形态：`Show Battery` 和 `Danke` 使用完整对象数组（`classname`、`entrypoint`、`intent_filters`），一些 seed/sample app 使用字符串数组（如 `clock`、`timer`）。发布 skill 生成 metadata 时必须输出完整 manifest 形态，不能照抄 seed 数据的字符串 activity。
- `api/v1/apps` 比 `app_index.json` 多出 `slug`、`revision`、`tags`、`hardware_tags`、`min_os_version`、`min_api_level`、`screenshots`、`installs_count`、`downloads_count`、`stars_count`、`released_at`、`pagination` 等 storefront 字段；这些适合发布摘要和上传后核对，不应替代本地 `MANIFEST.JSON`。
- upystore 上传本身应保持为用户操作：skill 准备 MPK、icon、元数据摘要和校验结果，然后推荐用户访问 `https://upystore.io/` 或 Developer Console 上传。上传后如果用户提供下载 URL 或 app_index/API 返回值，skill 再做 MPK 顶层目录和设备端安装验证。
- 本地 `MicroPythonOS/docs/upystore-integration-analysis_CN.md` 的旧结论仍然关键：设备端不应放宽 `StreamingUnzip` 校验；打包/上传侧必须保证 MPK 第一个 ZIP entry 是 `{fullname}/`，排除 `__MACOSX/`、`._*` 等垃圾文件。


## 对话式 skill 的基本写法

对话式不是把说明写得很长，而是让每个阶段有清晰的输入、输出和下一步。建议每个阶段都使用一个轻量状态对象，例如：

```json
{
  "app_fullname": "com.example.weather",
  "app_name": "Weather",
  "phase": "generate",
  "target": "desktop-first",
  "requirements": [],
  "dependencies": [],
  "artifacts": {
    "app_dir": "internal_filesystem/apps/com.example.weather",
    "manifest": "internal_filesystem/apps/com.example.weather/META-INF/MANIFEST.JSON",
    "mpk": null
  },
  "open_questions": [],
  "verification": []
}
```

原则：

- 编排 skill 只问必要的阻塞问题，不一次性问长问卷。
- 每个阶段 skill 接收上游状态，产出可交接的 artifact，而不是只输出自然语言结论。
- 用户明确要“从一句话到完成”时，入口 skill 顺序调用阶段 skill；用户明确只要测试/打包/发布时，直接触发对应 skill。
- 高风险动作必须分开：生成代码、烧录固件、擦除文件系统、上传发布不能混在一个 skill 里默认执行。
- SKILL.md 保持短，详细规则放 `references/`，确定性动作放 `scripts/`。

## 建议 Skill 设计

### 1. `mpos-dev`：共享基础层

定位：所有 MicroPythonOS App skill 的基础知识库，不作为用户主要入口。

保留内容：

- MicroPythonOS 目录结构、Activity/App/Service 生命周期。
- LVGL 9.x/micropython binding 约束。
- Native MicroPython 模块 API 速查。
- 全局约束：ruff 双引号、临时文件放项目 `tmp/`、桌面运行用 timeout、调试杀进程用 `killall`。
- `extract_mpos_api.py` 和 `extract_lvgl_api.py`。

已完成或应继续保持：

- App 结构示意应继续以当前仓库实际结构为准：`META-INF/MANIFEST.JSON`、`assets/*.py`、`res/mipmap-mdpi/icon_64x64.png`。
- 已在 `reference/docs-app-model.md` / `reference/docs-packaging.md` 记录在线 docs 当前扁平 app 示例与本地仓库/测试约束不一致；生成和打包以本地测试为准，docs 只作背景参考。
- 明确 `from mpos import Activity` 是 docs 推荐的统一导入方式，同时也可从 `mpos.app.activity import Activity` 导入；新 skill 应优先使用主 `mpos` re-export，除非当前代码已有局部惯例。
- `extract_lvgl_api.py` 默认路径已经覆盖 `/home/leeqingshui/lvgl_micropython`；涉及其他 binding checkout 时仍可显式传 `--lvgl-micropython-dir`。
- 已让 MicroPythonOS 与 LVGL API reference 同时具备 MD/JSON 双格式；JSON 包含生成时间、统计和符号索引，便于判断是否过期。

当前/建议资源：

```text
mpos-dev/
  SKILL.md
  reference/docs-app-model.md
  reference/docs-packaging.md
  reference/docs-frameworks.md
  reference/docs-deploy-targets.md
  reference/docs-os-development.md
  reference/docs-web-port.md
  reference/docs-site-index.md
  reference/mpos-api-reference.md
  reference/mpos_api_summary.json
  reference/lvgl-api-reference.md
  reference/lvgl_api_summary.json
  reference/lvgl-rules.md      # 可选：如果 SKILL.md 中 LVGL 规则继续变长，再拆出
  scripts/extract_mpos_api.py
  scripts/extract_lvgl_api.py
```

### 2. `mpos-plan-app`：对话式入口/编排

触发：

- 用户说“帮我做一个 MicroPythonOS App”。
- 用户只给自然语言功能描述，希望从需求到生成、测试、打包、部署。
- 用户问“下一步该做什么”“继续完成这个 app”。

职责：

- 把用户自然语言转为阶段状态。
- 选择是否进入需求分析、依赖准备、代码生成、测试、打包、部署、发布。
- 维护开放问题，但只问真正阻塞的问题，例如 App 名称/fullname、是否需要硬件、目标设备、是否允许烧录。
- 调用下游 skill，不亲自写所有实现细节。

不做：

- 不直接下载不明驱动。
- 不直接烧录。
- 不自动上传 upystore。

输出：

- 当前 phase。
- App 目录/manifest/测试/MPK 等 artifact 路径。
- 下一步建议和需要用户确认的高风险动作。

### 3. `mpos-analyze-app`：需求分析

触发：

- 用户给出 App 想法但没有明确功能边界。
- 需要把需求转为 manifest、Activity、Service、数据持久化、硬件权限/依赖计划。

职责：

- 识别 App 类型：纯 UI、工具、游戏、网络、音频、相机、传感器、后台服务。
- 产出最小可行功能、非目标、风险点。
- 建议 `fullname`、`name`、`category`、`activities`、`services`。
- 判断是否需要：
  - `SharedPreferences`
  - `TaskManager`
  - `DownloadManager`
  - `CameraManager`
  - `AudioManager`
  - `SensorManager`
  - 外部 MicroPython 驱动
  - C 模块或固件重编译
- 明确测试策略：普通 unittest、GraphicalTestCase、手动硬件测试、设备端验证。

输出建议：

```json
{
  "manifest_draft": {},
  "feature_slices": [],
  "dependency_plan": [],
  "test_plan": [],
  "blocking_questions": []
}
```

### 4. `mpos-prepare-deps`：驱动下载与依赖准备

触发：

- App 需要外部传感器/显示/网络/服务 SDK。
- 用户说“下载驱动”“找库”“这个硬件没有驱动”。
- `mpos-analyze-app` 标记存在依赖缺口。

职责：

- 优先检查 MicroPythonOS 内置能力和 managers，不重复引入外部驱动。
- 需要 MicroPython 驱动时，复用现有 `fetch-doc`、`upy-pkg-guide`、`upy-gen-driver` 的资料检索和缺失驱动能力。
- 下载或整理依赖到 App 的 `assets/` 或共享 `lib/`，并记录来源、版本、许可证。
- 判断是否必须重编译固件：如果是 Python 驱动，通常不需要；如果是 C 模块、LVGL/display binding、固件组件，才进入固件构建/烧录链路。

边界：

- 这不是 `upy-select-hw`。MicroPythonOS App 通常运行在已有设备/系统镜像上，不应默认重新做 MCU/引脚选型。
- 外设引脚和目标板相关时，应要求用户提供设备/板卡，或读取 `internal_filesystem/lib/mpos/board/*.py`。

建议脚本：

- `scripts/vendor_python_module.py`：把单文件/目录驱动放入 app assets 或 lib，并生成来源记录。
- `scripts/check_dependency_imports.py`：静态检查 App entrypoint 的 import 是否能在 MPOS 树或 vendor 目录中找到。

### 5. `mpos-gen-app`：代码生成

触发：

- 用户要创建/修改 MicroPythonOS App。
- 上游已有需求分析和依赖计划。

职责：

- 创建或修改 `internal_filesystem/apps/<fullname>/`。
- 生成 `META-INF/MANIFEST.JSON`。
- 生成 `assets/*.py` 中的 Activity/Service 代码。
- 创建或补齐 `res/mipmap-mdpi/icon_64x64.png`。
- 使用 `mpos-dev` 的 API reference 和 LVGL rules。
- 对 UI 代码严格遵守本仓库 LVGL 约束。

必须修正的生成规则：

- 当前 `mpos-gen-app/SKILL.md` 的目录示意仍把 Activity/Service 文件放在 app 根目录，且 manifest 示例里的 `entrypoint` 缺少 `.py`；这会直接生成不通过 `tests/test_apps_manifest.py` 的 app，必须优先修。
- `entrypoint` 应优先用 `assets/main.py` 或 `assets/<app>.py`，必须带 `.py` 后缀，并确保文件存在。
- Activity 类名必须在 entrypoint 代码中出现。
- 如果自定义 `__init__`，必须 `super().__init__()`。
- 新建 label 必须显式 `set_text("")` 或设置目标文本。
- `style_t()` 后必须 `init()`。
- 不硬编码屏幕分辨率，优先 `lv.pct(100)`、flex、align。
- 持久化使用 `SharedPreferences(self.appFullName)`。
- 后台/异步用 `TaskManager`，UI 更新需要在前台或主线程安全路径。

建议 resources：

```text
mpos-gen-app/
  SKILL.md
  references/app-patterns.md
  references/lifecycle.md
  assets/templates/basic_app/
  assets/templates/service_app/
  scripts/validate_manifest.py
```

### 6. `mpos-test-app`：测试与质量门禁

现有 skill 基本方向正确。

触发：

- 用户要验证 App、写测试、修 bug 前复现。
- 生成或修改 App 后自动进入测试阶段。

职责：

- 运行或指导运行：
  - `make lint`
  - `make syntax-tests`
  - `./tests/unittest.sh`
  - 单个测试文件
  - 图形化测试
- 使用 `mpos.ui.testing.GraphicalTestCase`、`KeyboardTestCase`。
- 使用 `scripts/mpos_controller.py` 做桌面或串口自动化。
- 对截图用 widget tree/visible text/pixel 检查，不只靠肉眼描述。

建议补强：

- 增加“新 App 最小测试模板”。
- 增加“manifest 测试失败如何修”的 quick path。
- 增加“MPK 打包后用 `test_streaming_unzip` 规则验证”的引用，但实际打包验证归 `mpos-package-app`。

### 7. `mpos-package-app`：App 打包

触发：

- 用户说“打包 app”“生成 MPK”“准备上传 AppStore/upystore”。
- 代码生成和测试完成后进入发布准备。

职责：

- 读取 `internal_filesystem/apps/<fullname>/META-INF/MANIFEST.JSON`。
- 校验 manifest 与文件结构。
- 确保 icon 存在，路径为 `res/mipmap-mdpi/icon_64x64.png`。
- 生成单 App MPK。
- 生成或输出 app_index 条目，包括：
  - `icon_url`
  - `download_url`
  - `fullname`
  - `version`
  - `activities`
  - `services`
- 验证 MPK 的第一条 ZIP entry 是 `{fullname}/` 目录。

为什么需要独立 skill：

- `scripts/bundle_apps.sh` 是全量打包脚本，有 blacklist 和 app store 批量输出逻辑，不适合作为用户对话中“只打包当前 App”的唯一入口。
- MPK 规范严格，错误包会在设备端下载时失败。这个阶段需要确定性脚本。

建议脚本：

```text
mpos-package-app/
  scripts/package_mpos_app.py
  scripts/validate_mpk.py
  scripts/emit_app_index_entry.py
```

`package_mpos_app.py` 应保证：

- zip 内第一条 entry 是 `{fullname}/`。
- 文件顺序稳定。
- 修改时间可固定，便于可重复构建。
- 排除 `.git/`、`__pycache__/`、`*.pyc`、`__MACOSX/`、`._*`。
- 可选择 stored 或 deflated，但要符合 `StreamingUnzip` 支持范围。

### 8. `mpos-deploy-app`：Linux 仿真、设备安装和固件烧录

触发：

- 用户说“在 Linux 端仿真”“运行桌面模拟器”“安装到设备”“烧录固件”“刷机”。
- 打包前后需要真实运行验证。

职责拆分：

- 桌面仿真：
  - 确认已有 `lvgl_micropython/build/lvgl_micropy_unix`。
  - 若没有，指导或运行 `make build-mpos-unix`。
  - 使用 `timeout -s 9 30 ./scripts/run_desktop.sh <app_fullname>`。
  - 需要交互时用 `scripts/mpos_controller.py`。
- App 安装到设备：
  - 使用 `scripts/install.sh <fullname>` 或 mpremote 单文件复制。
  - 安装后提醒执行 `AppManager.refresh_apps()` 或重启。
  - 复用 `mpremote-device-interaction`、`mpremote-file-transfer`、`mpremote-live-session`。
- 固件烧录：
  - 只有在固件不存在、C 模块变更、系统镜像变更、用户明确要求刷机时才进入。
  - 使用 `scripts/build_mpos.sh <target>` 和 `scripts/flash_over_usb.sh`。
  - 烧录、擦除、重置都需要明确确认。

边界：

- “安装 App”不是“烧录固件”。绝大多数 Python App 迭代只需复制 app 目录或安装 MPK。
- “Linux 端仿真”不是 PC 端 mock 项目，它运行 MicroPythonOS 的 unix build 和 SDL LVGL。

### 9. `mpos-publish-app`：upystore 发布指导

触发：

- 用户说“上传到 upystore”“发布 App”“准备 AppStore 上架”。

职责：

- 确认已通过：
  - manifest 校验
  - 测试
  - MPK 格式校验
  - 图标存在
  - 版本号递增
- 输出发布包路径和元数据摘要。
- 明确 upystore Developer Console 需要用户登录 developer account；skill 不请求、不保存账号密码。
- 引导用户打开 `https://upystore.io/` 或 Developer Console 上传。
- 告知上传后建议验证：
  - app_index 中字段是否完整。
  - 下载得到的 MPK 是否仍保留 `{fullname}/` 顶层目录。
  - 设备端 AppStore 是否能安装。

不做：

- 不自动替用户上传。
- 不保存或请求 upystore 账号密码。
- 不把 upystore 当成固件发布站点。固件发布和 `install.micropythonos.com` 属于另一条流程。

## 现有 skill 的复用与调整建议

### 已有 `mpos-*`

当前 `MicroPython_Skills` 中已有：

- `mpos-dev`
- `mpos-gen-app`
- `mpos-test-app`
- `mpos-debug-app`

它们可以作为新体系的基础，但还不完整：

- 缺少对话式入口/编排。
- 缺少需求分析阶段。
- 缺少驱动/依赖准备阶段。
- 缺少单 App MPK 打包阶段。
- 缺少“安装 App”和“烧录固件”分开的部署阶段。
- 缺少 upystore 发布指导阶段。
- `mpos-gen-app` 的 App 结构示意需要对齐实际 `assets/*.py` 模式，manifest 示例的 `entrypoint` 必须带 `.py` 后缀。

### 旧 `upy-*` 的角色

可复用但不要直接当 MicroPythonOS 主链：

- `fetch-doc`：可用于驱动资料、GitHub、URL 内容补充。
- `upy-pkg-guide`：可用于 MicroPython 驱动包用法查询。
- `upy-gen-driver` / `upy-gen-driver-plugin`：可用于缺失驱动分支。
- `mpremote-*`：可用于设备连接、文件复制、长会话。
- `upy-deploy`：思想可参考，但 MicroPythonOS App 安装应优先走 `scripts/install.sh`、MPK、AppManager 流程。

不建议直接复用为 MPOS 主链的部分：

- `upy-select-hw`：它面向 MCU/引脚/固件选型，MicroPythonOS App 默认已有目标系统。
- `upy-scaffold`/`upy-generate`：它们生成普通 MicroPython firmware 项目，不等同于 MPOS App 的 Activity/manifest/MPK。
- `upy-simulate`：它是 PC CLI/rich 模拟，不等同于 MicroPythonOS unix SDL 桌面仿真。

## 推荐实现顺序

1. 先修正并巩固 `mpos-dev`。
   - 对齐 App 目录事实。
   - 确保 API 提取脚本可运行并更新 reference。
2. 增强 `mpos-gen-app`。
   - 加 manifest validator。
   - 加基础 App 模板。
   - 生成 `assets/*.py`。
3. 新增 `mpos-package-app`。
   - 这是发布链路最容易出错、最适合脚本化的阶段。
4. 新增 `mpos-deploy-app`。
   - 明确桌面仿真、App 安装、固件烧录三条路径。
5. 新增 `mpos-analyze-app` 和 `mpos-plan-app`。
   - 前面阶段稳定后，再做对话式编排入口，避免入口 skill 只会“口头规划”。
6. 新增 `mpos-prepare-deps`。
   - 复用 `fetch-doc`、`upy-pkg-guide`、`upy-gen-driver`。
7. 新增 `mpos-publish-app`。
   - 只做发布前检查、上传指引、上传后验证，不自动上传。

## 每个 SKILL.md 的写法模板

每个 skill 的 `description` 要包含“做什么 + 何时触发”，因为这是 Codex 触发 skill 的主要依据。正文只保留必要流程和资源导航。

示例：

```markdown
---
name: mpos-package-app
description: Package and validate MicroPythonOS Apps as MPK files for AppStore/upystore release. Use when Codex needs to create a .mpk, validate MANIFEST.JSON, emit app_index metadata, or prepare an MPOS App for publishing.
---

# MicroPythonOS App Packaging

## Workflow

1. Read `mpos-dev` for MPOS App and MPK constraints.
2. Locate `internal_filesystem/apps/<fullname>/META-INF/MANIFEST.JSON`.
3. Run `scripts/validate_manifest.py`.
4. Run `scripts/package_mpos_app.py --app <fullname>`.
5. Run `scripts/validate_mpk.py <mpk> --fullname <fullname>`.
6. Report MPK path and app_index metadata.

## Constraints

- The first ZIP entry must be `<fullname>/`.
- Exclude `__MACOSX/`, `._*`, `.git/`, `__pycache__/`, `*.pyc`.
- Do not publish or upload automatically.
```

## 最小脚本清单

为了让 skill 真正可执行，建议至少补这些脚本：

| 脚本 | 所属 skill | 用途 |
|---|---|---|
| `scripts/validate_manifest.py` | `mpos-gen-app` 或 `mpos-package-app` | 复刻 `test_apps_manifest.py` 中的单 App 校验 |
| `scripts/package_mpos_app.py` | `mpos-package-app` | 单 App 生成规范 MPK |
| `scripts/validate_mpk.py` | `mpos-package-app` | 检查 ZIP entry 顺序、顶层目录、非法文件 |
| `scripts/emit_app_index_entry.py` | `mpos-package-app` | 根据 manifest 和 base URL 输出 app_index 条目 |
| `scripts/check_dependency_imports.py` | `mpos-prepare-deps` | 静态检查 App import 来源 |
| `scripts/run_app_desktop.py` | `mpos-deploy-app` | 包装 `run_desktop.sh` + timeout + app 启动 + 日志采集 |

已有脚本继续保留：

- `mpos-dev/scripts/extract_mpos_api.py`
- `mpos-dev/scripts/extract_lvgl_api.py`

## 对用户原始设想的逐项回应

> 需求分析

应该独立成 `mpos-analyze-app`，并由 `mpos-plan-app` 调用。它输出 manifest 草案、功能切片、依赖计划、测试计划，而不是直接写代码。

> 驱动下载

应该独立成 `mpos-prepare-deps`。但默认先查 MicroPythonOS 内置 managers 和 `mpos/board`，不要一上来下载普通 MicroPython 驱动。确实缺驱动时复用 `fetch-doc`、`upy-pkg-guide`、`upy-gen-driver`。

> 代码生成，需要脚本提取 MicroPythonOS 和 lvgl_micropython API

代码生成仍由 `mpos-gen-app` 做。API 提取脚本应放在共享 `mpos-dev`，现有 `extract_mpos_api.py` 和 `extract_lvgl_api.py` 已经是正确方向。代码生成 skill 应先读取/刷新 reference，再生成代码。

> `/home/leeqingshui/lvgl_micropython`

它应作为 LVGL binding 的事实来源之一，但不要直接套官方 LVGL binding 文档。优先使用本地生成的 `lvgl.pyi`/`lvgl_api_summary.json` 和 `MicroPythonOS/AGENTS.md` 的约束。它不建议单独作为用户入口 skill；更合理的是被 `mpos-dev` 的 API 提取/reference 层管理，必要时由依赖准备或部署阶段显式传入 `--lvgl-micropython-dir /home/leeqingshui/lvgl_micropython`。

> App 打包

应该独立成 `mpos-package-app`。这是发布链路的关键风险点，必须脚本化验证 MPK 顶层目录和 manifest。

> Linux 端仿真和烧录 App

建议合并成 `mpos-deploy-app`，但内部必须分三条路径：

- Linux 桌面仿真：`make build-mpos-unix` + `timeout -s 9 30 ./scripts/run_desktop.sh <app>`。
- 安装 App 到设备：`scripts/install.sh <fullname>` 或 mpremote 文件复制。
- 烧录固件：只有用户确认需要刷机时，才走 `build_mpos.sh`/`flash_over_usb.sh`。

“烧录 App”这个说法建议在 skill 里改成“安装 App 到设备”；“烧录”保留给固件镜像。

> 上传到 upystore

应该独立成 `mpos-publish-app`，但只做发布前检查、产物路径整理和上传链接提示。推荐用户自行访问 `https://upystore.io/` 上传。上传后如果用户提供下载 URL 或 app_index，可以让 skill 做 MPK 结构和设备端安装验证。

## 最终建议的用户体验

用户说：

> 做一个 MicroPythonOS 天气 App，能显示温度和网络状态，帮我打包上传 upystore。

理想流程：

1. `mpos-plan-app` 建立状态，询问 App 名/fullname 或给默认建议。
2. `mpos-analyze-app` 输出功能、manifest 草案、依赖和测试计划。
3. `mpos-prepare-deps` 确认是否需要网络 API SDK 或只用 `DownloadManager`。
4. `mpos-gen-app` 通过 `mpos-dev` 检查或刷新 `mpos_api_summary.json` / `lvgl_api_summary.json`，确认 API reference 没过期。
5. `mpos-gen-app` 生成 `internal_filesystem/apps/<fullname>/...`。
6. `mpos-test-app` 跑 lint/syntax/graphical 测试。
7. `mpos-deploy-app` 在 Linux 桌面仿真运行，必要时设备安装。
8. `mpos-package-app` 生成并验证 `.mpk`。
9. `mpos-publish-app` 给出发布摘要和 `https://upystore.io/` 上传指引。

这样拆分后，每个 skill 都短、可触发、可测试，也符合 skill-creator 的 progressive disclosure 原则。
