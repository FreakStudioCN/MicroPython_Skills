---
name: mpos-analyze-app
description: Analyze MicroPythonOS App ideas directly or when invoked by mpos-plan-app. Use to turn natural-language MPOS App requests into requirements, default app identity, manifest draft, Activity/Service plan, MPOS/LVGL API plan, dependency risk, test/deploy plan, mandatory MicroPythonOS resource links, and a JSON handoff before code generation.
---

# MicroPythonOS App 需求分析

## 角色

把用户的一句或多句 MicroPythonOS App 想法分析成可交给下游 skill 的稳定状态。支持两种入口：

- 用户直接要求分析、规划、确认一个 MPOS App。
- `mpos-plan-app` 调用本 skill 作为对话式流水线的 analyze 阶段。

本 skill 只做分析和交接，不写代码、不下载驱动、不打包、不安装 App、不烧录固件、不上传 upystore。

## 用户可见语言

遵守 `mpos-dev` 的语言连续性规则：当前 workflow 从中文开始，分析、问题和总结继续用中文；从英文开始则继续用英文。代码、命令、路径、API 名和 JSON 字段名保持英文。

## 统一项目日志

完成分析并产出 `analysis_result.json` 后，必须登记到项目状态目录：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill mpos-analyze-app \
  --phase analyze \
  --result <success|partial|failed> \
  --artifact analysis_result=<analysis_result.json> \
  --next-skill <handoff.next_skill-or-null> \
  --event "Analyzed requirements and produced analysis_result.json"
```

如果 `fullname` 只是建议值，也要用该建议值建立 `tmp/mpos-plan-app/<fullname>/plan_state.json`，便于后续确认或改名时追踪。

## 必读上下文

先加载 `mpos-dev`。分析时按需读取：

- App/Activity/Service/Intent：`mpos-dev/reference/docs-app-model.md`
- 系统 manager、持久化、网络、音频、相机、传感器、后台任务：`mpos-dev/reference/docs-frameworks.md`
- 全部硬件能力合同和生成边界：`mpos-dev/reference/docs-hardware-capabilities.md`
- 跨设备相机 App 和能力探测：`mpos-dev/reference/docs-camera-apps.md`
- MPOS API 精确索引：`mpos-dev/reference/mpos_api_summary.json`
- LVGL API 精确索引：`mpos-dev/reference/lvgl_api_summary.json`
- 目标设备、OS 安装、桌面仿真、Web 运行：`mpos-dev/reference/docs-deploy-targets.md`
- 浏览器仿真细节：`mpos-dev/reference/docs-web-port.md`
- MPK、AppStore、upystore：`mpos-dev/reference/docs-packaging.md`

API 判断优先用 JSON。LVGL `type_aliases[]` 只解释签名类型，不是可生成的 runtime API。
`mpos_api_summary.json` 和 `lvgl_api_summary.json` 必须完整读取并用于判断；不能因为需求简单、UI 简单或只做修复而省略。

## 固定资源入口

每次用户可见输出都必须展示这些入口；JSON 的 `resource_links[]` 也必须包含它们：

- 官方文档：`https://docs.micropythonos.com/`
- UpyStore：`https://upystore.io/`
- 安装 MicroPythonOS：`https://install.micropythonos.com/`
- 浏览器仿真：`https://web.micropythonos.com/`

这些链接是固定入口，不是前置阻塞条件。只有当用户要真机运行、设备状态不明、或明确没装 OS 时，才把“是否已经安装 MicroPythonOS”列为问题；未安装时推荐 installer。`web.micropythonos.com` 可用于快速浏览器仿真/烟测，但不能替代 Linux SDL 桌面仿真或真实硬件验证。

## 工作流

1. 读取用户需求和已有上下文，保留用户明确指定的 App 名、功能、硬件能力和发布意图。默认不要求选择板卡；把硬件需求记录为 `required_capabilities`，只在真机部署或板级故障诊断时询问设备信息。
2. 生成默认 App 身份。缺少 `fullname` 时按功能名建议 `com.micropythonos.<slug>`；缺少 `name`、`category`、`version`、`publisher` 时给合理默认值，不因此阻塞。`publisher` 默认从 `fullname` 组织前缀派生，例如 `com.example.calc` -> `com.example`。
3. 拆分功能边界：MVP、后续功能、非目标、风险点。
4. 判断 App 结构：需要哪些 Activity，是否需要 Service，是否需要 `boot_completed`、Intent、持久化、后台任务。
5. 判断内置 API 是否足够：优先使用 MPOS managers/frameworks 和 LVGL MicroPython API；相机等已由 MPOS manager 抽象的能力不得误判为 App 外部驱动。只标记真正的 App 依赖，不在本阶段搜索或生成板级驱动实现。
   - 将板载需求写入 `required_capabilities[]`，逐项标记 `portable_api`、运行时 probe、fallback 和真机验证要求。
   - `portable_api=false` 时返回 `MPOS_CAPABILITY_API_MISSING`，不能通过指定板卡、导入 `mpos.board.*` 或下载驱动继续生成。
   - 只有用户明确提出外接模块时才写入 `required_accessories[]`，并记录协议、接线待确认项和资源冲突风险。
