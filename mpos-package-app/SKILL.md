---
name: mpos-package-app
description: Package and validate a single MicroPythonOS App as an MPK release artifact. Use when Codex needs to create a .mpk, validate an MPOS App manifest/icon/package structure, emit one app_index_entry.json fragment, run optional temporary install validation, or prepare AppStore/upystore publishing artifacts without uploading.
---

# MicroPythonOS App 打包

## 角色

把一个已经存在的 MicroPythonOS App 目录打包成可安装、可发布的 `.mpk` 产物。只处理单个 App 的发布产物准备，不生成或修复 App 代码，不下载依赖，不运行桌面模拟器，不登录或上传 upystore。

优先在 `mpos-gen-app` 静态门禁完成、`mpos-test-app` runtime smoke 完成后使用本 skill。若测试结果缺失或失败，仍允许继续打包，但必须在 `package_result.json` 中记录 warning。

## 统一项目日志

完成打包并产出 `package_result.json` 后，必须登记到项目状态目录：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill mpos-package-app \
  --phase package \
  --result <success|partial|failed> \
  --artifact package_result=<package_result.json> \
  --next-skill <handoff.next_skill-or-null> \
  --event "Packaged App as MPK and app_index_entry"
```

缺失或失败的 generation/test 结果仍可让打包继续并标 warning，但项目状态要保留这些 warning，便于 `mpos-plan-app` 决定是否能继续到 deploy/publish。

## 必读上下文

先加载 `mpos-dev`，并读取：

- 打包、manifest、MPK、AppStore/upystore 约束：`mpos-dev/reference/docs-packaging.md`
- 本地强约束：`<repo-root>/AGENTS.md`
- 当前 manifest 测试事实：`<repo-root>/tests/test_apps_manifest.py`
- 当前 MPK/streaming install 事实：`<repo-root>/tests/test_streaming_unzip.py`
- 当前 installer 事实：`<repo-root>/internal_filesystem/lib/mpos/content/streaming_unzip.py`

当旧分析文档或 docs 与当前仓库冲突时，优先当前仓库和测试。

## 边界

- 不修改 `internal_filesystem/apps/<fullname>/` 的业务代码、manifest 或 icon。
- 不修复 lint、flake8、pylint、manifest、syntax、import 错误；这些回到 `mpos-gen-app repair`。
- 不下载第三方依赖；依赖准备回到 `mpos-prepare-deps`。
- 不跑 desktop simulator、Web Port 或设备交互；运行测试回到 `mpos-test-app`。
- 不安装到真实 `/apps`，不覆盖真实 `internal_filesystem/apps`。
- 不登录、不上传、不保存 upystore 凭据；发布上传归用户或未来 `mpos-publish-app`。
- 不修改 MicroPythonOS OS/build 源码。

## App 布局策略

默认新布局：

```text
internal_filesystem/apps/<fullname>/
  MANIFEST.JSON
  icon_64x64.png
  assets/<entrypoint>.py
```

兼容旧布局，但必须 warning：

```text
internal_filesystem/apps/<fullname>/
  META-INF/MANIFEST.JSON
  res/mipmap-mdpi/icon_64x64.png
  assets/<entrypoint>.py
```

如果根目录 `MANIFEST.JSON` 和旧 `META-INF/MANIFEST.JSON` 同时存在，优先根目录 manifest，并记录旧路径共存 warning。icon 同理优先根目录 `icon_64x64.png`。

## 工作流

1. 确定 `fullname` 和 App 目录，默认 `<repo-root>/internal_filesystem/apps/<fullname>`。
2. 读取可选 `generation_result.json` 和 `app_test_result.json`。缺失或失败只产生 warning，不阻塞打包。
   - 缺失、路径不存在、JSON 无法解析、schema/phase 不匹配、`result != "success"` 都按 warning 处理。
   - 上游 generation/test warning 必须同步输出到终端和 `package_result.json`。
   - 只要 App 目录、manifest、icon、entrypoint、MPK 结构校验还能通过，就继续生成 `.mpk` 和 `app_index_entry.json`。
3. 运行 App 校验：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-package-app/scripts/validate_mpos_app.py \
  --repo <repo-root> \
  --app-fullname <fullname>
```

4. 生成 MPK、`app_index_entry.json` 和 `package_result.json`：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-package-app/scripts/package_mpos_app.py \
  --repo <repo-root> \
  --app-fullname <fullname> \
  --compression stored
```

默认输出目录：

```text
<repo-root>/tmp/mpos-package-app/<fullname>/
```

5. 用户要求临时安装验证时加 `--install-check`。该检查只解包到 `tmp/mpos-package-app/<fullname>/install-check/` 并重新校验解包后的 App，不写真实 App 目录：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-package-app/scripts/package_mpos_app.py \
  --repo <repo-root> \
  --app-fullname <fullname> \
  --compression stored \
  --install-check
```

6. 复核结果：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-package-app/scripts/validate_package_result.py \
  <repo-root>/tmp/mpos-package-app/<fullname>/package_result.json
```

## MPK 规则

必须由脚本保证：

- `.mpk` 是 ZIP archive。
- 第一条 local file header 必须是 `<fullname>/` 目录 entry。
- 只能有一个 top-level directory。
- 所有 entry 必须在 `<fullname>/` 下。
- 默认压缩方式是 `stored`。可以显式 `--compression deflated`，但仍必须通过 local-header 校验。
- 不允许 data descriptor flag；local header 必须包含准确 size。
- 排除 `.git/`、`__pycache__/`、`*.pyc`、`__MACOSX/`、`._*`、`.DS_Store`。
- 使用固定 timestamp 和稳定排序，便于可重复构建。

## App Index

本 skill 默认只生成当前 App 的 `app_index_entry.json`，不合并或修改完整 `app_index.json`。完整 store index 合并涉及发布仓库、URL 策略、排序、冲突处理和上线流程，不是本 skill 默认职责。

`emit_app_index_entry.py` 会基于 manifest 生成单条 metadata，并按 base URL 生成：

```text
<base_url>/apps/<fullname>/icons/<fullname>_<version>_64x64.png
<base_url>/apps/<fullname>/mpks/<fullname>_<version>.mpk
```

默认 base URL 是 `https://apps.micropythonos.com`。如果目标是 upystore 上传，仍只准备本地 metadata 和 MPK，不上传。

## 输出 JSON

`package_result.json` 必须匹配 `templates/package_result.json` 的形状，并通过 `scripts/validate_package_result.py`：

- `schema_version` 为 `mpos-package-app-v1`。
- `phase` 为 `package`。
- `result` 为 `success`、`partial` 或 `failed`。
- `checks[]` 至少包含 `app_validation`、`generation_result`、`app_test_result`、`mpk_validation`、`app_index_entry`。
- 请求 `--install-check` 时追加 `temporary_install_validation`。
- 缺失/失败的 generation/test 结果只记 warning，不能让 package 失败。
- `handoff.next_skill` 通常为 `mpos-publish-app` 或 `null`。

## 失败处理

- App manifest、entrypoint、classname、icon 缺失：停止打包，交回 `mpos-gen-app repair`。
- MPK local-header、top dir、data descriptor、非法文件失败：修本 skill 脚本或重新打包，不让 `mpos-gen-app` 改业务代码。
- 临时安装验证失败：如果 MPK 结构问题，留在本 skill；如果解包后 manifest/App 文件缺失，交回 `mpos-gen-app repair`。
- generation/test 缺失或失败：继续输出 MPK，但 `result` 为 `partial` 并记录 warning。
