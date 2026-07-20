# MicroPythonOS Skill 知识索引

生成日期：2026-07-14
最近更新：2026-07-20

这个文件是本次对话中形成的 MicroPythonOS / LVGL / mpos-* skill 知识总入口。它不是某一个具体 skill 的执行说明，而是给后续维护者和 Codex 快速定位资料用的索引：哪些目录是源头，哪些文件是参考文档，哪些 API 是脚本提取的，哪些外部站点需要重新同步。

正文使用中文；代码、命令、路径、API 名、JSON 字段名保持英文。

## 1. 总体结论

- `mpos-dev` 应继续作为 `mpos-*` skill 家族的共享基础层，放置 MicroPythonOS 架构、LVGL 约定、官方 docs 专题参考、API 提取脚本和生成出的 reference 文件。
- 当前 `mpos-*` 主链已经补齐为：`mpos-plan-app` -> `mpos-analyze-app` -> `mpos-prepare-deps` -> `mpos-gen-app` -> `mpos-test-app` -> `mpos-package-app` -> `mpos-deploy-app` -> `mpos-publish-app`，外加共享 `mpos-dev`。
- 所有面向单个 App 的阶段 skill 应统一维护 `<repo-root>/tmp/mpos-plan-app/<fullname>/plan_state.json` 和 `activity_log.jsonl`，并通过 `mpos-plan-app/scripts/update_plan_state.py` 登记阶段产物，便于中断、恢复、用户改需求和 AI 调试。
- 新 App 默认使用 flat 布局：`MANIFEST.JSON`、`icon_64x64.png`、`assets/*.py`。旧 `META-INF/MANIFEST.JSON` 和 `res/mipmap-mdpi/icon_64x64.png` 只做兼容读取，并必须 warning。
- `/home/leeqingshui/MicroPythonOS` 主仓库应尽量保持和上游一致。build、desktop simulator、web preview、联调测试默认放在隔离 clone/worktree/临时副本中；除新增 App 或用户明确允许外，不修改 OS/build 源码。
- `docs.micropythonos.com` 的内容已经被拆成多个专题 reference 文档，便于按任务读取；这不是逐字全文镜像。是否覆盖全部页面，应以 `mpos-dev/reference/docs-site-index.md` 里的 sitemap/search index 审计为准。
- `web.micropythonos.com` 属于 WebAssembly/browser runtime 资料，应同时出现在 `mpos-dev/reference/docs-web-port.md` 和根级分析文件 `mpos-conversational-skills-analysis.md` 的路线图中。
- LVGL API 的源头应是编译/生成后的 MicroPython stub：`/home/leeqingshui/lvgl_micropython/lvgl.pyi`，不是直接从 LVGL C 头文件猜 API。
- MicroPythonOS API 提取应只提取 MicroPython 可见 API：native MicroPython 模块的 import/call 形态、模块 globals、type locals、以及 `mpos.__all__` 导出的 Python API；不要把内部实现函数、底层签名或实现源文件当成公开 API。
- 机器检索优先用 JSON，人读和 Codex 快速扫读需要 MD。当前已补齐 `mpos_api_summary.json`、`mpos-api-reference.md`、`lvgl_api_summary.json` 与 `lvgl-api-reference.md`；mpos 相关 skill 必须完整读取 API summary，不能按任务难度省略。

## 2. 本地根目录

### `/home/leeqingshui/MicroPython_Skills`

这是 skill 仓库和本次新增索引所在目录。

关键文件：

- `mpos-skill-knowledge-index.md`：当前文件，本次对话知识总索引。
- `mpos-conversational-skills-analysis.md`：mpos skill 家族拆分与对话式能力分析，之前要求把 `https://web.micropythonos.com/` 也纳入这里。
- `README.md`：仓库级说明。

当前与 MicroPythonOS 相关的 skill：