6. 产出测试计划：语法、manifest、API 交叉校验、App-only 变更检查、普通 unittest、GraphicalTestCase、Linux SDL 桌面仿真、可选 Web smoke、设备硬件验证。
7. 产出部署/运行计划：桌面优先；Web 可预览；真机前确认设备、串口和 MicroPythonOS 是否已安装；安装 App 与烧录固件分开。
8. 只问阻塞问题。分析阶段可以用默认值继续；只有马上进入代码生成且缺少必要身份、硬件或目标限制时才阻塞。
9. 输出 Markdown 摘要和强制 JSON。JSON 应匹配 `templates/analysis_result.json`，并可用 `scripts/validate_analysis_json.py` 校验。

## 输出要求

用户可见部分按这个顺序：

1. `MicroPythonOS 入口`：列出四个固定链接。
2. `分析摘要`：一句话说明 App 目标和默认身份。
3. `功能与边界`：MVP、后续、非目标。
4. `实现计划`：Activity/Service、framework/LVGL/API、依赖判断。
5. `测试与运行`：测试计划、桌面/Web/设备路径。
6. `需要确认`：只列真正阻塞的问题；没有则写“无阻塞问题”。
7. `JSON`： fenced `json` 代码块，必须包含完整分析对象。

## JSON 契约

使用 `templates/analysis_result.json` 作为字段模板。关键要求：

- `schema_version` 固定为 `"mpos-analyze-v1"`。
- `phase` 固定为 `"analyze"`。
- `result` 使用 `"success"`、`"partial"` 或 `"failed"`。
- `resource_links[]` 必须包含四个固定 URL。
- `app.fullname` 可为建议值；不知道时仍给可用默认，不因缺用户确认而为空。
- `app.publisher` 和 `manifest_draft.publisher` 必须是非空字符串；默认从 `fullname` 组织前缀派生。
- `manifest_draft.activities[]` 和 `services[]` 使用完整对象：`classname`、`entrypoint`、`intent_filters`。
- `entrypoint` 必须带 `.py`，建议使用 `assets/main.py` 或 `assets/service.py`。
- `app_structure.manifest` 新 App 默认使用根目录 `MANIFEST.JSON`。
- `app_structure.icon` 新 App 默认使用根目录 `icon_64x64.png`。
- 旧 `META-INF/MANIFEST.JSON` 和 `res/mipmap-mdpi/icon_64x64.png` 仅在分析现有 legacy App 时作为兼容路径。
- `dependency_plan.builtin_api_sufficient` 和 `external_driver_required` 是本阶段的核心判断。
- `blocking_questions[]` 只放阻塞下游的问题。
- `handoff.next_skill` 推荐值为 `mpos-gen-app`、`mpos-prepare-deps`、`mpos-test-app`、`mpos-package-app`、`mpos-deploy-app`、`mpos-publish-app` 或 `mpos-plan-app`。

校验命令：

```bash
python3 /home/leeqingshui/MicroPython_Skills/mpos-analyze-app/scripts/validate_analysis_json.py \
  /home/leeqingshui/MicroPython_Skills/mpos-analyze-app/templates/analysis_result.json
```

## 下游路由

- 内置 API 足够、需求清楚：`handoff.next_skill = "mpos-gen-app"`。
- 需要外部 Python 驱动、器件资料、依赖整理：`mpos-prepare-deps`。
- 用户只要验证现有 App：`mpos-test-app`。
- 用户说运行、仿真、真机安装、烧录：`mpos-deploy-app`，并明确 App 安装不是固件烧录。
- 用户说 MPK、AppStore、upystore、发布：`mpos-package-app` 或 `mpos-publish-app`。
- 需要完整从需求到发布的多阶段编排：交回 `mpos-plan-app`。

## 边界

- 不生成或修改 `internal_filesystem/apps/<fullname>/`。
- 不调用驱动下载、datasheet 提取、冷门驱动生成。
- 不把 upystore seed 数据中的字符串型 `activities` 当作新 manifest 格式。
- 不要求用户先阅读 docs 或先安装 OS 才能完成分析。
- 不把 `web.micropythonos.com` 描述成 installer 或发布站点。
- 不把 `install.micropythonos.com` 描述成 App 安装工具；它是 OS/固件安装入口。
