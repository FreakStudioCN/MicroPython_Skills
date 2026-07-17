# MicroPythonOS Docs 站点索引

本文件基于 2026-07-14 重新读取的 `https://docs.micropythonos.com/sitemap.xml` 和 `search/search_index.json` 生成。

用途：审计 docs 覆盖范围。本轮按 sitemap 逐页读取了全部 61 个页面，结果为 `DOCS_FETCH_OK=61/61 failed=0`；docs 搜索索引包含 977 个页面/小节条目。具体工作规则拆分在下面这些专题 reference 文件中。

## Reference 路由

- `docs-app-model.md`：App 模型、Activity、Service、Intent、内置 App、native app。
- `docs-packaging.md`：MPK、app index 元数据、AppStore、BadgeHub、upystore 打包检查。
- `docs-frameworks.md`：framework 架构和 manager/service API。
- `docs-deploy-targets.md`：运行目标、桌面端、设备安装、固件烧录、QEMU、WebSerial、浏览器预览。
- `docs-os-development.md`：编译、测试、移植、release/merge checklist、文件格式。
- `docs-web-port.md`：WebAssembly/browser runtime 和 web build target。

## Sitemap 覆盖映射

| Docs page | Reference |
|---|---|
| `/` | `docs-app-model.md`, `docs-deploy-targets.md` |
| `/overview/` | `docs-app-model.md`, `docs-deploy-targets.md` |
| `/apps/` | `docs-app-model.md` |
| `/apps/app-lifecycle/` | `docs-app-model.md` |
| `/apps/appstore/` | `docs-app-model.md`, `docs-packaging.md` |
| `/apps/badgehub/` | `docs-packaging.md` |
| `/apps/built-in-apps/` | `docs-app-model.md` |
| `/apps/bundling-apps/` | `docs-packaging.md` |
| `/apps/creating-apps/` | `docs-app-model.md` |
| `/apps/native-apps/` | `docs-app-model.md`, `docs-os-development.md` |
| `/architecture/boot-sequence/` | `docs-os-development.md` |
| `/architecture/filesystem/` | `docs-app-model.md`, `docs-os-development.md` |
| `/architecture/frameworks/` | `docs-frameworks.md` |
| `/architecture/intents/` | `docs-app-model.md` |
| `/architecture/overview/` | `docs-app-model.md`, `docs-os-development.md` |
| `/frameworks/` | `docs-frameworks.md` |
| `/frameworks/app-manager/` | `docs-frameworks.md` |
| `/frameworks/appearance-manager/` | `docs-frameworks.md` |
| `/frameworks/audiomanager/` | `docs-frameworks.md` |
| `/frameworks/battery-manager/` | `docs-frameworks.md` |
| `/frameworks/build-info/` | `docs-frameworks.md` |
| `/frameworks/connectivity-manager/` | `docs-frameworks.md` |
| `/frameworks/device-info/` | `docs-frameworks.md` |
| `/frameworks/display-metrics/` | `docs-frameworks.md` |
| `/frameworks/download-manager/` | `docs-frameworks.md` |
| `/frameworks/file-explorer-activity/` | `docs-frameworks.md` |
| `/frameworks/focus/` | `docs-frameworks.md` |
| `/frameworks/font-manager/` | `docs-frameworks.md` |
| `/frameworks/input-activity/` | `docs-frameworks.md` |
| `/frameworks/input-manager/` | `docs-frameworks.md` |
| `/frameworks/lights-manager/` | `docs-frameworks.md` |
| `/frameworks/notification-manager/` | `docs-frameworks.md` |
| `/frameworks/number-format/` | `docs-frameworks.md` |
| `/frameworks/preferences/` | `docs-frameworks.md` |
| `/frameworks/sensor-manager/` | `docs-frameworks.md` |
| `/frameworks/service/` | `docs-frameworks.md`, `docs-app-model.md` |
| `/frameworks/setting-activity/` | `docs-frameworks.md` |
| `/frameworks/settings-activity/` | `docs-frameworks.md` |
| `/frameworks/task-manager/` | `docs-frameworks.md` |
| `/frameworks/time-zone/` | `docs-frameworks.md` |
| `/frameworks/webserver/` | `docs-frameworks.md` |
| `/frameworks/widget-animator/` | `docs-frameworks.md` |
| `/frameworks/wifi-service/` | `docs-frameworks.md` |
| `/getting-started/` | `docs-deploy-targets.md` |
| `/getting-started/running/` | `docs-deploy-targets.md` |
| `/getting-started/supported-hardware/` | `docs-deploy-targets.md` |
| `/os-development/` | `docs-os-development.md` |
| `/os-development/automated-testing/` | `docs-os-development.md` |
| `/os-development/compiling/` | `docs-os-development.md` |
| `/os-development/emulating-esp32-on-desktop/` | `docs-deploy-targets.md`, `docs-os-development.md` |
| `/os-development/installing-on-esp32/` | `docs-deploy-targets.md`, `docs-os-development.md` |
| `/os-development/linux/` | `docs-deploy-targets.md`, `docs-os-development.md` |
| `/os-development/macos/` | `docs-deploy-targets.md`, `docs-os-development.md` |
| `/os-development/porting-guide/` | `docs-os-development.md` |
| `/os-development/running-on-desktop/` | `docs-deploy-targets.md` |
| `/os-development/windows/` | `docs-deploy-targets.md`, `docs-os-development.md` |
| `/other/merge-checklist/` | `docs-os-development.md` |
| `/other/release-checklist/` | `docs-os-development.md` |
| `/other/supported-file-formats/` | `docs-os-development.md` |
| `/web-port/developer/` | `docs-web-port.md`, `docs-os-development.md` |
| `/web-port/using/` | `docs-web-port.md`, `docs-deploy-targets.md` |

## 说明

- 这不是 docs 站点的逐字镜像，而是拆分后 reference 文件的覆盖表和路由表。
- 各专题 reference 会转述 docs 内容，并在公共文档与本地仓库不一致时加入本地 `AGENTS.md` 约束。
- 如果任务需要精确 API 签名，除专题 docs reference 外，还要读取 `mpos-api-reference.md` 和 `lvgl_api_summary.json`。