- `mpos-dev/`：共享基础知识库，包含 API reference、docs reference、提取脚本。
- `mpos-plan-app/`：对话式入口和状态机，负责阶段编排、中断恢复、失效清单确认和默认跑到发布交接。
- `mpos-analyze-app/`：把自然语言需求转成 App 身份、manifest 草案、Activity/Service 计划、依赖风险和测试/部署计划。
- `mpos-prepare-deps/`：准备应用层纯 Python/MPY 依赖，缓存搜索结果，支持 async/aio/uasyncio 搜索策略；同步库必须标 `sync_needs_adapter=true` 交给生成阶段做非阻塞封装。
- `mpos-gen-app/`：两阶段生成、更新、修复 App 文件；强制先输出计划并等待确认，执行后立即跑 manifest、syntax、MPY import、API usage、`make lint`、flake8、pylint、App-only 变更检查等静态门禁并产出 `generation_result.json`。
- `mpos-test-app/`：只做目标 App 的 MPOS runtime smoke/可选 Web Port 检查，使用 MicroPythonOS 内置 `run_desktop.sh`、`mpos_controller.py` 等工具；不拥有静态 lint/manifest/API 门禁，但必须复核 `generation_result.json` 已记录这些门禁。
- `mpos-package-app/`：生成单 App `.mpk`、`app_index_entry.json` 和 `package_result.json`，默认 `stored` 压缩；测试缺失或失败时可继续打包但必须 warning。
- `mpos-deploy-app/`：只做部署/预览路径，包括 desktop-preview、web-preview、device-copy、mpk-install、install-site、local-flash；先确认物理设备、串口和 MicroPythonOS 安装状态，desktop/manual launch 只是可选预览，不是 smoke gate。
- `mpos-publish-app/`：只做 upystore 发布指导和校验，必须同时读取 `package_result.json`、`app_test_result.json`、`deploy_result.json`，并产出 `publish_result.json`；不登录、不上传。

### `/home/leeqingshui/MicroPythonOS`

这是 MicroPythonOS 主仓库。

关键目录：

- `AGENTS.md`：本地最高优先级工程约束和 LVGL/MicroPythonOS 注意事项。
- `internal_filesystem/`：一对一映射到设备文件系统的核心目录。
- `internal_filesystem/lib/mpos/`：MicroPythonOS Python 框架代码，`mpos.__all__` 是公开 Python API 的重要来源。
- `internal_filesystem/apps/`：已安装 App。
- `internal_filesystem/builtin/`：内置资源或内置应用相关内容。
- `c_mpos/src/`：native MicroPython 模块实现源码，如 `webcam`、`pdm_mic`、`adc_mic`、`qrdecode`、`rvswd`；reference 输出只展示 MPY 用户可调用接口。
- `docs/`：本地 docs 源文件。
- `scripts/`：构建、运行、安装、烧录、部署、controller 等脚本；之前确认这里不是 API 提取脚本目录。
- `tests/`：语法测试、单元测试、controller 测试等。
- `lvgl_micropython/`：MicroPythonOS 仓库内的 LVGL 子模块。

重要规则：当官方文档示例和当前仓库实际代码冲突时，优先当前仓库和 `AGENTS.md`。

### `/home/leeqingshui/lvgl_micropython`

这是独立的 `lvgl_micropython` 仓库。当前 LVGL API 提取应优先使用这里的：

- `lvgl.pyi`：MicroPython LVGL API 的 stub，当前 API 总结 JSON 的 source-of-truth。
- `gen/lvgl_api_gen_mpy.py`
- `gen/stub_gen.py`
- `gen/fixed_gen_json.py`
- `gen/api_gen/*`
- `stubs/*.pyi`
- `build/*.bin`

注意：`/home/leeqingshui/MicroPythonOS/lvgl_micropython` 和 `/home/leeqingshui/lvgl_micropython` 都存在。对话中已明确，skill 的 LVGL API 提取应针对独立仓库的 `/home/leeqingshui/lvgl_micropython/lvgl.pyi`，因为它代表当前编译/生成后的 MicroPython binding API。

