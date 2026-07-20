# MicroPythonOS 打包与 Store 参考

本文件基于 2026-07-14 重新读取的 `docs.micropythonos.com` sitemap/search index、`https://upystore.io/`、`https://upystore.io/app_index.json`、`https://upystore.io/api/v1/apps` 生成，并结合本地 `scripts/bundle_apps.sh`、`tests/test_apps_manifest.py`、`tests/test_streaming_unzip.py`、`internal_filesystem/lib/mpos/content/streaming_unzip.py` 修正。

## 什么时候读取

创建 `.mpk`、校验 app manifest、生成 app index 元数据、准备 AppStore/upystore/BadgeHub 发布、排查安装失败时读取本文件。

## 来源覆盖

- `apps/bundling-apps/`
- `apps/appstore/`
- `apps/badgehub/`
- 本地 `scripts/bundle_apps.sh`
- 本地 MPK 测试和 `StreamingUnzip`

## MPK 契约

`.mpk` 是 ZIP archive，并且有严格的 stream-order 约束：

- 第一个 ZIP local header 必须是名为 `<fullname>/` 的目录 entry。
- `<fullname>/` 必须与 app manifest 中的 `fullname` 一致。
- 只能有一个顶层目录。
- 所有文件都必须位于该顶层目录下。
- 支持的压缩方式是 stored 和 deflated。
- 不支持 data descriptor flag；local file header 必须包含准确大小。

合法的 stream order：

```text
com.example.app/
com.example.app/MANIFEST.JSON
com.example.app/assets/main.py
com.example.app/icon_64x64.png
```

旧嵌套布局 `META-INF/MANIFEST.JSON` 和 `res/mipmap-mdpi/icon_64x64.png` 仍可被当前安装路径兼容，但新 package 应优先使用根目录 `MANIFEST.JSON` 和 `icon_64x64.png`。

格式错误的 archive 会在 streaming extraction 过程中被拒绝，可能在写入文件前或写入过程中失败。

## 本地 Manifest 校验

打包前校验：

- 目录名等于 manifest `fullname`。
- manifest JSON 能解析。
- `name`、`publisher` 和 `version` 存在且非空。
- `version` 是规范的整数点号字符串。
- 每个 activity/service entrypoint 都以 `.py` 结尾。
- 每个 entrypoint 都存在于 app 根目录的相对路径下。
- 每个声明的 classname 都出现在 entrypoint 源码中。

这些规则对应 `tests/test_apps_manifest.py`。

## 可重复打包

本地批量打包脚本是 `scripts/bundle_apps.sh`，从 `internal_filesystem/apps` 生成 package。

单 App 打包也应遵循同样原则：

- zip 前切到 app repository 的父目录，确保路径包含 `<fullname>/`。
- 目录 entry 放在文件 entry 前。
- entry 排序稳定。
- 使用固定 timestamp，便于可重复构建。
- 排除 `.git/`、`__pycache__/`、`*.pyc`、`__MACOSX/`、`._*`。
- 确保 icon 存在于根目录 `icon_64x64.png`；旧 `res/mipmap-mdpi/icon_64x64.png` 只作为兼容路径。

建议的单 App 脚本：

- `mpos-package-app/scripts/validate_mpos_app.py`
- `scripts/package_mpos_app.py`
- `scripts/validate_mpk.py`
- `scripts/emit_app_index_entry.py`

## App Index 元数据

兼容 MicroPythonOS 的 app index 应包含：

- `name`
- `publisher`
- `short_description`
- `long_description`
- `icon_url`
- `download_url`
- `fullname`
- `version`
- `category`
- `activities`
- `services`（如果存在）

Activity 元数据优先使用带 `classname`、`entrypoint`、`intent_filters` 的完整 manifest object。不要给新生成的 package 输出字符串型 activity 列表。
upystore 上传同样要求 manifest 中存在非空 `publisher`；本地打包阶段必须提前拦截，不能把缺字段的 `.mpk` 交给用户上传。

## AppStore Backend

AppStore 可以从多个 backend 拉取应用。

- MicroPythonOS curated app index：人工 review 的 app 元数据和 `.mpk` 下载 URL。
- BadgeHub：社区 appstore，包含 project summary、project detail endpoint、release、icon 和下载包。
- upystore：面向开发者的外部 store；本地准备 package 和 metadata，然后让用户手动上传。

`slug`、`revision`、`tags`、`hardware_tags`、`screenshots`、安装量、下载量、star、发布时间等 storefront 字段适合发布摘要，但不能替代本地 `MANIFEST.JSON`。

## upystore 专项建议

从 skill 角度看，`https://upystore.io/` 上传流程应保持简单：生成并校验 package，然后给用户网站或 Developer Console 链接。不要请求或保存账号密码。

2026-07-14 复核结果：

- `https://upystore.io/app_index.json` 当前是 10 个 app 的 list，字段包括 `activities`、`category`、`download_url`、`fullname`、`icon_url`、`long_description`、`name`、`publisher`、`short_description`、`version`。
- `https://upystore.io/api/v1/apps` 当前返回 `apps`、`filters`、`pagination`，分页显示 `total=10`、`total_pages=1`，并额外包含 `slug`、`revision`、`tags`、`hardware_tags`、`min_os_version`、`min_api_level`、`screenshots`、`installs_count`、`downloads_count`、`stars_count`、`released_at` 等 storefront 字段。
- 按 `api/v1/apps` 的 10 个 `slug` 逐个读取公开 app detail 页面，结果为 `UPYSTORE_DETAIL_OK=10/10`。这些 detail 页面可用于上传后人工核对，但不能替代本地 manifest 和 MPK 校验。

上传后检查：

- 如果用户提供 URL，抓取上传后的 app index 或 API detail。
- 校验必需字段齐全。
- 下载生成的 `.mpk`。
- 校验第一个 ZIP entry 是 `<fullname>/`。
- 确认没有 macOS resource fork 文件。
- 可选：走设备或桌面端安装验证。

## BadgeHub 专项建议

BadgeHub 发布是独立于 upystore 的路径。它使用 BadgeHub metadata 和 release。目标是 BadgeHub 时，检查 project slug、release version、`.mpk` artifact、icon 和 project description。

## 来自 AGENTS 的本地规则

- 修改代码或脚本后运行 `make lint`。
- 有等价入口时优先使用现有 `Makefile` target。
- 临时文件写到 repository `tmp/`。
- 不要削弱 `StreamingUnzip` 校验来接受格式错误的 package。
- 不要把安装 App 和烧录固件混为一谈。