## 3. `mpos-dev` 文件结构和职责

`/home/leeqingshui/MicroPython_Skills/mpos-dev` 是共享基础层。

关键文件：

- `SKILL.md`：MicroPythonOS 基础开发知识库入口，包含架构、LVGL 约定、native MicroPython 模块速查和 reference 路由。
- `scripts/extract_lvgl_api.py`：从 `lvgl.pyi` 提取 LVGL MicroPython API，当前输出 `reference/lvgl_api_summary.json` 和 `reference/lvgl-api-reference.md`。
- `scripts/extract_mpos_api.py`：从 MicroPythonOS 主仓库提取 MicroPython 可见 API，当前输出 `reference/mpos_api_summary.json` 和 `reference/mpos-api-reference.md`。

`reference/` 当前文件：

- `docs-site-index.md`：docs 站点覆盖索引，记录 sitemap/search index 覆盖情况。
- `docs-app-model.md`：App 模型、Activity、Service、Intent、本地 layout override。
- `docs-packaging.md`：`.mpk`、Store、`upystore`、BadgeHub、manifest、app index。
- `docs-frameworks.md`：系统 managers、framework API、LVGL 使用规则。
- `docs-deploy-targets.md`：Linux 桌面、浏览器、设备、固件、QEMU、目标设备。
- `docs-os-development.md`：构建、测试、移植、发布、OS 级开发。
- `docs-web-port.md`：WebAssembly/browser runtime、`web.micropythonos.com`、web target。
- `mpos-api-reference.md`：MicroPythonOS mpy-visible API 人读参考。
- `mpos_api_summary.json`：MicroPythonOS 用户可调用 API 机器可读索引，含 `native_modules`、root exports、全源码 public API、`source_index` 和 `symbols[]`。
- `lvgl-api-reference.md`：LVGL MicroPython API 人读参考。
- `lvgl_api_summary.json`：LVGL MicroPython API 机器可读总结。

## 4. mpos 阶段交接产物

统一交接目录：

```text
<repo-root>/tmp/mpos-plan-app/<fullname>/
  plan_state.json
  activity_log.jsonl
```

标准 artifact key：

- `analysis_result`：`mpos-analyze-app` 需求分析结果。
- `dependency_handoff`：`mpos-prepare-deps` 依赖文件、缓存、同步适配需求。
- `generation_result`：`mpos-gen-app` 写文件和静态门禁记录。
- `app_test_result`：`mpos-test-app` runtime smoke/Web Port 记录。
- `package_result`：`mpos-package-app` MPK、app_index_entry 和打包 warning。
- `deploy_result`：`mpos-deploy-app` desktop/web/device/MPK install 预览或部署记录。
- `publish_result`：`mpos-publish-app` upystore 版本对比、store metadata 和发布交接。

维护规则：

- 不手写 `plan_state.json` 或 `activity_log.jsonl`；使用 `mpos-plan-app/scripts/update_plan_state.py record/discover/invalidate`。
- 用户中断后说“继续/恢复/下一步”时，先读取或重建 `plan_state.json`，不要从头开始分析。
- 用户修改需求时，`mpos-plan-app` 必须先列出失效 artifact 清单并让用户确认；`mpos-gen-app` 的两阶段确认仍然强制。
- 没有实体板卡时，`desktop-preview` 或 `web-preview` 的 `deploy_result.json` 可以满足 publish 前置；有硬件时优先用 `mpk-install` 做真机发布验证。

## 5. 外部站点和索引

本次对话涉及这些外部资料入口：

- `http://docs.micropythonos.com/`：MicroPythonOS 官方 docs 主站。
- `http://docs.micropythonos.com/sitemap.xml`：用于审计 docs 页面覆盖。
- `https://docs.micropythonos.com/search/search_index.json`：用于审计搜索索引覆盖。
- `https://web.micropythonos.com/`：MicroPythonOS 浏览器/WebAssembly 运行入口。
- `https://install.micropythonos.com/`：安装入口。
- `https://upystore.io/`：应用商店/包索引相关入口。
- `https://upystore.io/app_index.json`：应用索引 JSON。

建议维护方式：

- 站点目录和搜索索引的审计结果放在 `mpos-dev/reference/docs-site-index.md`。
- 按主题拆解后的内容放在 `mpos-dev/reference/docs-*.md`。
- `web.micropythonos.com` 的运行方式、限制、部署目标放在 `docs-web-port.md`。
- `upystore.io`、`.mpk`、`app_index.json` 放在 `docs-packaging.md`。
- 需要重新同步外部站点时再抓取，不要把临时 curl 输出混进 skill 文件。

## 6. Docs 拆分状态

当前 docs 已按任务主题拆分到 `mpos-dev/reference/`。这些文件应作为按需加载的 reference，而不是全部塞进 `SKILL.md`。

阅读路由：

- 生成/修改 App：先读 `docs-app-model.md`，再按需读 `docs-frameworks.md`。
- 使用系统服务、manager、通知、下载、音频、传感器：读 `docs-frameworks.md`。
- 打包、商店、manifest、`.mpk`：读 `docs-packaging.md`。
- Linux 桌面、设备安装、固件、QEMU、目标设备：读 `docs-deploy-targets.md`。
- 修改 OS 内核、构建系统、测试、移植：读 `docs-os-development.md`。
- 浏览器运行、WebAssembly、`web.micropythonos.com`：读 `docs-web-port.md`。
- 判断 docs 是否漏页：读 `docs-site-index.md`。

当前重要数字：

- `docs-site-index.md` 记录过 sitemap 约 61 个页面、search index 约 977 条搜索项。
- 这些 reference 是中文说明，代码、JSON、路径和 API 名保持英文。

## 7. API 提取现状

### LVGL API

当前输出：

- `/home/leeqingshui/MicroPython_Skills/mpos-dev/reference/lvgl_api_summary.json`
- `/home/leeqingshui/MicroPython_Skills/mpos-dev/reference/lvgl-api-reference.md`

当前 source：

- `/home/leeqingshui/lvgl_micropython/lvgl.pyi`

当前脚本：

```bash
python3 /home/leeqingshui/MicroPython_Skills/mpos-dev/scripts/extract_lvgl_api.py --lvgl-micropython-dir /home/leeqingshui/lvgl_micropython
```

对话中已经确认：

- LVGL 要提取的是 MicroPython binding API，也就是 mpy API。
- `lvgl.pyi` 是最合适的输入，因为它来自当前 `lvgl_micropython` 的生成结果。
- 当前 JSON 结构包含 `source`、`generated_at`、`generator`、`counts`、`type_aliases`、`enums`、`data_classes`、`widgets`、`functions`、`symbols[]`。
- 当前统计为：60 type aliases、90 enum classes、873 enum members、79 data classes、41 widgets、247 standalone functions、1016 widget methods、1369 data class methods、3715 symbols。
- `*_t = int` 这类 stub 类型别名不再写入 `symbols[]`，只放在 `type_aliases[]`，并尽量提供 `runtime_enum` 映射，例如 `display_render_mode_t -> lv.DISPLAY_RENDER_MODE`、`grad_dir_t -> lv.GRAD_DIR`、`event_code_t -> lv.EVENT`、`fs_whence_t -> lv.FS_SEEK`。AI 生成代码时应使用 `lv.DISPLAY_RENDER_MODE.PARTIAL`、`lv.GRAD_DIR.VER`、`lv.EVENT.CLICKED` 等 runtime enum member。

剩余注意：

- JSON 适合机器检索，MD 适合人类和 Codex 快速扫读；两者都由同一个脚本生成。
- `description` 字段不能靠脚本硬编；只有来自 docstring、注释、官方文档或人工 override 的说明才应写入。

### MicroPythonOS API

当前输出：

- `/home/leeqingshui/MicroPython_Skills/mpos-dev/reference/mpos-api-reference.md`
- `/home/leeqingshui/MicroPython_Skills/mpos-dev/reference/mpos_api_summary.json`

当前脚本：

```bash
python3 /home/leeqingshui/MicroPython_Skills/mpos-dev/scripts/extract_mpos_api.py --mpos-dir /home/leeqingshui/MicroPythonOS
```

当前提取范围：

- Native MicroPython 模块：`MP_REGISTER_MODULE`、module globals、type locals，最终输出只保留用户可 import/call 的 Python 形态。
- Python root export：`internal_filesystem/lib/mpos/__init__.py` 里 `mpos.__all__` 暴露的公共 API。
- Python 全源码 public API：`internal_filesystem/lib/mpos/**/*.py` 中非下划线 public class/function/constant/变量，并给 root export 标记 `availability`/`aliases`。

对话中已经确认：

- 这是 MicroPython 用户可调用 API 索引，不抓私有下划线实现。
- 当前重新生成后，`mpos-api-reference.md` 与 `mpos_api_summary.json` 均为 MPY 接口视角，不包含 native 实现源文件路径或底层签名。
- 当前包含 105 个 Python 文件、106 个 public class、164 个 public function、297 个 public constant/变量。
- 当前 root exports 包含 38 个 `mpos` 类、36 个 `mpos` 函数、1 个变量、11 个导出子模块，`missing` 为 0。
- 当前 native MicroPython modules 包含 5 个模块、3 个 class、23 个 method、8 个 module-level function、4 个 constant。
- `rvswd` 应表现为 `RVSWD` class、方法和常量。
- `webcam` 当前实际 MPY 接口是 module-level functions 加 `Webcam` type，JSON/MD 已按这个结构索引：`webcam.init(...)` 返回 `Webcam` handle，其他 module-level functions 接收该 handle。

剩余注意：

- `description`、`notes`、`examples` 只应从 docstring、注释、官方文档或人工 override 填充；没有来源时保持 `null` 或空数组。

## 8. JSON 与 Markdown 的建议

当前已同时保留两类产物：

- JSON：给脚本、agent 检索、自动校验、精确字段查询使用。
- Markdown：给人类阅读、Codex 快速扫读、任务前人工确认使用。

都放在：

- `/home/leeqingshui/MicroPython_Skills/mpos-dev/reference/`

已补齐文件：

- `reference/mpos_api_summary.json`
- `reference/lvgl-api-reference.md`

当前 JSON 顶层字段：

```json
{
  "source": {},
  "generated_at": "",
  "generator": "",
  "counts": {},
  "symbols": []
}
```

推荐 `symbols[]` 字段：

```json
{
  "kind": "",
  "name": "",
  "fqname": "",
  "module": "",
  "parent": null,
  "signature": "",
  "params": [],
  "returns": null,
  "description": null,
  "description_source": null,
  "notes": [],
  "examples": [],
  "source_path": "",
  "source_line": null,
  "availability": null,
  "aliases": [],
  "deprecated": false
}
```

字段说明：

- `source`：输入来源，例如 `lvgl.pyi`、`internal_filesystem/lib/mpos/__init__.py`；native 模块的实现源文件不写入用户侧 reference。
- `generated_at`：生成时间，便于判断是否过期。
- `generator`：生成脚本名和版本信息。
- `counts`：按模块、类、函数、枚举、方法统计。
- `kind`：`module`、`class`、`method`、`function`、`enum`、`constant`、`data_class`、`widget` 等。
- `fqname`：完整名称，例如 `lv.button.set_text` 或 `mpos.AppManager`。
- `signature`、`params`、`returns`：从 stub、AST 或人工维护的 native MPY 签名表中能可靠提取时再填。
- `description`：API 说明。不要编造；没有来源就填 `null`。
- `description_source`：`docstring`、`comment`、`official_docs`、`manual_override`、`stub` 等。
- `notes`：绑定差异、坑点、AGENTS 规则、兼容性提醒。
- `examples`：短示例；优先来自官方 docs 或人工维护，不要自动生成误导性示例。
- `source_path`、`source_line`：Python/stub API 可定位时填写；native 模块符号保持 `null`，避免把实现细节混入用户侧 API reference。

## 9. `AGENTS.md` 基础规则

从 `/home/leeqingshui/MicroPythonOS/AGENTS.md` 合并到 skill 的关键规则：

- 优先使用根目录 `Makefile` 目标：`make build-mpos-unix`、`make syntax-tests`、`make unittest-tests`、`make tests`、`make lint`、`make lint-fix`。
- MicroPythonOS 代码改动后必须通过 `make lint`。
- 运行桌面端时用 `timeout -s 9 30 ./scripts/run_desktop.sh`。
- 临时调试脚本写到仓库根目录 `tmp/`，不要写 `/tmp`。
- 杀进程用 `killall <name>`，不要用 `pkill -f <pattern>`。
- Python 格式遵循 `ruff.toml`，当前 quote style 是 double quotes。
- App 安装到设备后，需要 `AppManager.refresh_apps()` 后再 `start_app()`。
- `self.appFullName` 由 `ActivityNavigator` 自动设置，App 内持久化等场景优先用它，不要硬编码包名。
- `Soft reset` 在当前 `lvgl_micropython` / MicroPythonOS 组合里不可靠，使用 `machine.reset()`。

LVGL 重点规则：

- `import lvgl as lv`。
- 使用 `lv.screen_active()`，不是 `lv.scr_act()`。
- 不硬编码分辨率，使用 `lv.pct(100)` 等自适应方式。
- 使用 `button`、`image`，不要沿用旧名 `btn`、`img`。
- `lv.EVENT.VALUE_CHANGED`，不是 `lv.EVENT_VALUE_CHANGED`。
- `lv.obj.FLAG.CLICKABLE`，不是 `lv.OBJ_FLAG.CLICKABLE`。
- 隐藏/显示用 `.add_flag(lv.obj.FLAG.HIDDEN)` / `.remove_flag(lv.obj.FLAG.HIDDEN)`。
- 新 label 必须显式 `label.set_text("")`，否则默认显示 `"Text"`。
- `style_obj = lv.style_t()` 后必须 `style_obj.init()` 再调用 setter。
- LVGL 9 style setter 只传 value，selector 放在 `obj.add_style(style, selector)`。
- 事件回调需要 event 参数，方法同时作为回调和普通方法时用 `event=None`。
- 回调中优先用 `event.get_target_obj()`。
- LVGL object wrapper 不支持任意 Python 属性赋值，关联数据用闭包/lambda 或平行列表。

## 10. Codex/审批相关记录

本次对话也涉及 Codex 审批模式。这个内容属于运行时安全配置，不建议写进某个 MicroPythonOS skill 的默认流程。

维护建议：

- skill 文档里不要默认要求“跳过所有审批”或“关闭 sandbox”。
- 需要联网、写非工作区、运行可能危险命令时，应按当前 Codex 会话的审批机制单独确认。
- 如果后续专门整理 Codex 使用说明，应放到单独的 Codex 工具说明文件，不和 `mpos-dev` 开发规则混在一起。

## 11. 后续待办

- 为常用 API 增加人工维护的 `description`、`notes`、`examples`，并标注 `description_source: "manual_override"`。
- 如果给 `webcam` 补人工示例，继续按实际 MPY 接口结构处理：module-level functions 加 `Webcam` type，示例要避免写成不存在的方法。
- 重新同步外部 docs 时，优先更新 `docs-site-index.md`，再更新对应专题 reference。
- 维护 `mpos-*` skill 时继续遵守 progressive disclosure：`SKILL.md` 只保留阶段流程和资源路由，细节放 `reference/`，确定性动作放 `scripts/`，不要复制粘贴整份资料。
