# 自然语言生成 MicroPythonOS App 项目前后端交接说明

本文档面向参与“浏览器端 AI 自然语言生成、仿真、打包、部署 MicroPythonOS App”的前端/后端工程师。目标是让对方从零理解项目背景、基础环境、VMware + Ubuntu 24.04 开发环境、浏览器产品形态、后端编排接口，以及和 skill 改造工作的边界。

本文不是 skill 内部实现文档。skill 改造由 skill 负责人维护；前后端需要稳定依赖的是协议、状态、制品、权限和错误返回。

## 1. 项目一句话介绍

用户在浏览器里用自然语言描述一个 MicroPythonOS App，例如“做一个极简四则运算计算器”，系统自动完成：

1. 需求分析
2. MicroPythonOS / LVGL API 校验
3. App 源码生成
4. 桌面或 Web 预览
5. 打包为 `.mpk`
6. 可选部署到真实 ESP32/ESP32-S3 硬件
7. 生成发布前检查结果和上传指导

最终产物不是普通 Web App，而是运行在 MicroPythonOS 上的 MicroPython + LVGL App。

## 2. MicroPythonOS 基础概念

MicroPythonOS 是一个基于 MicroPython 的轻量 OS，主要运行在 ESP32/ESP32-S3 等微控制器，也支持 Linux/macOS 桌面运行和 WebAssembly 浏览器运行。

核心概念：

- App 写在 `internal_filesystem/apps/<fullname>/` 或项目生成目录中。
- 每个 App 必须有 `MANIFEST.JSON`。
- App 的 Python 入口通常在 `assets/main.py`。
- UI 使用 `lvgl` MicroPython 绑定。
- App 打包产物是 `.mpk`。
- 发布用 release 编号命名，例如 `com.example.demo_r1.mpk`、`com.example.demo_r2.mpk`。
- `MANIFEST.JSON` 中 `publisher` 是必填字段。

重要本地路径：

- MicroPythonOS 源码：`/home/leeqingshui/MicroPythonOS`
- skill 源仓库：`/home/leeqingshui/MicroPython_Skills`
- Claude Code skills 安装目录：`/home/leeqingshui/.claude/skills`
- 英文翻译仓库：`/home/leeqingshui/MicroPython_Skills_EN`
- 建议本地测试目录：`/home/leeqingshui/tmp/mpos-skill-cc-test-20260717`

外部入口：

- MicroPythonOS 官网：https://micropythonos.com/
- MicroPythonOS 文档：https://docs.micropythonos.com/
- MicroPythonOS 在线安装器：https://install.micropythonos.com/
- MicroPythonOS Web 运行说明：https://docs.micropythonos.com/web-port/using/
- MicroPythonOS App 文档：https://docs.micropythonos.com/apps/
- MicroPythonOS 文件系统布局：https://docs.micropythonos.com/architecture/filesystem/
- MicroPythonOS 桌面运行说明：https://docs.micropythonos.com/os-development/running-on-desktop/
- uPyStore 首页：https://upystore.io/
- uPyStore 开发者入口：https://upystore.io/developer

## 3. 当前 skill 改造边界

skill 负责人不覆盖现有 `mpos-*` classic skill，而是新增一套后缀为 `-web` 的浏览器/后端 runner 版本。classic skill 继续服务 Claude Code 中 `/skill-name 描述` 的本地调用；`mpos-*-web` 服务浏览器项目的 JSON 协议编排。

classic skill 保留：

- `mpos-dev`
- `mpos-plan-app`
- `mpos-analyze-app`
- `mpos-prepare-deps`
- `mpos-gen-app`
- `mpos-test-app`
- `mpos-package-app`
- `mpos-deploy-app`
- `mpos-publish-app`

新增浏览器 skill：

- `mpos-dev-web`：协议、状态机、错误码、artifact manifest、权限、能力、板卡/Web 限制。
- `mpos-plan-app-web`：创建/恢复/重试/取消 session 并路由阶段。
- `mpos-analyze-app-web`：输出结构化 `analysis_result.json`。
- `mpos-prepare-deps-web`：输出 `dependency_handoff.json`。
- `mpos-gen-app-web`：输出 `generation_result.json` 和 file operations。
- `mpos-test-app-web`：输出 `app_test_result.json`、截图和 preview 记录。
- `mpos-package-app-web`：输出 `package_result.json`、`app_index_entry.json` 和 `_rN.mpk`。
- `mpos-deploy-app-web`：输出 `deploy_result.json`，处理权限和设备/preview 记录。
- `mpos-publish-app-web`：输出 `publish_result.json` 和手工上传指导。

`mpos-debug-app` 当前已不需要，也不新增 `mpos-debug-app-web`。

所有 mpos skill 必须强调：

- 必须完整阅读 API 相关列表，不能因为任务简单省略。
- 生成代码前必须对 `lv.X`、`lv.Y.Z` 调用做 `lvgl_api_summary.json` 交叉校验。
- 不能修改 MicroPythonOS 中 App 目录外的任何代码。
- 不能修改 `mpos` OS 框架、`lvgl_micropython`、构建脚本、系统库来迁就 App。
- 零参考 widget 必须给 warning，并建议更简单替代方案。
- 必须确认是否已经安装 MicroPythonOS。
- 必须提示真实硬件安装/部署路径，不能全程只谈桌面预览。
- Web preview 是可选项，且可能因为 Web port 或浏览器限制失败。
- 出错时要把报错信息返回给 AI，让 AI 逐步修改，而不是一次失败就结束。

## 4. 浏览器版和本地 Claude Code 的关系

本地 Claude Code 用法：

```text
/skill-name 用自然语言描述任务
```

例如：

```text
/mpos-gen-app 生成一个极简四则运算计算器 App，包名 com.example.calculator
```

浏览器版不能直接假设用户会操作 Claude Code。浏览器只负责收集需求、展示进度、展示权限请求、展示预览和产物。后端负责启动 AI/agent/skill runner，并把所有过程变成结构化事件返回给前端。

前后端应把 skill 看成一个“长任务执行器”，而不是一个普通同步 API。

## 5. GitHub 仓库协作和子模块约定

浏览器项目应单独创建一个新的 GitHub 仓库，由前后端工程师创建并维护。创建后把 skill 负责人加入 collaborator，或者如果放在组织下，给对应仓库的 write 权限。

不要把浏览器项目直接写进 `MicroPythonOS` 或 `MicroPython_Skills` 仓库。推荐结构：

```text
mpos-ai-app/
├── frontend/
├── backend/
├── runner/
├── docs/
├── vendor/
│   ├── MicroPythonOS/        # git submodule
│   └── MicroPython_Skills/   # git submodule
├── .gitmodules
├── .gitignore
└── README.md
```

### 5.1 前后端工程师创建仓库

建议流程：

1. 在 GitHub 创建独立仓库，例如 `mpos-ai-app` 或 `micropythonos-ai-app-builder`。
2. 仓库可以先设为 private。
3. 在仓库 `Settings -> Collaborators` 中邀请 skill 负责人。
4. 开启 branch protection，要求 PR review 后合并到 `main`。
5. 不把 API key、Claude/DeepSeek token、设备串口信息、个人绝对路径提交进仓库。

### 5.2 初始化浏览器项目仓库

示例命令：

```bash
mkdir mpos-ai-app
cd mpos-ai-app
git init -b main
mkdir -p frontend backend runner docs vendor
```

添加 MicroPythonOS 子模块：

```bash
git submodule add https://github.com/MicroPythonOS/MicroPythonOS.git vendor/MicroPythonOS
```

添加 skill 仓库子模块。如果 skill 仓库是 private，建议用 SSH URL，并确保所有协作者都有权限：

```bash
git submodule add git@github.com:<owner-or-org>/MicroPython_Skills.git vendor/MicroPython_Skills
```

首次提交：

```bash
git add .gitmodules vendor/MicroPythonOS vendor/MicroPython_Skills README.md
git commit -m "chore: initialize browser app repo with mpos submodules"
git remote add origin git@github.com:<owner-or-org>/<repo>.git
git push -u origin main
```

### 5.3 克隆浏览器项目

首次克隆必须带 submodule：

```bash
git clone --recurse-submodules git@github.com:<owner-or-org>/<repo>.git
cd <repo>
```

如果已经普通 clone 了，再补拉 submodule：

```bash
git submodule update --init --recursive
```

日常拉取更新：

```bash
git pull --rebase
git submodule update --init --recursive
```

### 5.4 普通前后端提交流程

浏览器项目代码在父仓库中提交：

```bash
git checkout main
git pull --rebase
git submodule update --init --recursive

git checkout -b feat/session-api
# 修改 frontend/backend/runner/docs
git status
git add frontend backend runner docs
git commit -m "feat: add session API skeleton"
git push -u origin feat/session-api
```

然后在 GitHub 上创建 PR，review 后合并。

### 5.5 子模块修改和更新规则

重点：父仓库不会保存子模块的文件内容，只保存子模块指向的 commit SHA。

如果 skill 负责人修改 `MicroPython_Skills`：

```bash
cd vendor/MicroPython_Skills
git checkout main
git pull --ff-only
# 修改 skill 文件
git status
git add mpos-dev mpos-gen-app mpos-test-app mpos-package-app mpos-deploy-app mpos-publish-app README.md
git commit -m "feat: protocolize mpos app generation skills"
git push
```

然后回到浏览器父仓库，提交新的 submodule 指针：

```bash
cd ../..
git status
git add vendor/MicroPython_Skills
git commit -m "chore: bump MicroPython_Skills submodule"
git push
```

如果要更新 `MicroPythonOS`：

```bash
cd vendor/MicroPythonOS
git checkout main
git pull --ff-only
cd ../..
git add vendor/MicroPythonOS
git commit -m "chore: bump MicroPythonOS submodule"
git push
```

原则：

- 浏览器项目一般只读 `MicroPythonOS`，不要在浏览器项目中直接改 OS 代码。
- skill 改造应先提交到 `MicroPython_Skills` 仓库，再在浏览器父仓库 bump submodule 指针。
- 如果子模块目录显示 detached HEAD，需要先 `git checkout main` 或切到明确分支再修改。
- 父仓库 PR 中如果看到 `vendor/MicroPythonOS` 或 `vendor/MicroPython_Skills` 变化，表示 submodule 指针变了，需要确认对应子仓库 commit 已经 push。

### 5.6 GitHub Actions 和私有子模块

如果后端 CI 要 checkout 子模块，workflow 需要启用 submodules：

```yaml
- uses: actions/checkout@v6
  with:
    submodules: recursive
```

如果 `MicroPython_Skills` 是 private，默认 `GITHUB_TOKEN` 可能没有权限读取另一个 private repo。需要配置最小权限 PAT、GitHub App token，或 deploy key：

```yaml
- uses: actions/checkout@v6
  with:
    submodules: recursive
    token: ${{ secrets.SUBMODULE_READ_TOKEN }}
```

私有 token 只放 GitHub Secrets，不写入仓库。

### 5.7 `.gitignore` 建议

浏览器父仓库应忽略运行产物和敏感文件：

```gitignore
.env
.env.*
!.env.example
node_modules/
dist/
build/
.venv/
__pycache__/
*.pyc
tmp/
artifacts/
sessions/
*.mpk
*.bin
*.uf2
```

如果需要保留示例产物，用 `docs/examples/` 放小文件，并明确不是用户真实 session 输出。

相关官方文档：

- GitHub 邀请 collaborator：https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository
- GitHub 克隆仓库：https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository
- GitHub 拉取远端更新：https://docs.github.com/en/get-started/using-git/getting-changes-from-a-remote-repository
- GitHub Pull Request：https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests
- Git submodule 官方文档：https://git-scm.com/docs/git-submodule
- Git submodule 工作流说明：https://git-scm.com/docs/gitsubmodules.html
- GitHub SSH key：https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account
- GitHub deploy keys：https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys
- GitHub Actions checkout：https://github.com/actions/checkout

## 6. 浏览器产品形态

建议第一版页面包含：

- Prompt 输入框：用户描述想生成的 App。
- 语言切换：中文 / English，至少支持基础中英文转换。
- App 元信息表单：包名、显示名、publisher、version、目标平台。
- MicroPythonOS 安装引导：展示设备是否已安装 OS，未安装或不确定时引导到 `https://install.micropythonos.com/`。
- 目标选择：
  - Desktop smoke test
  - Web preview
  - Physical device deploy
  - Package only
- 进度时间线：analysis、generation、test、package、deploy、publish。
- 权限弹窗：文件写入、运行脚本、连接设备、烧录、上传。
- 错误面板：错误码、日志、建议下一步、可重试按钮。
- 对话记录：保存用户需求、AI 回复、工具日志、错误和用户确认动作。
- 连续修改入口：允许用户基于已有 session 继续说“改一下按钮布局”“增加设置页”，而不是每次从零生成。
- 预览区：
  - desktop screenshot
  - Web preview iframe 或独立页面
  - 真实设备截图或运行日志
- 产物区：
  - App 源码文件列表
  - `MANIFEST.JSON`
  - `.mpk`
  - `generation_result.json`
  - `app_test_result.json`
  - `package_result.json`
  - `deploy_result.json`
  - `publish_result.json`
- 发布引导区：App 生成、测试、打包完成后，展示上传到 `https://upystore.io/developer` 的检查清单和手工步骤。

### 6.1 产品必须解决的用户路径

第一版不要只做“输入 prompt -> 等待 -> 下载文件”。这个产品的核心是把非专业用户带完整走完 MicroPythonOS App 生命周期：

1. 用户用中文或英文描述 App。
2. 系统补齐 App 元信息，包括 `fullname`、`publisher`、`version`、显示名、短描述、分类、图标和截图要求。
3. 系统先确认目标环境：只预览、打包、真实设备部署，还是准备发布。
4. 如果用户要跑真实硬件，系统先确认设备是否已经安装 MicroPythonOS。
5. 未安装或不确定时，前端展示 MicroPythonOS 在线安装器链接和基础说明。
6. 后端创建 session，调用 `mpos-*-web` skill 按阶段执行。
7. 前端展示阶段进度、日志、warning、error、artifact 和权限请求。
8. App 生成后，用户可以预览、继续修改、下载源码、下载 `.mpk`、部署到设备。
9. 测试和打包完成后，系统引导用户准备 upystore 发布材料。
10. 发布前只做检查和引导，除非后续明确接入 upystore API；第一版不应假装已经自动发布。

### 6.2 中英文转换和本地化

浏览器产品至少要支持基础中英文转换，原因是用户可能用中文描述需求，但 App 发布材料、错误日志、内部技术提示、upystore 页面或团队协作可能需要英文。

前端要求：

- UI 支持 `zh-CN` 和 `en-US` 两种语言切换。
- Prompt 输入框允许中文、英文或中英混合。
- 用户输入后可以显示“原始需求”和“转换后的技术需求”两个视图。
- 错误面板默认给用户语言版本，同时保留英文原始错误码和原始日志。
- App 元信息建议支持双语字段：
  - `display_name_zh`
  - `display_name_en`
  - `short_description_zh`
  - `short_description_en`
  - `release_notes_zh`
  - `release_notes_en`

后端要求：

- 保存 `prompt_original`，不能只保存翻译后的文本。
- 保存 `prompt_language`，例如 `zh-CN`、`en-US`、`mixed`、`unknown`。
- 保存 `prompt_normalized_en`，作为给 AI 做技术规划和 API 检索的稳定输入。
- 保存 `prompt_normalized_zh`，用于中文 UI 回显和交付说明。
- 翻译失败不能中断整个生成流程，应返回 warning，并继续使用原始 prompt。
- 任何翻译服务、模型 key、代理配置都只能放服务端环境变量或 secret 管理中，不能进入仓库。

建议结构：

```json
{
  "language": {
    "ui_locale": "zh-CN",
    "prompt_language": "mixed",
    "prompt_original": "做一个 calculator，支持深色模式",
    "prompt_normalized_zh": "做一个计算器，支持深色模式。",
    "prompt_normalized_en": "Create a calculator app with dark mode support."
  }
}
```

### 6.3 MicroPythonOS 安装引导

浏览器产品必须明确告诉用户：生成 App 和安装 OS 是两件事。真实设备运行前，设备必须先有 MicroPythonOS。

前端需要提供一个“设备准备”区：

- “我只想先预览”：默认走 desktop smoke 或 Web preview。
- “我有真实设备”：提示连接 USB，并请求浏览器/后端检测串口能力。
- “我还没安装 MicroPythonOS”：打开或提示访问 `https://install.micropythonos.com/`。
- “我已经安装 MicroPythonOS”：继续做设备探测和 App 部署。

安装提示文案应该包含：

- 在线安装器链接：`https://install.micropythonos.com/`
- 推荐浏览器：Chrome、Edge、Brave 等支持 WebSerial 的浏览器。
- 设备需要 USB 连接。
- 必要时进入 bootloader mode。
- 安装 OS 后再回到本产品继续部署 App。

后端不要仅凭“用户说装好了”就认为设备可用。部署前仍要做能力探测，并把失败归类清楚：

- 没检测到串口：`DEVICE_NOT_CONNECTED`
- 设备不是 bootloader：`DEVICE_BOOTLOADER_NOT_FOUND`
- 设备上无法 import `mpos`：`MPOS_NOT_INSTALLED_ON_DEVICE`
- 设备探针脚本失败但 `mpremote` 文件复制成功：记录为 `device-copy`，不是 App 生成失败。

### 6.4 生成完成后的 upystore 发布引导

App 生成成功不等于可以直接发布。浏览器产品在 `package_done` 后必须给用户一个“发布准备”流程，引导去 upystore。

发布入口：

- uPyStore 首页：`https://upystore.io/`
- uPyStore 开发者入口：`https://upystore.io/developer`

第一版建议做“发布引导”，不要默认自动上传。前端展示：

- `.mpk` 下载链接，文件名必须是 `<fullname>_rN.mpk`，例如 `com.example.demo_r1.mpk`。
- `MANIFEST.JSON` 检查结果，尤其是 `publisher` 必填。
- App 图标是否存在。
- 截图是否符合 PNG/JPEG/WebP。
- 短描述、长描述、分类、版本号、release notes 是否齐全。
- 桌面 smoke、Web preview、真实设备部署的状态。
- upystore 是否已有同名 App 或同 release 的检查结果。
- “打开 upystore 开发者入口”按钮。
- “下载发布材料包”按钮，包含 `.mpk`、图标、截图、manifest、release notes、publish_result.json。

后端输出的 `publish_result.json` 至少要能驱动前端展示：

```json
{
  "stage": "publish",
  "status": "ready_for_manual_upload",
  "upystore": {
    "home_url": "https://upystore.io/",
    "developer_url": "https://upystore.io/developer",
    "mode": "manual_guidance"
  },
  "checks": [
    {
      "name": "manifest.publisher",
      "status": "passed"
    },
    {
      "name": "mpk_release_filename",
      "status": "passed"
    }
  ],
  "artifacts": [
    "com.example.demo_r1.mpk",
    "MANIFEST.JSON",
    "icon_64x64.png",
    "screenshot.png"
  ]
}
```

如果后续要做自动上传，必须增加独立权限确认，并把 token、账号、审核状态、上传结果作为受保护信息处理。

### 6.5 对话记录和审计日志

浏览器产品必须把对话和执行过程当成一等数据保存。否则一旦生成失败、页面刷新、浏览器关闭或用户想继续修改，就只能从头开始。

每个 session 至少保存：

- 用户原始输入。
- 翻译/规范化后的需求。
- AI 的阶段性回复。
- skill runner 调用记录。
- 权限请求和用户选择。
- 每个阶段的开始/结束时间。
- stdout/stderr 摘要。
- 结构化 warning/error。
- 生成文件 manifest。
- 每次继续修改的 diff 和原因。
- 最终交付说明。

对话记录需要支持：

- 重新打开历史 session。
- 从最近 checkpoint 恢复。
- 导出 session bundle。
- 复制错误信息给 AI 继续修。
- 面向用户的简洁摘要和面向工程师的完整日志分开展示。

前端不要只保存浏览器内存状态。刷新页面后，用户应该还能看到之前的 App、进度、错误和产物。

### 6.6 连续修改和版本管理

用户生成完第一版后，大概率会继续要求修改。产品必须把“连续修改”当成主流程：

- “继续修改这个 App”按钮使用原 `session_id`。
- 每次修改创建新的 `revision_id` 或 `change_id`。
- 修改前读取当前 artifact manifest 和 App 源码快照。
- AI 必须基于现有 App 修改，不应无提示重建并覆盖全部文件。
- 应展示 diff 或文件变更摘要，再请求用户确认写入。
- 修改后重新跑必要阶段：API check、desktop smoke、package，必要时部署。
- 如果只是 UI 文案修改，不必强制重跑设备部署；如果涉及硬件能力、依赖、manifest 或启动流程，必须重新部署验证。
- 发布版本要按 release 编号递增：`_r1`、`_r2`、`_r3`。
- `version` 字段和 `_rN` 关系要在 UI 上解释清楚，避免用户只改一个忘了另一个。

建议 session 结构：

```text
session sess_xxx
├── revision r1：初始生成
├── revision r2：修改布局
├── revision r3：增加设置页
└── latest -> r3
```

连续修改失败时不能覆盖最后一个成功版本。前端要能让用户回到上一个成功 revision。

### 6.7 错误反馈和逐步修复体验

这个产品必须默认承认 LLM 输出质量不稳定。用户看到失败时，系统要帮他把错误带回 AI，而不是只显示“失败”。

前端需要有：

- “复制给 AI 修复”按钮。
- “用当前错误继续修复”按钮。
- 错误上下文预览，包括阶段、错误码、关键日志、artifact 路径、MicroPythonOS commit、API summary 版本。
- warning 和 error 分级显示。
- retry 按钮要说明是从当前 checkpoint 重试，不是全部重做。

后端 retry 要求：

- retry 使用新的 `idempotency_key`。
- retry 读取上一轮失败的 result JSON 和 activity log。
- retry 不删除失败现场。
- retry 成功后新建 revision 或 checkpoint，不覆盖历史错误记录。
- 超时、取消、权限拒绝要有独立状态，不能都归类成 failed。

### 6.8 第一版建议页面拆分

建议前端第一版拆成这些页面或区域：

- 首页/创建页：prompt、语言、App 元信息、目标选择。
- Session 工作台：进度时间线、对话、日志、权限、预览、产物。
- App 文件页：源码树、manifest、图标、截图、diff。
- 设备页：OS 安装引导、串口检测、设备能力、部署历史。
- 发布页：upystore checklist、发布材料包、上传引导。
- 历史页：历史 session、revision、继续修改入口。

最小可交付版本也至少要保留：创建 session、阶段进度、错误面板、artifact 下载、继续修改、upystore 引导。

### 6.9 功能优先级建议

P0 必须有：

- 创建 session 和恢复 session。
- 中文/英文 UI 切换。
- 中文/英文 prompt 输入和基础转换。
- App 元信息补全，尤其是 `fullname`、`publisher`、`version`。
- 阶段进度时间线。
- API 校验、生成、desktop smoke、打包 `.mpk`。
- MicroPythonOS 安装引导和安装链接。
- artifact manifest 展示和下载。
- 结构化错误面板、复制错误、基于错误 retry。
- 对话记录和 activity log。
- 基于同一 App 的继续修改。
- upystore 发布检查清单和开发者入口。

P1 应尽快有：

- Web preview iframe 或独立页面。
- 真实设备探测和 `device-copy` 部署。
- session bundle 导出。
- revision diff 展示。
- 发布材料包下载。
- 图片格式检查和截图上传。

P2 后续增强：

- 自动生成双语 release notes。
- 自动检查 upystore 同名 App 或同 release 状态。
- 自动上传 upystore，但必须先设计账号、token、权限和审计。
- 多用户团队协作、评论、任务分配。
- 浏览器内串口日志实时显示。

## 7. 后端核心职责

后端不是简单转发 prompt。后端至少需要：

- 创建 session。
- 保存 checkpoint。
- 管理长任务队列。
- 流式返回事件。
- 处理取消。
- 处理重试。
- 处理超时。
- 管理 artifact。
- 做 capability negotiation。
- 做 permission prompt。
- 调用 AI/Claude Code/skill runner。
- 调用本机脚本、桌面 runner、Web runner、设备部署工具。
- 隔离不同用户或不同 session 的工作目录。

推荐后端接口：

```text
GET  /api/capabilities
POST /api/sessions
GET  /api/sessions/:session_id
GET  /api/sessions/:session_id/events
POST /api/sessions/:session_id/actions/analyze
POST /api/sessions/:session_id/actions/generate
POST /api/sessions/:session_id/actions/test
POST /api/sessions/:session_id/actions/package
POST /api/sessions/:session_id/actions/deploy
POST /api/sessions/:session_id/actions/publish-check
POST /api/sessions/:session_id/resume
POST /api/sessions/:session_id/retry
POST /api/sessions/:session_id/cancel
GET  /api/sessions/:session_id/artifacts
GET  /api/artifacts/:artifact_id
POST /api/permissions/:permission_id/decision
```

事件推送可以用 SSE 或 WebSocket。第一版用 SSE 通常更简单；如果需要双向控制、终端交互、设备串口实时输入，可以再上 WebSocket。

### 7.1 可参考的现有架构：mpy-hardware-extension

`/home/leeqingshui/mpy-hardware-extension` 是一个 VS Code 插件形态的参考项目，不是 mpos 浏览器项目的直接代码来源。它值得借鉴的是“浏览器 UI / 会话控制器 / 协议工具 / 本地 shim / artifact / session log”的分层，不是硬件选型、接线图和普通 MicroPython 固件生成流程。

不要照搬这些部分：

- 普通 MicroPython 固件项目的 `firmware/main.py` 目录结构。
- 板卡/传感器选型、接线图、驱动生成和 pin layout overlay。
- GitHub 登录、credits、云端计费逻辑，除非浏览器产品后续明确要做多用户商业化。
- `MPYHW_READY` 之类普通 MicroPython 硬件项目成功标记。
- VS Code `acquireVsCodeApi()`、Activity Bar、WebView CSP 细节。

mpos 项目的核心对象是 MicroPythonOS App、`MANIFEST.JSON`、LVGL UI、`.mpk`、真实设备上的 MicroPythonOS runtime 和 upystore 发布材料。

可重点阅读这些文件：

- `/home/leeqingshui/mpy-hardware-extension/docs/plugin-architecture-and-skill-acceptance.md`
- `/home/leeqingshui/mpy-hardware-extension/docs/Blockless MicroPython六阶段Skill插件工作流与UI完整规范.md`
- `/home/leeqingshui/mpy-hardware-extension/contracts/protocol_messages.json`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/core/protocol-registry.ts`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/core/protocol-loop.ts`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/extension/session-controller.ts`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/extension/session-recorder.ts`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/extension/artifact-index.ts`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/extension/device-lock.ts`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/extension/device-shim.ts`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/webview/components/message-bus.js`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/webview/components/ActivityTimeline.js`
- `/home/leeqingshui/mpy-hardware-extension/mpy-hardware-extension/src/webview/components/ArtifactBrowser.js`

它当前的核心链路可以抽象为：

```text
WebView UI
  -> SessionController
  -> ProtocolLoop
  -> LLM / skill phase prompt
  -> protocol tools
  -> file/script/device/ui executors
  -> tool_result
  -> phase_complete
  -> artifact/session log
```

mpos 浏览器项目应改造成：

```text
Browser Frontend
  -> Backend Session API
  -> Runner Worker / Skill Adapter
  -> mpos-*-web skills
  -> MicroPythonOS scripts / desktop runner / web preview / device deploy
  -> structured result JSON
  -> artifact manifest + session log
  -> Frontend timeline / preview / publish guide
```

也就是说，VS Code 插件里的 `SessionController` 应该变成后端的 `RunnerController` 或 `SessionOrchestrator`；VS Code WebView 里的 message bus 应该变成浏览器前端的 SSE/WebSocket client；`DeviceShim` 应该变成后端本机 runner 的 Python/Node shim；`ArtifactBrowser` 的相对路径和 host-only 绝对路径隔离规则要保留。

### 7.2 建议采用的浏览器端总体架构

第一版推荐分成 5 层：

```text
frontend/
  App Builder Workbench
  Session Timeline
  Approval / Permission Dialogs
  Preview / Device / Publish panels

backend-api/
  Auth / session REST API
  SSE event stream
  Artifact file service
  Permission decision endpoint

runner/
  SessionOrchestrator
  SkillAdapter for mpos-*-web
  Protocol tool dispatcher
  Timeout / retry / cancellation manager

local-executors/
  File executor
  Script executor
  Desktop preview executor
  Web preview executor
  Device executor
  Publish-check executor

storage/
  session_state.json or database rows
  activity_log.jsonl
  artifact_manifest.json
  generated App workspace
  package/deploy/publish result files
```

职责边界：

- 前端只展示、收集输入、发起 action、展示 permission prompt 和 artifact，不直接执行 shell、写本机文件或碰串口。
- 后端 API 管 session、权限、artifact、用户身份、事件流，不直接把 LLM prose 当状态。
- Runner 负责把 mpos skill 阶段跑起来，并把阶段产物转成统一事件。
- Local executors 负责具体副作用：文件写入、脚本执行、desktop smoke、Web preview、设备部署。
- Storage 是恢复和审计的 source of truth，不能只靠浏览器内存或对话上下文。

### 7.3 协议工具可以复用六类，但 payload 要改成 mpos

`mpy-hardware-extension` 已经验证过 6 类通用协议工具，这个抽象可以保留：

| 工具 | 浏览器 mpos 项目中的职责 |
|---|---|
| `approval_request` | 用户确认需求、覆盖文件、安装依赖、连接设备、部署、打开安装器、准备发布 |
| `file_operation` | 只允许写 session/App 工作目录，生成 `MANIFEST.JSON`、`assets/main.py`、图标和 result JSON |
| `script_run` | 调用 MicroPythonOS 脚本、API 检查、desktop smoke、打包、lint、Web preview 服务 |
| `device_command` | 设备扫描、确认 MicroPythonOS 是否安装、`mpremote` 拷贝、MPK install、日志读取 |
| `status_update` | 推送阶段进度、warning、当前动作和预计下一步 |
| `phase_complete` | 每个阶段收尾，写 checkpoint、result JSON、artifact manifest 和 next action |

mpos 阶段建议固定为：

```text
analyze
prepare_deps
generate
test
package
deploy
publish_check
```

硬性规则：

- 每个阶段必须以 `phase_complete` 或结构化 failed 收尾。
- `phase_complete` 必须携带 `session_id`、`stage`、`status`、`checkpoint_id`、`result_path`、`artifact_manifest_path`。
- 浏览器不要解析 AI 最终自然语言回答作为状态。
- 所有副作用都要可审计：谁发起、何时发起、用户是否确认、命令摘要、结果文件在哪里。
- `file_operation` 必须限制在 session/App 目录，不能写 MicroPythonOS 的 OS 层代码。
- `device_command` 必须串行化，同一设备同一时间只能一个部署/文件操作占用串口。

### 7.4 前端工程师具体要求

前端可以参考 `mpy-hardware-extension` 的 WebView 组件思想，但实现上应是普通浏览器应用，不要依赖 VS Code API。

建议页面组件：

- `Workbench`：创建 session，输入 prompt，选择语言、目标、App 元信息。
- `ActivityTimeline`：显示用户消息、AI 摘要、阶段开始/结束、warning/error、retry、cancel。
- `ApprovalPromptHost`：统一承载权限确认卡片，所有确认都带 `permission_id`。
- `ArtifactBrowser`：展示源码、manifest、截图、`.mpk`、result JSON、session bundle。
- `PreviewPanel`：展示 desktop screenshot、可选 Web preview iframe、Web preview 限制提示。
- `DevicePanel`：展示 MicroPythonOS 安装状态、安装器链接、串口扫描、设备部署日志。
- `PublishPanel`：展示 upystore checklist、发布材料包、开发者入口。
- `HistoryPanel`：历史 session、revision、继续修改入口。

前端实现要求：

- 通过 `GET /api/sessions/:session_id/events` 订阅 SSE。
- 刷新页面后用 `GET /api/sessions/:session_id` 恢复状态。
- 所有按钮都使用 `idempotency_key`，避免重复点击造成重复生成、重复部署或重复打包。
- `approval_request` 需要防重复渲染，同一个 `permission_id` 只能回答一次。
- long-running 阶段要有持续可见的 working 状态，不能只有全屏 loading。
- warning、error、blocked、cancelled、timeout 要分开展示。
- 错误面板必须有“复制给 AI 修复”和“用当前错误重试”。
- artifact 列表只展示后端返回的相对路径、角色、大小、hash、mime、阶段，不展示服务器绝对路径。
- 打开 artifact 时只传 `artifact_id` 或 manifest 内相对路径，由后端校验后返回下载/预览 URL。
- Web preview 页面要明确提示：这是可选预览，不等于真实硬件验证。
- 真实硬件入口不能隐藏在高级设置里，生成完成后应明确出现“部署到设备”和“未安装 OS 先安装”的路径。

### 7.5 后端工程师具体要求

后端应把 `mpy-hardware-extension` 的 SessionController、ProtocolLoop、SessionRecorder、ArtifactIndex、DeviceCommandQueue 思路服务化。

建议服务模块：

- `SessionService`：创建 session、读取 session、列历史、记录 revision。
- `EventService`：把 runner 事件写入日志并推送 SSE。
- `RunnerController`：控制一个 session 的 in-flight run、AbortController、retry、resume、timeout。
- `ProtocolDispatcher`：把 `approval_request`、`file_operation`、`script_run`、`device_command` 路由到对应 executor。
- `PermissionService`：创建权限请求、等待用户决定、过期、审计。
- `ArtifactService`：生成 artifact manifest、hash、mime、下载 URL、路径安全校验。
- `DeviceService`：串口扫描、设备锁、MicroPythonOS 探测、部署、日志读取。
- `MposSkillAdapter`：调用 `mpos-*-web` skill，读取阶段 result JSON，转换为事件。
- `PublishService`：检查 manifest、MPK 文件名、截图格式、upystore 发布材料。

后端实现要求：

- 单个 session 同一时间只允许一个主流程 run。
- 同一设备串口同一时间只允许一个 device operation。
- `cancel` 要杀掉或中断正在运行的子进程，并释放设备锁。
- `retry` 不能删除失败现场，必须读取上一次失败的 result JSON 和 activity log。
- `resume` 必须从 `checkpoint_id` 和 `session_state.json` 恢复，而不是重新问一遍模型。
- 每个阶段都要写 `activity_log.jsonl`，每行带 `seq`、`ts`、`session_id`、`stage`。
- artifact manifest 必须去重、计算 hash，并跳过不存在的文件。
- 绝对路径只允许后端内部使用，前端只看到相对路径或 `artifact_id`。
- 运行脚本必须有白名单，不允许模型或前端传任意 shell。
- script/device/file 操作失败要返回结构化错误，不能让 runner 直接崩溃。
- token、API key、串口路径、服务器绝对路径不要泄露给普通前端用户。
- MicroPythonOS 和 MicroPython_Skills 作为 submodule 时，后端要记录当前 commit SHA。

推荐后端目录：

```text
backend/
  src/api/
  src/session/
  src/events/
  src/runner/
  src/protocol/
  src/executors/
  src/artifacts/
  src/devices/
  src/publish/
  src/storage/
runner/
  scripts/
  schemas/
  adapters/mpos/
```

### 7.6 浏览器版最小数据流

一次完整生成建议按这个数据流实现：

```text
POST /api/sessions
  -> create session_root
  -> write session_state.json
  -> return session_id

POST /api/sessions/:id/actions/analyze
  -> RunnerController starts run
  -> SSE phase_start(analyze)
  -> mpos-analyze-app-web
  -> analysis_result.json
  -> phase_complete(requirements_analyzed)

POST /api/sessions/:id/actions/generate
  -> mpos-gen-app-web
  -> API summary full-read and cross-check
  -> write App files
  -> generation_result.json
  -> artifact_manifest.json update

POST /api/sessions/:id/actions/test
  -> desktop smoke
  -> optional Web preview
  -> app_test_result.json
  -> screenshot artifact

POST /api/sessions/:id/actions/package
  -> validate MANIFEST.JSON
  -> build <fullname>_rN.mpk
  -> package_result.json

POST /api/sessions/:id/actions/deploy
  -> permission prompt
  -> device scan / OS check / deploy
  -> deploy_result.json

POST /api/sessions/:id/actions/publish-check
  -> upystore readiness check
  -> publish_result.json
  -> publish materials bundle
```

对于“连续修改”：

```text
POST /api/sessions/:id/revisions
  -> create revision rN+1 from latest successful artifact snapshot
  -> run analyze/generate/test/package as needed
  -> keep previous successful revision immutable
```

本地 Claude Code 测试和浏览器项目要共用同一套阶段产物名称。差别只是入口不同：

- Claude Code：用户用 `/mpos-plan-app 描述` 或 `/mpos-gen-app 描述`，产物落在本地目录。
- 浏览器：前端发 API，后端 runner 调用 `mpos-*-web`，产物落在 session workspace。

两边都必须以 result JSON、artifact manifest、activity log 和 checkpoint 为状态依据。

## 8. 协议字段要求

浏览器版和本地 skill runner 之间需要统一 JSON 协议。最低字段：

```json
{
  "protocol_version": "mpos-ai-app/v1",
  "session_id": "sess_20260723_001",
  "checkpoint_id": "generation_done",
  "idempotency_key": "user-click-uuid",
  "operation": "generate_app",
  "status": "running",
  "capabilities": {
    "desktop_preview": true,
    "web_preview": true,
    "physical_device": false,
    "mpremote": true,
    "upystore_publish": false
  },
  "input": {
    "prompt": "生成一个极简四则运算计算器 App",
    "fullname": "com.example.calculator",
    "publisher": "com.example",
    "version": "1.0.0"
  }
}
```

必须支持：

- `session_id`
- `checkpoint/resume`
- `cancellation`
- `retry`
- `timeout`
- `idempotency_key`
- `protocol_versioning`
- `capability negotiation`
- `structured error reporting`
- `artifact/file manifest`
- `permission prompts for file/device/script operations`

## 9. Checkpoint / Resume

每个阶段成功后必须写 checkpoint，避免中断后从头来。

建议 checkpoint：

```text
session_created
requirements_analyzed
api_checked
code_generated
desktop_test_done
web_preview_done
package_done
device_deploy_done
publish_check_done
completed
failed
cancelled
```

每个 checkpoint 需要记录：

- 输入参数
- skill 名称和版本
- MicroPythonOS commit
- API summary 版本
- 输出文件列表
- 错误或 warning
- 下一步可执行动作

## 10. 错误上报格式

不要只返回字符串错误。必须结构化：

```json
{
  "error": {
    "code": "LVGL_API_MISSING",
    "message": "lv.obj.set_style_row_gap 不在当前 lvgl_api_summary.json 中",
    "stage": "generation",
    "retryable": true,
    "owner": "app",
    "details": {
      "symbol": "lv.obj.set_style_row_gap",
      "suggestion": "改用 set_style_pad_row 或 flex + 普通 button 布局"
    },
    "logs": [
      "generation_result.json: API check failed"
    ]
  }
}
```

常见错误码建议：

```text
MPOS_NOT_FOUND
MPOS_NOT_INSTALLED_ON_DEVICE
LVGL_API_MISSING
MPOS_API_MISSING
MANIFEST_MISSING_FIELD
MPK_RELEASE_NAME_INVALID
WIDGET_ZERO_REFERENCE
DESKTOP_RUNNER_SEGFAULT
WEB_PREVIEW_UNSUPPORTED
WEB_PREVIEW_BUILD_FAILED
DEVICE_NOT_CONNECTED
DEVICE_BOOTLOADER_NOT_FOUND
DEVICE_PROBE_FAILED
DEVICE_DEPLOY_FAILED
SCRIPT_TIMEOUT
PERMISSION_DENIED
USER_CANCELLED
TOOLCHAIN_MISSING
EXTERNAL_OS_BLOCKED
UNSUPPORTED_IMAGE_FORMAT
TRANSLATION_WARNING
```

`owner` 建议取值：

```text
app
skill
backend
frontend
toolchain
micropythonos
device
external
user
```

## 11. 权限模型

浏览器版不能默默执行危险动作。至少这些动作需要权限确认：

- 创建/覆盖 App 文件
- 执行本地脚本
- 安装依赖
- 打包 `.mpk`
- 连接 USB/串口设备
- 拷贝文件到设备
- 烧录固件
- 上传到远端服务
- 删除/清理 session 工作目录

权限请求示例：

```json
{
  "permission_id": "perm_001",
  "session_id": "sess_20260723_001",
  "type": "device_write",
  "title": "允许部署到 ESP32-S3 设备",
  "description": "将 App 文件复制到串口设备 /dev/ttyACM0",
  "risk": "medium",
  "command_preview": "mpremote fs cp -r app :/apps/",
  "expires_at": "2026-07-23T12:00:00Z"
}
```

## 12. Artifact Manifest

每个阶段产生的文件都要进入 manifest。前端不能靠猜路径展示产物。

```json
{
  "artifacts": [
    {
      "id": "art_manifest",
      "kind": "source",
      "path": "internal_filesystem/apps/com.example.calculator/MANIFEST.JSON",
      "mime": "application/json",
      "role": "app_manifest",
      "sha256": "..."
    },
    {
      "id": "art_mpk",
      "kind": "package",
      "path": "tmp/mpos-package-app/com.example.calculator/com.example.calculator_r1.mpk",
      "mime": "application/octet-stream",
      "role": "mpk"
    },
    {
      "id": "art_screenshot",
      "kind": "image",
      "path": "tmp/mpos-test-app/com.example.calculator.png",
      "mime": "image/png",
      "role": "desktop_screenshot"
    }
  ]
}
```

截图/图像输入输出优先支持：

- PNG
- JPEG
- WebP

其他格式需要明确报 `UNSUPPORTED_IMAGE_FORMAT`。

## 13. Web preview 的真实边界

Web preview 只能作为可选预览，不应被描述成完整硬件验证。

已知限制：

- 浏览器不是微控制器。
- Web port 无真实 GPIO、ADC、IMU、摄像头、蓝牙。
- HTTP 走浏览器 `fetch()`，跨域受 CORS 限制。
- IndexedDB 中的 `/data`、`/apps` 可能残留旧状态，需要清理 site data。
- Web build 或工具链可能因为 `machine_timer_type`、Emscripten、patch、依赖问题失败。
- 如果报错，必须把浏览器 console、runner log、结构化错误返回给 AI 逐步修。

因此前端文案应写：

```text
Web preview 是快速预览，不等同于真实硬件部署。涉及摄像头、IMU、GPIO、串口、蓝牙、SD 卡、物理按钮、音频等能力时，必须使用真实设备验证。
```

相关链接：

- MicroPythonOS Web Port 使用说明：https://docs.micropythonos.com/web-port/using/
- Web 最新发布入口：https://web.micropythonos.com/
- GitHub Pages bleeding-edge 入口：https://micropythonos.github.io/MicroPythonOS/

## 14. 真实硬件部署不能省略

项目必须显式支持真实硬件部署路径，不能只做桌面或 Web。

硬件部署有两个层次：

1. 安装/升级 MicroPythonOS 固件。
2. 把生成的 App 安装到已经运行 MicroPythonOS 的设备。

固件安装推荐：

- 使用 WebSerial 安装器：https://install.micropythonos.com/
- 浏览器推荐 Chrome / Edge / Brave。
- 设备需要进入 bootloader mode。

App 部署推荐：

- 优先使用 MicroPythonOS 现有 `mpremote` 流程。
- 不要依赖 raw-repl 假设；MicroPythonOS 的上传/控制脚本和普通 raw-repl 不完全一样。
- 如果设备探测脚本失败，但 `mpremote` 复制成功，应记录为 `device-copy` 模式，而不是把整个部署判为 App 失败。

## 15. 当前本地 MicroPythonOS 支持板卡

按 `/home/leeqingshui/MicroPythonOS/internal_filesystem/lib/mpos/board/*.py` 和运行时探测逻辑，当前已集成的物理板卡包括：

- Freenove ESP32-S3 Display
- Fri3d Camp 2024 Badge
- Fri3d Camp 2026 Badge
- LilyGO T-Display S3
- LilyGO T-HMI
- LilyGO T-Watch S3 Plus
- LilyGo T4
- M5Stack Core2
- M5Stack Fire
- Makerfabs MaTouch ESP32-S3 SPI IPS 2.8" with Camera OV3660
- Hardkernel ODROID-GO
- unPhone / unPhone 9
- SQUiXL
- DFRobot UniHiker K10
- Waveshare ESP32-S3-Touch-LCD-2

桌面/仿真：

- `linux.py`：Linux / macOS SDL target。
- `web` build：浏览器 WebAssembly target。

注意：上游 `lvgl_micropython` 有更多 ESP32 board 目录，但不等于 MicroPythonOS 已完成运行时适配。

## 16. Ubuntu 24.04 + VMware 基础环境

如果前后端工程师使用 Windows 主机，推荐用 VMware Workstation Pro 安装 Ubuntu 24.04 Desktop VM。这样环境更接近实际 Linux runner，避免 Windows 路径、shell、串口权限和构建依赖差异。

### 16.1 下载 Ubuntu 24.04 镜像

推荐下载 Ubuntu 24.04.4 LTS Desktop AMD64。

官方页面：

- Ubuntu 24.04 releases 页面：https://releases.ubuntu.com/24.04/
- Desktop ISO 直链：https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso
- SHA256 校验文件：https://releases.ubuntu.com/24.04/SHA256SUMS
- Ubuntu Desktop 下载入口：https://ubuntu.com/download/desktop

Windows 校验 ISO：

```powershell
Get-FileHash .\ubuntu-24.04.4-desktop-amd64.iso -Algorithm SHA256
```

Linux 校验 ISO：

```bash
sha256sum ubuntu-24.04.4-desktop-amd64.iso
```

把输出和 `SHA256SUMS` 中对应行比对。

### 16.2 下载 VMware Workstation Pro

VMware Workstation Pro 现在通过 Broadcom Support Portal 下载。按 Broadcom 说明，较新版本 Workstation Pro / Fusion Pro 对 Commercial、Educational、Personal 用户免费使用，不需要 license key，但下载通常需要 Broadcom 基础账号。

官方链接：

- Broadcom Support Portal：https://support.broadcom.com/
- 下载和许可说明：https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hype.html
- 下载 VMware Workstation Pro 说明：https://knowledge.broadcom.com/external/article/344595/downloading-vmware-workstation-pro.html
- 免费软件下载说明：https://knowledge.broadcom.com/external/article/397417/downloading-free-software-from-the-broad.html
- 安装 VMware Workstation Pro：https://knowledge.broadcom.com/external/article/387947/installing-vmware-workstation-pro.html
- 创建虚拟机说明：https://knowledge.broadcom.com/external/article?legacyId=1018415
- VMware Tools 安装说明：https://knowledge.broadcom.com/external/article/315363/install-vmware-tools-in-vmware-products.html
- open-vm-tools 支持说明：https://knowledge.broadcom.com/external/article/313456/vmware-support-for-openvmtools.html

不要从第三方软件下载站下载安装包，除非团队明确接受供应链风险。

### 16.3 Windows 开启虚拟化

如果 VMware 提示无法启动 VM，先检查 BIOS/UEFI 虚拟化是否启用。

官方链接：

- Microsoft：在 Windows 上启用虚拟化：https://support.microsoft.com/zh-CN/Windows/Experience/enable-virtualization-on-windows
- VMware Workstation FAQ / 系统要求：https://knowledge.broadcom.com/external/article?legacyId=90112
- VMware Host OS 支持信息：https://knowledge.broadcom.com/external/article/315436/supported-host-operating-systems-for-vmw.html

Windows 检查方式：

1. 打开任务管理器。
2. 进入“性能”。
3. 选择 CPU。
4. 查看“虚拟化：已启用/已禁用”。

如果禁用，进入 BIOS/UEFI 打开 Intel VT-x 或 AMD-V。

### 16.4 创建 Ubuntu VM 推荐配置

VMware 中选择：

- `Create a New Virtual Machine`
- Typical
- Installer disc image file：选择 Ubuntu 24.04 ISO
- Guest OS：Linux / Ubuntu 64-bit
- CPU：至少 4 vCPU，推荐 6-8 vCPU
- 内存：至少 8GB，推荐 16GB
- 磁盘：至少 80GB，推荐 120GB，单文件或拆分均可
- 网络：NAT 优先，桥接可选
- USB Controller：USB 3.x
- Display：可开启 3D acceleration，但如果 SDL/WebGL 异常可以关闭重试

如果要连接 ESP32 设备：

- 插入 USB 设备后，在 VMware 菜单中选择连接到 Guest。
- 确认 Ubuntu 内能看到 `/dev/ttyACM*` 或 `/dev/ttyUSB*`。
- 必要时把当前用户加入 `dialout` 组。

```bash
sudo usermod -aG dialout "$USER"
```

执行后需要退出登录或重启 VM。

### 16.5 Ubuntu 初始依赖

进入 Ubuntu 后先更新：

```bash
sudo apt update
sudo apt upgrade -y
```

安装常用开发依赖：

```bash
sudo apt install -y \
  git curl ca-certificates build-essential \
  python3 python3-pip python3-venv python3-dev \
  pkg-config cmake ninja-build make gcc g++ clang lld \
  libsdl2-dev libffi-dev libjpeg-dev libpng-dev libusb-1.0-0-dev \
  unzip zip jq ripgrep \
  nodejs npm
```

安装 VMware Tools 推荐用 Ubuntu 包：

```bash
sudo apt install -y open-vm-tools open-vm-tools-desktop
sudo reboot
```

如果后续 `make lint` 提示 `uv` 缺失，可以安装 `uv`：

- uv 官方文档：https://docs.astral.sh/uv/

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 17. Claude Code 和 skill 测试环境

Claude Code 官方链接：

- Claude Code Quickstart：https://code.claude.com/docs/en/quickstart
- Claude Code setup：https://docs.anthropic.com/en/docs/claude-code/getting-started
- Claude Code commands：https://code.claude.com/docs/en/commands
- Claude Code skills 中文说明：https://code.claude.com/docs/zh-CN/skills
- Claude skills 概念：https://support.claude.com/en/articles/12512176-what-are-skills
- Claude skills 使用说明：https://support.claude.com/en/articles/12512180-use-skills-in-claude

Ubuntu / Linux 安装 Claude Code：

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude --version
```

或 npm：

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

不要用 `sudo npm install -g @anthropic-ai/claude-code`，容易引发权限问题。

skill 调用方式：

```text
/skill-name 任务描述
```

示例：

```text
/mpos-gen-app 生成一个极简四则运算计算器 App，包名 com.example.cc_skill_smoke
```

建议用 `cc-switch` 或团队已有方式切换到 DeepSeek 模型做 skill 测试，但这不是浏览器系统的硬依赖。任何第三方模型/代理配置都不能把 API key 提交进仓库。

相关第三方链接：

- CC Switch 官网：https://ccswitch.io/
- CC Switch GitHub：https://github.com/farion1231/cc-switch
- DeepSeek 平台：https://platform.deepseek.com/

## 18. 本地 MicroPythonOS 测试命令

前后端工程师主要需要能跑通“预览”和“设备部署”的接口，不一定要修改 skill。

克隆/更新 MicroPythonOS：

```bash
git clone --recurse-submodules https://github.com/MicroPythonOS/MicroPythonOS.git
cd MicroPythonOS
```

如果已经有本地目录：

```bash
cd /home/leeqingshui/MicroPythonOS
git status
git submodule update --init --recursive
```

Linux 桌面运行方式参考：

```bash
./scripts/run_desktop.sh
```

从源码构建 Linux 桌面目标：

```bash
./scripts/build_mpos.sh unix
```

构建 Web target：

```bash
./scripts/build_mpos.sh web
```

构建 ESP32-S3 固件：

```bash
./scripts/build_mpos.sh esp32s3
```

部署单个 App 到设备：

```bash
./scripts/install.sh com.example.your_app
```

注意：如果构建或运行失败，要把完整 stderr/stdout、系统版本、MicroPythonOS commit、skill 产物路径一起返回给 AI。

## 19. 前后端最小联调流程

第一阶段不用真实 AI，可以 mock skill runner：

1. 前端创建 session。
2. 后端返回 `session_id`。
3. 前端订阅 SSE。
4. 后端依次推送：
   - `session_created`
   - `requirements_analyzed`
   - `api_checked`
   - `code_generated`
   - `desktop_test_done`
   - `package_done`
   - `completed`
5. 前端展示 artifact manifest。
6. 用户点击下载 `.mpk`。

第二阶段接真实 skill runner：

1. 输入自然语言需求。
2. 后端创建隔离工作目录。
3. 调用 Claude Code 或 runner。
4. skill 写阶段产物 JSON。
5. 后端读取 JSON 并转换成统一事件。
6. 失败时允许 retry/resume。

第三阶段接设备：

1. 后端 capability 中标记串口设备。
2. 前端弹出权限确认。
3. 后端调用部署脚本或 mpremote。
4. 写入 `deploy_result.json`。
5. 前端展示设备部署结果。

## 20. 前端注意事项

前端不要假设任务一定会成功。必须把失败作为主流程设计。

必须支持：

- 长时间 running 状态。
- 阶段级进度。
- warning 和 error 分开展示。
- 可复制错误日志。
- 继续/重试/取消按钮。
- 权限弹窗。
- artifact 下载。
- session 恢复。
- Web preview 清理缓存提示。
- 真实硬件部署提示。

不建议：

- 只做一个“生成中”全屏 loading。
- 失败后只展示“生成失败”。
- 把 Web preview 说成硬件验证。
- 隐藏原始错误日志。

## 21. 后端注意事项

后端要保证幂等和隔离。

必须支持：

- 每个 session 独立目录。
- idempotency key 防止用户重复点击。
- checkpoint 落盘。
- 任务超时。
- 取消后清理子进程。
- 失败时保留现场。
- artifact 路径不能越权。
- 不把 API key、串口路径、主机绝对路径泄露给普通前端用户，除非是本地单用户工具。

涉及设备和脚本执行时，必须有权限确认。浏览器端的“确认”要落到后端审计日志。

## 22. 和 skill 负责人的接口约定

前后端不要直接解析 Claude 自然语言最终回答作为状态依据。应解析这些结构化文件：

```text
analysis_result.json
generation_result.json
app_test_result.json
package_result.json
deploy_result.json
publish_result.json
plan_state.json
activity_log.jsonl
artifact_manifest.json
```

skill 改造会把这些文件进一步稳定化。前后端只依赖字段 schema，不依赖 Claude 输出文案。

## 23. 已知容易踩坑

- `MANIFEST.JSON` 缺 `publisher` 会导致上传失败。
- `.mpk` 文件名必须带 release 编号 `_rN`。
- `buttonmatrix.set_map` 需要 LVGL 格式约定：行分隔和终止项错误可能导致崩溃。
- `set_style_row_gap` 这类不存在的 LVGL API 必须在生成前被 API check 拦截。
- 某些 widget 在仓库中零使用量，必须 warning。
- `make lint` 可能因为 `uv`/`ruff` 未安装失败，这是工具缺失，不一定是代码问题。
- `mpy-cross` 在构建/freezefs/字节码相关流程中可能需要。
- `lvgl_micropy_unix` 如果启动后几秒 segfault，可能是 OS/desktop runner 预存问题，不一定是 App 问题。
- Web port 构建失败可能是工具链或 Web port patch 问题，不一定是 App 问题。
- 不能为了修 App 修改 MicroPythonOS 的 OS 层代码。

## 24. 推荐分工

skill 负责人：

- 改造 mpos skills。
- 定义协议 schema。
- 定义 artifact manifest。
- 定义错误码。
- 保持 API summary 更新。
- 维护 Claude Code 本地测试流程。

后端工程师：

- session/checkpoint 存储。
- runner 编排。
- SSE/WebSocket。
- 权限系统。
- artifact 服务。
- timeout/cancel/retry。
- 设备部署适配。

前端工程师：

- Prompt 和 App metadata 表单。
- 进度时间线。
- 权限弹窗。
- 错误面板。
- artifact 下载/预览。
- Web preview 容器。
- session 恢复 UI。

共同确认：

- JSON schema。
- 错误码。
- 阶段状态机。
- capability 字段。
- artifact manifest 字段。
- 权限交互。

## 25. 产品定位、宣传 PPT 和视频素材规划

本章节面向前端、后端、产品、运营、拍摄和剪辑人员。目标不是把技术栈讲复杂，而是把“为什么普通人需要它、它解决了什么现实问题、它能让创客项目如何被更多人体验和复刻”讲清楚，并准备可用于路演、学校/科创/STEM 合作、创客空间工作坊、短视频和官网落地页的素材。

### 25.1 产品一句话定位

中文定位：

```text
一个面向入门级创客、科创教育和 STEM 课堂的 AI 应用生成平台：让用户先看到效果，再深入学习，把硬件创意变成可预览、可部署、可复刻、可分发的 MicroPythonOS App。
```

英文定位：

```text
A browser-based AI workbench for maker education and STEM prototyping: describe a MicroPythonOS app in natural language, preview it, package it as MPK, deploy it to real ESP32/ESP32-S3 hardware, and prepare it for uPyStore publishing.
```

给小白用户的说法：

```text
很多创客项目看起来很有趣，但别人真正想复刻时，经常要先看长篇教程、装环境、配依赖、下载代码、理解目录、连设备、烧录系统、上传文件。还没看到效果，兴趣就被消耗掉了。这个产品要做的是：让感兴趣的人先在浏览器里体验起来，再一步步深入学习。
```

给学校/科创老师的说法：

```text
它把“看文章才能复刻”的硬件项目，变成“跟着浏览器流程就能先跑起来”的课堂体验。学生先获得可触摸、可展示、可分享的结果，再理解背后的 MicroPythonOS、设备能力和应用发布流程。
```

给开发者/评委的说法：

```text
它不是普通代码助手，而是把创意原型制作、小批量设备应用分发、多设备运行管理和作品发布串成一条产品化流程。技术能力最终服务的是传播效率：让硬件作品从“少数人能复刻的小众项目”，走向“更多人能体验、修改和继续创作的大众入口”。
```

### 25.2 产品相关事实依据

从 MicroPythonOS 本身和当前 `micropythonos-ai-app-builder` 仓库可以提炼这些事实作为宣传依据：

- MicroPythonOS 是带图形界面、App 生态、App Store/更新能力的 MicroPython OS。
- App 使用 MicroPython + LVGL 编写，最终运行在 MicroPythonOS 上，不是普通网页。
- App 有明确目录结构、`MANIFEST.JSON`、图标、入口文件和 `.mpk` 发布包。
- MicroPythonOS 支持桌面运行、WebAssembly 浏览器运行和 ESP32/ESP32-S3 真机运行。
- 当前 MicroPythonOS 源码中已集成 15 个物理板卡运行时适配，另有 Linux/macOS SDL 桌面目标和 WebAssembly Web target。
- 当前已接入 App Store/uPyStore 发布检查和手工上传引导。
- 当前 builder 是浏览器工作台：`frontend` + `backend` + `runner` + `vendor/MicroPythonOS` + `vendor/MicroPython_Skills`。
- 当前 builder 后端是 FastAPI，前端是 React/Vite，Runner 通过 `mpos-ai-app/v1` 协议写 result JSON、checkpoint、activity log 和 artifact manifest。
- 当前 builder 的核心路径包括自然语言需求、API 校验、源码生成、桌面烟测、可选 Web preview、MPK 打包、可选真机部署、uPyStore 发布准备。
- 当前 builder 固定本地端口：后端 `8000`，前端 `5174`。
- WebSerial 需要安全上下文；本地开发建议使用 `localhost`。
- Web preview 是可选预览，不能被宣传成真实硬件验证。
- 真机路径必须明确包含 MicroPythonOS 安装/确认、设备扫描、部署和日志。
- Tuya/涂鸦 3 款带屏幕板卡目前不能写成“已真实适配”。如果 PPT 或视频需要提前体现，应写成“规划适配 / 重点适配方向 / 概念演示”，并使用明确标注的合成效果画面；只有真实板卡完成 MicroPythonOS 运行时适配和 App 真机运行录制后，才能改成“已适配”。

宣传时不能夸大的点：

- 不能说“无需任何硬件知识就能完成所有复杂硬件项目”。更准确是“降低入门门槛，把工具链和 App 生命周期步骤自动化”。
- 不能说“Web preview 等同真机运行”。Web preview 只能快速看 UI 和部分逻辑。
- 不能说“完全自动发布到 uPyStore”。当前定位是发布检查和手工上传引导，除非后续明确接入上传 API。
- 不能说“AI 一次生成必定成功”。应该强调错误会被结构化记录，用户可以把报错回给 AI 逐步修复。
- 不能说“支持所有 MicroPython 板卡”。当前是 MicroPythonOS 已适配板卡和桌面/Web target。
- 不能把 Tuya/涂鸦概念合成视频说成真实运行视频；对外正式版必须区分“真实适配”与“规划演示”。

当前真实可宣传板卡口径：

```text
当前 MicroPythonOS 已集成 15 个物理板卡运行时适配，并支持 Linux/macOS 桌面模拟和 WebAssembly 浏览器预览目标。宣传物料需要配真实板卡照片和至少 3-5 段真机 App 运行视频，避免只用静态 UI 截图。
```

15 个物理板卡包括：

- Freenove ESP32-S3 Display
- Fri3d Camp 2024 Badge
- Fri3d Camp 2026 Badge
- LilyGO T4 V1.3
- LilyGO T-Display S3
- LilyGO T-HMI
- LilyGO T-Watch S3 Plus
- M5Stack Core2
- M5Stack Fire
- Makerfabs MaTouch ESP32-S3 SPI IPS 2.8" with Camera OV3660
- Hardkernel ODROID-GO
- SQUiXL
- DFRobot UniHiker K10
- unPhone 9
- Waveshare ESP32-S3-Touch-LCD-2

### 25.3 目标受众

第一优先级受众：

- 创客入门用户：想把想法快速做成小屏幕 App，但不熟悉 LVGL、MicroPythonOS、打包和串口部署。
- 科创/STEM 老师：需要一套课堂可演示、学生能跟做、结果能展示的工具链。
- 中学生/大学生创新项目：需要快速做出有屏幕、有交互、可真机展示的作品。
- 创客空间/社团组织者：需要一次 60-120 分钟工作坊就能产出作品。

第二优先级受众：

- MicroPython 开发者：希望把普通脚本升级成带 UI、可发布的 MicroPythonOS App。
- 嵌入式产品原型团队：希望用自然语言快速生成工具面板、测试面板、演示 App。
- App Store/uPyStore 生态贡献者：希望降低 App 创作和发布门槛。

不建议第一版主打：

- 专业量产固件开发。
- 复杂实时控制或安全关键嵌入式系统。
- 完全离线、完全本地、完全无需模型服务的场景。
- 大型多人协作 IDE。

### 25.4 传播主线

宣传 PPT 和视频都应围绕这条主线：

```text
过去：创客项目传播经常停在文章、代码仓库和演示视频里。别人想复刻，要先跨过环境安装、依赖配置、设备烧录、文件上传、版本差异和文档理解这些门槛。

现在：用户在浏览器里描述想法，系统把创意变成可预览、可修改、可打包、可部署到真实设备的 MicroPythonOS App。用户先看到效果，再学习细节。

结果：学生更快获得成就感，老师更容易组织课堂，创客更容易分发作品，小批量设备也能用统一 App 流程管理和更新。硬件项目从“看得懂的人才能复刻”，变成“感兴趣的人也能先体验起来”。
```

建议标题备选：

- 中文：`一句话生成 MicroPythonOS App`
- 中文：`从创意到真机：面向 STEM 的 AI App 工作台`
- 中文：`让学生把想法装进掌上设备`
- 中文：`AI + MicroPythonOS：创客入门的新工具链`
- 中文：`让创客项目从小众教程变成大众体验`
- 中文：`先看到效果，再学会原理`
- 英文：`Natural Language to MicroPythonOS Apps`
- 英文：`An AI App Builder for Maker Education`
- 英文：`From Idea to Device in One Browser Workflow`

建议口号：

- `说出想法，生成 App，装到设备。`
- `先做出来，再学深入。`
- `让 STEM 课堂从代码讲解变成作品创造。`
- `从浏览器到真机，从作品到应用商店。`
- `不只是看文章，是真的跑起来。`
- `把硬件创意变成别人也能复刻的作品。`

### 25.5 宣传 PPT 结构

建议准备两套 PPT：

- 8-10 页短版：给路演、合作沟通、短演示。
- 18-25 页长版：给学校、创客空间、投资/合作方、内部培训。

短版 PPT 建议：

| 页 | 标题 | 核心内容 | 需要素材 |
|---|---|---|---|
| 1 | 让创客项目真正被体验 | 产品名、口号、动态真机画面、浏览器工作台 | 动态 Hero：电脑 + 多块小屏幕设备运行 App |
| 2 | 现在的问题 | 作品分发后，别人要看文章、装环境、配依赖、烧录、上传，入门用户很容易放弃 | “复刻门槛漏斗”示意图 |
| 3 | 我们解决什么 | 先让用户看到效果，再引导学习、修改、部署和发布 | 浏览器步骤动图 |
| 4 | 产品怎么用 | 描述想法 -> 预览 -> 修改 -> 打包 -> 真机 -> 发布准备 | 动态流程图，少放代码 |
| 5 | MicroPythonOS 生态基础 | 图形化 OS、App、MPK、uPyStore、真机/桌面/Web | Launcher、App Store、MPK、真机运行短片 |
| 6 | 当前设备覆盖 | 已真实适配 15 个物理板卡，另有 Linux/Web 目标；物料必须插入实物图和运行视频 | 15 板卡照片墙 + 3-5 段真机视频 |
| 7 | Tuya/涂鸦方向 | 3 款带屏幕涂鸦板卡作为重点规划适配方向，先做概念演示，不写已适配 | 标注“概念演示/规划适配”的合成 App 运行画面 |
| 8 | 应用场景 | 创意原型制作、STEM 课堂、小批量设备 App 分发、多设备演示管理 | 课堂、创客空间、小批量设备桌面 |
| 9 | 用户真实反馈 | 学生/老师/创客第一次用、修改、部署、展示作品 | 用户测评视频拼贴、分屏剪辑 |
| 10 | Call to action | 试用链接、GitHub、安装器、uPyStore、合作方式 | 二维码 + 真机作品墙 |

长版 PPT 可增加：

- 为什么创客项目难以从小众传播到大众。
- MicroPythonOS 是什么，以及它为什么适合小屏幕 App 分发。
- MicroPythonOS App 和普通 MicroPython 脚本的区别，但只讲用户价值：有图形界面、能打包、能安装、能发布。
- 当前真实适配 15 个物理板卡和 Web/desktop target。
- Tuya/涂鸦 3 款带屏幕板卡规划适配的商业意义：更接近量产硬件和普及型产品形态。
- `mpos-ai-app/v1` 协议化长任务设计。
- 为什么必须 API 校验和 artifact manifest，但表达成“让用户少踩坑、让作品可复刻”。
- 为什么 Web preview 只是可选，不替代真机，但表达成“先体验，再验证”。
- 课堂项目案例：倒计时器、情绪投票器、传感器仪表盘、小游戏、校园活动打卡器。
- 小批量设备管理场景：同一批设备安装同一个 App、不同班级/活动分发不同 App、用 MPK 做版本流转。
- 作品评价标准：功能、交互、界面、真机表现、发布材料。
- 一次工作坊流程。
- 前后端/Runner 技术架构放到后半段，不要在开头讲。
- 与普通 AI 代码助手、普通 IDE、Blockly 类工具的区别。

### 25.6 PPT 每页视觉要求

PPT 不要做成纯文字说明。每页最多一个核心观点，必须配一张真实产品或设备相关图片。

推荐视觉素材：

- 开头背景不要用静态纯色或静态产品图，尽量用动态画面：多块带屏设备同时运行 App、浏览器生成过程快放、学生现场操作、模拟器画面流动。
- 浏览器工作台首页截图：prompt、语言、App 元信息、目标选择。
- 运行中时间线截图：analysis/generation/test/package/deploy/publish。
- 权限确认截图：写文件、运行脚本、连接设备、部署到设备。
- 生成代码截图：`MANIFEST.JSON` 和 `assets/main.py`，但不要大段代码。
- 桌面预览截图：MicroPythonOS App 在 Linux SDL 中运行。
- Web preview 截图：带“可选预览，不等于真机验证”的提示。
- 设备部署截图：设备面板、串口扫描、部署结果。
- 真机实拍：ESP32-S3 小屏幕运行生成的 App。
- uPyStore 发布检查截图：MPK、publisher、截图、release notes。
- MicroPythonOS launcher/App Store 截图。
- 当前真实适配板卡合影：Freenove、LilyGO、M5Stack、Waveshare、SQUiXL、UniHiker K10 等。
- 当前真实适配 15 个物理板卡的照片墙，PPT 中需要明确写出“当前真实适配 15 个物理板卡 + Linux/Web target”。
- Tuya/涂鸦 3 款带屏幕板卡的规划适配页：需要找实物图或产品图，并制作一个带 MicroPythonOS App 的概念运行视频。画面必须标注“规划适配 / 概念演示”，不能伪装成真实已适配。
- 学生/创客使用场景照片：电脑、USB 线、开发板、课堂桌面。
- 结果作品墙：多个学生作品卡片。
- 多 App 分屏画面：4-9 个 App 同时运行，用来体现“应用生态”和“作品可以分发”。

截图规范：

- 浏览器截图使用 16:9，推荐 1920x1080。
- 真机实拍横屏 16:9 和竖屏 9:16 都要拍。
- 图片格式优先 PNG/JPEG/WebP。
- 代码截图只保留关键 10-20 行，避免把页面变成代码讲解。
- 所有截图中不能露出 API key、token、真实个人路径、真实串口序列号、私有仓库地址或未发布账号信息。
- 如果显示日志，只保留可分享摘要，不显示完整服务器路径。

### 25.7 视频类型规划

建议做 5 类视频，每类服务不同场景：

| 类型 | 时长 | 目标 | 发布位置 |
|---|---:|---|---|
| 15 秒短视频 | 15s | 让人立刻理解“说一句话生成 App” | 抖音、B 站动态、朋友圈、官网 Hero |
| 60 秒产品介绍 | 45-75s | 给新用户快速理解产品价值 | 官网、GitHub README、PPT 开场 |
| 3 分钟演示 | 2-4min | 完整展示从 prompt 到预览/MPK | B 站、YouTube、产品文档 |
| 8-12 分钟教程 | 8-12min | 让老师/创客照着做 | 教学文档、课程、工作坊 |
| 使用实录合集 | 2-5min | 展示真实用户/学生做作品 | 宣传页、社群、路演 |

视频总原则：

- 开头先讲背景和具体问题，不要一上来讲架构、API、Runner、协议。
- 多用动态画面，不要长时间停在静态 PPT 或静态截图。
- 真机运行画面优先，其次是桌面模拟器动态画面，再其次才是 Web preview。
- 每个视频至少出现一次“别人不用只看文章，而是能跟着浏览器步骤跑起来”的表达。
- 每个正式宣传视频至少出现一次“当前真实适配 15 个物理板卡”的口径，并插入实物图或真机运行视频。
- 如果出现 Tuya/涂鸦 3 款带屏幕板卡，必须标注为规划适配或概念演示；可以用 P 出来的 App 运行画面占位，但不能口播“已经真实适配”。
- 尽量做多 App 分屏视频：同一屏里展示倒计时器、传感器仪表盘、小游戏、打卡器等多个 App 同时运行，强调这不是单个 demo，而是一套 App 生态入口。
- 多做用户测评视频：学生、老师、创客的真实使用反应，比单纯讲功能更有说服力。

### 25.8 15 秒短视频脚本

目标：一眼看懂，不讲技术细节。

镜头脚本：

1. 0-3s：快速切换几个“复刻失败”的画面：长教程、依赖安装、串口连接、用户皱眉。
2. 3-5s：字幕：`有趣的创客项目，不能只停在文章里。`
3. 5-7s：电脑屏幕，用户输入“做一个课堂倒计时器 App”。
4. 7-10s：预览和真机画面快速切换，同一个 App 跑起来。
5. 10-13s：多个 App 分屏：倒计时器、传感器仪表盘、小游戏、打卡器。
6. 13-15s：Logo/标题：`先看到效果，再深入学习。`

屏幕文字：

```text
不用先啃长教程
先在浏览器里跑起来
再装到真实设备
让创客作品更容易被复刻
```

旁白：

```text
把创客项目从“看得懂的人才能复刻”，变成“感兴趣的人也能先体验起来”。
```

### 25.9 60 秒产品介绍视频脚本

结构：

1. 背景：很多创客项目分发出去后，别人复刻前要先看教程、装环境、配依赖、烧录和上传。
2. 问题：对入门用户、学生和老师来说，这些步骤会在看到效果前消耗兴趣。
3. 方案：打开浏览器，用自然语言描述 App，系统把流程变成可跟随的步骤。
4. 结果：先预览、再修改、再打包和部署到真实设备。
5. 价值：创意原型更快出现，小批量设备更容易分发 App，课堂和创客项目更容易传播。

旁白草稿：

```text
很多创客项目看起来很有趣，但别人真正想复刻时，经常要先看长篇教程、安装环境、配置依赖、下载代码、连接设备、烧录系统、上传文件。还没看到效果，兴趣就被消耗掉了。MicroPythonOS AI App Builder 想解决的就是这个问题：用户只要在浏览器里描述想做什么，比如课堂倒计时器、传感器仪表盘或小游戏，系统就把想法变成可以预览、修改、打包和部署到真实设备的 App。它不是让用户跳过学习，而是先给用户一个可触摸、可展示、可分享的结果。当前 MicroPythonOS 已真实适配 15 个物理板卡，并支持桌面模拟和 Web 预览。它让创客作品从“看文章的人才可能复刻”，变成“感兴趣的人也能先体验起来”。
```

必须出现的画面：

- 输入 prompt。
- 复刻门槛背景画面：长教程、环境安装、接线、烧录。
- 阶段时间线，但只停留 2-3 秒，不做技术长讲。
- 模拟器动态运行画面。
- 真机运行画面。
- 15 个真实适配板卡照片墙或快闪。
- 多个 App 分屏运行画面。
- 发布检查页。

### 25.10 3 分钟完整演示视频脚本

建议演示项目：`课堂倒计时器`。原因是它不依赖复杂外设，适合 Web/桌面/真机同时展示，老师和学生都能理解。

演示 Prompt：

```text
生成一个 MicroPythonOS 课堂倒计时器 App，支持设置 5、10、15 分钟，显示剩余时间，有开始、暂停、重置按钮，时间结束时显示醒目的提示。
```

分镜：

1. 0:00-0:25：背景问题。展示一个创客项目传播出去后，别人要看教程、装环境、烧录、上传，强调“很多人还没看到效果就放弃”。
2. 0:25-0:45：展示解决方案。打开浏览器工作台，输入课堂倒计时器 prompt。
3. 0:45-1:05：展示系统自动生成和预览，时间线只作为辅助，不长讲技术。
4. 1:05-1:25：展示模拟器动态运行，用户点击开始、暂停、重置。
5. 1:25-1:50：展示真机运行同一个 App，镜头要比静态截图更长，让观众看到它确实在动。
6. 1:50-2:10：展示连续修改，例如“按钮大一点，结束时变红”，再切回模拟器/真机动态画面。
7. 2:10-2:30：展示多个 App 分屏运行，体现应用生态和作品分发，不要只展示单一 Demo。
8. 2:30-2:45：展示当前真实适配 15 个物理板卡的照片墙和 3-5 个真机运行片段。
9. 2:45-3:00：展示发布检查页和总结：作品不只是看文章，而是可以被别人体验、复刻和继续修改。

屏幕录制要点：

- 鼠标移动慢一点，不要频繁切窗口。
- 每个关键结果停 2-3 秒。
- 如果模型生成失败，不要剪掉全部失败。可以保留一段“把错误交给 AI 修复”的画面，这反而体现真实流程。
- 真机镜头要能看清屏幕，不要过曝。

### 25.11 8-12 分钟教程视频脚本

目标：让老师或创客能照着复现。

章节：

1. 准备环境：打开浏览器、后端、前端、确认端口 `8000`/`5174`。
2. 认识界面：prompt、元信息、目标、时间线、artifact、设备、发布。
3. 第一个 App：课堂倒计时器或四则运算计算器。
4. 预览：desktop smoke 和 Web preview 的区别。
5. 打包：`.mpk`、`MANIFEST.JSON`、`publisher`、`_rN`。
6. 真机：MicroPythonOS 安装器、设备连接、部署。
7. 连续修改：让 AI 改布局、改颜色、加设置页。
8. 错误修复：展示一个可控错误，如缺字段、API 不存在、截图格式不支持。
9. 发布准备：截图、说明、release notes、uPyStore developer。
10. 课堂任务：学生如何提交作品包和演示视频。

教程中必须明确：

- Web preview 是可选，不是真机验证。
- 未安装 MicroPythonOS 的设备，要先去安装器。
- 生成失败时，把错误和日志给 AI 继续修。
- 不能要求 AI 修改 MicroPythonOS OS 层、LVGL、构建脚本来迁就 App。

### 25.12 使用实录怎么拍

使用实录比完美宣传片更重要，尤其面向创客入门和 STEM。建议拍 3 类人：

- 第一次接触 MicroPythonOS 的学生。
- 有 Arduino/MicroPython 基础但没做过 LVGL App 的创客。
- 老师或社团组织者。

每个实录建议拍 20-40 分钟素材，剪成 2-5 分钟。

必须拍到的片段：

- 用户是因为什么被吸引：看到别人文章、视频、课堂作品或开源项目后，想自己试一下。
- 用户说出自己想做什么。
- 用户输入 prompt。
- 用户看到系统拆阶段执行。
- 用户第一次看到预览。
- 用户修改需求，例如“按钮大一点”“加一个深色模式”。
- 用户遇到错误并点击重试/修复。
- 用户把 App 装到真机。
- 用户展示作品并用一句话解释用途。
- 用户把 `.mpk` 或项目链接分享给别人，说明这个作品不是只能在作者电脑上跑。
- 用户基于同一个 session 连续改第二版、第三版，体现“边看效果边改”。

采访问题：

- 你一开始想做什么作品？
- 你是先在哪里看到类似创客项目的：文章、视频、课堂还是 GitHub？
- 如果没有这个工具，你觉得最难的步骤是什么？
- 如果只给你一篇教程和一堆命令，你还会不会继续做下去？
- 哪一步让你觉得“真的跑起来了”？
- 你想继续加什么功能？
- 如果用于课堂，你希望学生最后提交什么？
- 如果有一批同样的设备，给每台设备装同一个 App 或不同 App，你觉得哪里最省事？

拍摄注意：

- 不要要求用户背稿。
- 保留真实停顿和试错，但剪掉长时间等待。
- 拍手部、电脑屏幕、开发板屏幕和用户反应。
- 如果用户是未成年人，必须取得监护和学校授权后再公开发布。
- 不展示账号、token、私有仓库、个人聊天记录。
- 用剪映/CapCut 做一版“用户测评合集”：保留真实反应，重点剪出第一次看到预览、第一次真机跑起来、第一次成功分享这三个瞬间。
- 每个实录建议同时导出横屏完整片和竖屏高光片。横屏用于路演和 README，竖屏用于短视频平台。

### 25.13 需要准备的图片素材清单

产品截图：

- 首页/Workbench 空状态。
- Demo mode 示例入口和一键填充 prompt。
- Prompt 输入后状态。
- App 元信息填写。
- 阶段时间线 running。
- 阶段完成状态。
- 权限确认弹窗。
- 错误面板。
- “复制给 AI 修复”或 retry 入口。
- Artifact Browser。
- 生成的 `MANIFEST.JSON`。
- 生成的 `assets/main.py`。
- Desktop preview 截图。
- Web preview 截图。
- 多 App 分屏运行截图：倒计时器、传感器仪表盘、小游戏、打卡器同时出现。
- 设备面板：未连接、已连接、等待安装、部署完成。
- uPyStore 发布检查页。
- 历史 session/revision 页面。

MicroPythonOS 截图：

- Launcher 主屏。
- App Store/uPyStore 相关界面。
- Settings/WiFi 页面。
- File Manager。
- HowTo/About 页面。
- 一个内置游戏或图形 App。
- 一个生成的课堂 App。

硬件照片：

- 当前 15 个真实适配物理板卡合影。
- 电脑通过 USB 连接 ESP32-S3 小屏幕设备。
- 真机运行生成 App 的近景。
- 3-5 段不同真实板卡运行生成 App 的对比视频。
- 多设备同框：几块设备分别运行不同 App，体现小批量 App 分发和多设备展示。
- Tuya/涂鸦 3 款带屏幕板卡的实物图或产品图。
- Tuya/涂鸦 3 款带屏幕板卡的概念合成视频：把 App 运行画面合成到屏幕上，必须标注“规划适配 / 概念演示 / 非真实适配录制”。
- 学生桌面：电脑、设备、USB、笔记。
- 教室/工作坊环境。
- 老师投屏演示。
- 多个学生作品一起展示。

图形资产：

- 产品 Logo。
- MicroPythonOS Logo。
- 流程图：prompt -> analysis -> API check -> generate -> preview -> package -> deploy -> publish。
- 架构图：frontend -> backend -> runner -> MicroPythonOS -> device/uPyStore。
- 状态机图：session/checkpoint/revision/retry/cancel。
- 对比图：传统流程 vs AI App Builder。
- 传播路径图：从“文章/代码仓库/演示视频”到“浏览器可体验流程”再到“真机运行/MPK 分发/uPyStore”。
- 小批量设备 App 分发图：同一批设备安装同一个 App、不同班级分发不同 App、版本升级流转。
- 从小众教程到大众体验的漏斗图：兴趣 -> 看到效果 -> 修改 -> 真机 -> 分享。
- 支持板卡图标或照片卡片。
- 二维码：GitHub repo、安装器、Web preview、uPyStore developer。

### 25.14 视频录制准备

电脑录屏：

- 分辨率：1920x1080，16:9。
- 帧率：30fps 足够；演示 UI 动效可用 60fps。
- 浏览器缩放：100% 或 110%，保证字能看清。
- 字体大小：终端和代码编辑器至少 16px。
- 录制前清理桌面、关闭通知、关闭无关标签页。
- 浏览器书签栏可隐藏。
- 使用测试账号和测试 publisher。
- 清空或准备好固定 session，避免历史记录混乱。

真机拍摄：

- 相机或手机固定在三脚架上。
- 避免屏幕反光，必要时降低设备屏幕亮度。
- 拍 3 个角度：
  - 正面特写：看清设备屏幕。
  - 侧面手部：看用户按按钮/触摸屏。
  - 环境广角：电脑和设备同框。
- 如果设备刷新频闪，调整快门到 1/50 或 1/60。
- 每个关键动作多拍 2 次，方便剪辑。
- 至少拍 3-5 个真实适配板卡的 App 运行短片，避免宣传只依赖模拟器。
- 拍一组多设备动态镜头：多个设备同时亮屏、不同 App 同时运行、用户在浏览器里切换部署目标。
- Tuya/涂鸦 3 款带屏幕板卡如果还没有完成真实适配，只能拍产品实物和概念合成画面，画面角标必须写“规划适配 / 概念演示”。

音频：

- 旁白建议后期录，不要依赖现场同期声。
- 使用领夹麦或 USB 麦克风。
- 现场实录要单独录环境声，但最终可压低。
- 每段视频开头先安静 3 秒，方便降噪。

推荐录制工具：

- 屏幕录制：OBS Studio。
- 剪辑：剪映/CapCut 优先做用户测评合集和短视频，DaVinci Resolve、Final Cut Pro、Premiere 适合长片和高质量路演视频。
- 音频清理：Audacity。
- GIF/短动图：ScreenToGif 或 ffmpeg。
- PPT：PowerPoint、Keynote、Google Slides、Canva、Figma。

### 25.15 必录 Demo 片段清单

每个片段都要单独保存原始素材，文件名建议带日期、场景和 take 编号。

| 片段 | 画面 | 用途 |
|---|---|---|
| `01_prompt_input` | 输入自然语言需求 | 所有宣传视频开头 |
| `02_metadata` | 填 fullname/publisher/version | 说明 App 不是临时代码 |
| `03_timeline` | 阶段时间线运行 | 展示长任务可见 |
| `04_permission` | 权限确认 | 展示可控和安全 |
| `05_api_check` | API 校验结果 | 展示不是盲目生成 |
| `06_code_artifacts` | `MANIFEST.JSON`、`main.py`、artifact | 展示真实产物 |
| `07_desktop_preview` | 桌面烟测/截图 | 展示快速验证 |
| `08_web_preview` | Web preview | 展示浏览器体验，同时提示限制 |
| `09_package_mpk` | `.mpk` 生成 | 展示可发布包 |
| `10_install_os` | 打开 MicroPythonOS 安装器 | 展示真机准备 |
| `11_device_scan` | 串口/设备能力 | 展示真实硬件路径 |
| `12_deploy_device` | 部署成功和日志 | 展示从浏览器到设备 |
| `13_device_running` | 真机运行 App | 核心证明镜头 |
| `14_iterate_change` | 连续修改需求并看 diff | 展示持续修改 |
| `15_error_retry` | 失败后复制错误/重试 | 展示真实工程能力 |
| `16_publish_check` | uPyStore checklist | 展示发布闭环 |
| `17_student_demo` | 用户介绍自己的作品 | 使用实录 |
| `18_multi_app_split` | 4-9 个 App 分屏同时运行 | 展示应用生态和批量作品 |
| `19_multi_device_wall` | 多块真实适配板卡同时运行 | 展示当前 15 个物理板卡覆盖能力 |
| `20_tuya_concept` | 涂鸦带屏板卡概念合成 App 运行画面 | 展示规划方向，必须标注非真实适配 |
| `21_user_review_cut` | 学生/老师/创客测评高光剪辑 | 展示真实反馈和入门价值 |

### 25.16 Demo App 选题

优先选择易懂、低风险、能在 Web/桌面/真机都展示的项目。

入门级：

- 四则运算计算器。
- 课堂倒计时器。
- 番茄钟。
- 每日任务打卡。
- 抽签/随机点名器。
- 情绪投票器。

STEM/科创级：

- 传感器数据仪表盘。
- 校园空气质量展示面板。
- IMU 姿态可视化。
- 蓝牙设备扫描面板。
- 音量/电量/温度状态面板。
- 小型数据记录器。

展示性强：

- 记忆翻牌小游戏。
- Connect 4/井字棋。
- 画板。
- 音乐播放器界面。
- 图像查看器。
- 课程积分榜。

首批宣传推荐 3 个固定 Demo：

- `课堂倒计时器`：老师和学生都秒懂。
- `传感器仪表盘`：体现硬件和 STEM。
- `记忆小游戏`：体现 UI 和创意。

多 App 分屏推荐组合：

- 左上：`课堂倒计时器`，体现课堂场景。
- 右上：`传感器仪表盘`，体现 STEM 和硬件数据。
- 左下：`记忆小游戏`，体现交互和趣味。
- 右下：`校园提醒面板` 或 `每日任务打卡`，体现实际使用。

小批量设备管理演示组合：

- 同一个倒计时器 App 同时部署到 3 块真实适配板卡，体现活动现场统一发放。
- 不同班级使用不同主题 App，体现“同一套设备，不同活动内容”。
- 同一个 App 从 `_r1.mpk` 升级到 `_r2.mpk`，体现版本分发和可持续维护。

### 25.17 课堂/工作坊方案

45 分钟体验课：

1. 5 分钟：介绍 MicroPythonOS 和 AI App Builder。
2. 5 分钟：老师演示一句话生成倒计时器。
3. 10 分钟：学生输入自己的 App 想法。
4. 10 分钟：生成、预览、看 artifact。
5. 10 分钟：连续修改一次。
6. 5 分钟：作品展示和提交截图。

90 分钟工作坊：

1. 10 分钟：设备和系统介绍。
2. 10 分钟：MicroPythonOS 安装或确认。
3. 15 分钟：第一个 App 生成。
4. 15 分钟：预览和真机部署。
5. 15 分钟：连续修改和错误修复。
6. 15 分钟：打包和发布材料。
7. 10 分钟：学生展示。

半天科创营：

- 上午：理解 MicroPythonOS、自然语言生成、基础 UI。
- 中午：分组确定作品主题。
- 下午：实现、真机部署、录制展示视频、准备发布材料。

学生提交物：

- App 名称和一句话说明。
- 截图 PNG/JPEG/WebP。
- `.mpk` 文件。
- 30-60 秒演示视频。
- 生成过程中的一次错误修复记录。
- 如果发布，附 `publish_result.json` 或发布检查截图。

评价标准：

- 功能是否完整。
- UI 是否清楚。
- 是否通过预览或真机验证。
- 是否有连续修改痕迹。
- 是否能解释自己的设计选择。
- 发布材料是否齐全。

### 25.18 官网/README 宣传素材结构

GitHub README 或官网首屏建议包含：

- 一句话定位。
- 30 秒 GIF：prompt -> preview -> device。
- 三个按钮：
  - `Try locally`
  - `Install MicroPythonOS`
  - `Publish to uPyStore`
- 关键流程图。
- 3 个 Demo App 卡片。
- 设备支持说明。
- Web preview 限制说明。
- 安全边界：权限确认、artifact、不能改 OS。
- 教学场景：45 分钟体验课、90 分钟工作坊。

README 中不要只放架构。面向创客/STEM 的 README 第一屏要让非工程师也看懂：

```text
1. 输入想法
2. 看到 App
3. 装到设备
4. 分享作品
```

### 25.19 前后端为宣传演示需要补齐的能力

为了保证 PPT 和视频能拍得顺，前端需要优先补齐：

- Demo mode：固定示例 prompt，一键填充。
- Showcase mode：4-9 个 App 分屏展示，用于录制“这不是单个 demo，而是一套 App 生态入口”。
- Board support 展示组件：清楚区分 `已真实适配`、`规划适配`、`概念演示`，并显示当前 15 个真实适配物理板卡。
- Tuya/涂鸦规划适配展示组件：只作为重点方向和概念演示出现，页面文案不能写成已适配。
- Timeline 截图友好：阶段名称清晰，状态颜色稳定。
- Artifact Browser 截图友好：角色、文件名、阶段、下载按钮清楚。
- PublishPanel 截图友好：MPK、publisher、截图、release notes checklist。
- DevicePanel 截图友好：安装器链接、扫描状态、部署状态分明。
- ErrorPanel 截图友好：错误码、可复制上下文、retry 按钮。
- Web preview 限制提示常驻可见。
- 一键导出宣传素材包：截图、MPK、manifest、publish_result、session_summary。
- 一键导出用户测评素材包：脱敏对话、关键截图、生成前后对比、用户反馈文字，方便剪映/CapCut 快速剪合集。

后端需要优先补齐：

- 可重复运行的 demo seed，避免每次演示结果漂移太大。
- 固定 demo session 导入/恢复能力。
- 生成 demo artifact bundle。
- 生成脱敏 session log。
- 生成发布检查摘要。
- 错误注入开关，用于演示“报错 -> 回传 AI -> 修复”。
- 本地无设备时返回真实 blocked 状态和安装器链接，而不是假成功。
- Demo timeline 模式必须和真实运行记录分开：mock/staged demo 只能用于宣传演示，不能混进真实 result JSON。
- 多设备 demo state：记录多个设备的连接、部署、运行截图和 App 版本，支撑小批量设备演示。
- 板卡支持状态字段建议统一为 `supported`、`planned`、`concept_demo`，前端按状态显示不同标签。
- 每个导出素材包都要有 manifest，记录素材来源、真实/模拟/概念类型、是否可公开。

Runner/skill 需要配合：

- Demo prompt 的稳定输出模板。
- 至少准备 4 个稳定 demo prompt：课堂倒计时器、传感器仪表盘、记忆小游戏、校园提醒/任务打卡，用于分屏 showcase。
- 生成前 API 校验结果可视化。
- 常见错误的结构化解释。
- 连续修改输出 diff。
- package/deploy/publish 三个阶段的状态足够清楚。
- 如果 prompt 要求 Tuya/涂鸦板卡，而当前未真实适配，Runner/skill 必须返回明确 warning：只能做概念演示或选择已支持板卡。
- Web preview 结果必须和 desktop smoke、真机部署分开记录，避免用户误以为浏览器预览等于硬件验证。

### 25.20 素材命名和归档

建议在浏览器项目仓库中建立素材目录，但不要提交大体积原始视频到 Git。Git 中只放脚本、清单、压缩图和最终导出小文件。

推荐目录：

```text
docs/marketing/
  README.md
  pitch-deck/
    short-deck.md
    long-deck.md
    assets/
  video/
    scripts/
    shot-list.md
    storyboard.md
    release-checklist.md
  screenshots/
    product/
    micropythonos/
    device/
  thumbnails/
  transcripts/
```

大文件存放：

- 原始录屏、相机素材、工程文件放网盘、对象存储或 GitHub Release，不要直接提交 Git。
- 每个视频导出一份 1080p MP4 和一份压缩版。
- 每张对外图片保留原图和脱敏后版本。
- 每个公开素材记录来源、拍摄日期、授权状态和可用范围。

文件命名：

```text
2026-07-24_prompt_input_class_timer_take01.mp4
2026-07-24_device_running_class_timer_take02.mp4
2026-07-24_publish_check_class_timer.png
2026-07-24_student_demo_group_a_release-approved.mp4
```

### 25.21 发布前检查清单

PPT 发布前：

- 每页只讲一个重点。
- 每页都有产品/设备/流程相关视觉。
- 没有夸大 Web preview 或自动发布能力。
- 板卡口径准确：当前真实适配是 15 个物理板卡；Tuya/涂鸦 3 款带屏幕板卡只能写“规划适配 / 概念演示”，不能写“已适配”。
- 前 3 页先讲背景、痛点和用户价值，再讲技术流程。
- 至少有一页说明“先看到效果，再深入学习”，避免把产品讲成普通 IDE 或普通 AI 代码生成器。
- 必须插入真实设备照片或真机运行视频截图，不能全是静态 UI 和架构图。
- 所有链接和二维码可打开。
- 没有 token、隐私、个人路径、未授权学生照片。
- 中英文术语统一：MicroPythonOS、uPyStore、MPK、Web preview、desktop smoke。

视频发布前：

- 开头 10 秒必须出现背景问题或动态设备画面，不能用长时间静态 PPT 开场。
- 画面中没有密钥、私有路径、真实账号敏感信息。
- 真机运行画面清楚。
- 旁白没有说“必定成功”“支持所有板卡”“自动发布”等不准确表述。
- 如果出现 Tuya/涂鸦概念合成画面，字幕和画面角标必须写清楚“规划适配 / 概念演示 / 非真实适配录制”。
- 至少出现一次多 App 分屏或多设备同框动态画面。
- 用户测评合集必须保留真实反馈，不要剪成像广告口播；可以用剪映/CapCut 做节奏，但不能伪造评价。
- 字幕中保留关键术语。
- 片尾有 GitHub、安装器、文档和 uPyStore 链接。
- 使用实录已取得授权。
- 如果展示学生，确认学校和监护授权。

Demo 发布前：

- 生成出的 App 能重新打开。
- `.mpk` 文件名是 `<fullname>_rN.mpk`。
- `MANIFEST.JSON` 有 `publisher`。
- 截图是 PNG/JPEG/WebP。
- `publish_result.json` 没有 blocked 项，或者 blocked 原因被清楚说明。
- Web preview 和真机部署状态分开展示。
- 如果演示小批量设备分发，至少记录 App 版本、目标设备、部署结果和回滚/重试说明。
- 如果演示 session/resume/连续修改，保留 revision 记录和最终 artifact manifest，方便别人复刻。

## 26. Blockless-Make-APP 功能补齐计划

后续浏览器产品统一使用新产品名：

```text
Blockless-Make-APP
```

对外表达建议：

```text
Blockless-Make-APP 是面向创客入门、科创教育和 STEM 课堂的 AI App 生成与分发平台。用户在浏览器里描述想法，系统生成 MicroPythonOS App，支持预览、修改、打包、真机部署、发布到 uPyStore，并提供没有设备也能体验的仿真项目库。
```

### 26.1 产品命名和界面口径

需要统一修改：

- 浏览器标题、首页标题、README、PPT、视频字幕统一写 `Blockless-Make-APP`。
- 原 `MicroPythonOS AI App Builder` 可以作为技术说明或副标题出现，不再作为主品牌。
- 首屏不要先讲“AI 代码生成”，而是讲“说出想法 -> 浏览器预览 -> 真机运行 -> 发布分享”。
- 中文口号建议：`让创客 App 先跑起来，再传播出去。`
- 英文口号建议：`Make, preview, deploy, and share MicroPythonOS apps from the browser.`

### 26.2 App 上传 uPyStore 功能

目标：用户完成 App 后，可以在产品内看到清楚的发布准备流程，并被引导上传到 `upystore.io`。

第一阶段建议做“发布准备 + 手工上传引导”：

- 校验 `MANIFEST.JSON` 必填字段，尤其是 `publisher`、`version`、`fullname`、`name`、`description`。
- 校验 MPK 文件命名必须是 `<fullname>_rN.mpk`，例如 `com.example.timer_r1.mpk`。
- 校验截图格式必须是 PNG/JPEG/WebP。
- 生成 `publish_result.json`，列出可发布项、blocked 项、warning 项。
- 生成 uPyStore 上传材料包：MPK、图标、截图、README/description、release notes。
- 在 UI 中提供 `打开 uPyStore developer` 按钮，并展示“下一步手工上传”说明。

第二阶段再考虑真正接入上传接口：

- 如果 uPyStore 提供稳定 API，再做 OAuth/API token、自动上传、版本更新、失败重试。
- 没有正式 API 前，不要在界面上写“自动发布成功”，只能写“发布材料已准备好”或“等待用户上传”。

### 26.3 简易充值和点数功能

目标：线下活动和早期灰度可以快速给用户开通点数，降低试用阻力。

建议实现方式：

- 前端增加 `充值` 按钮。
- 用户点击后弹出充值面板，展示个人微信二维码、添加说明和账户名称。
- 面板提示用户添加微信后发送：`账户名称 + 充值金额 + 用途`。
- 后台增加管理员加点入口：管理员确认收款后，按账户名人工加点。
- 用户侧显示点数余额、消费记录、充值记录和管理员备注。

必须注意：

- 个人微信充值只适合早期内测、线下活动或人工灰度，不建议作为长期正式支付方案。
- 不能做“用户说已转款就自动加点”。必须由管理员确认收款后再加点。
- 每次加点都要记录操作人、时间、账户、金额、点数、备注，方便对账。
- 界面需要说明退款、异常处理和联系方式。
- 后续正式化建议接入微信支付/支付宝/Stripe 等合规支付渠道。

### 26.4 板卡厂家 Logo 和型号展示

目标：让用户一眼知道当前能用哪些设备，也让 PPT 和视频有可信的硬件生态展示。

前端需要展示：

- 当前真实适配板卡数量：`15 个物理板卡`。
- Linux/macOS desktop target。
- WebAssembly Web target。
- 每个板卡卡片包含：厂家/品牌、型号、芯片/平台、屏幕信息、支持状态、推荐用途、是否适合新手。
- 支持状态必须清楚区分：`已真实适配`、`规划适配`、`概念演示`。

当前真实适配板卡厂家/品牌包括：

- Freenove
- Fri3d Camp
- LilyGO
- M5Stack
- Makerfabs
- Hardkernel
- SQUiXL
- DFRobot
- unPhone
- Waveshare

当前真实适配型号包括：

- Freenove ESP32-S3 Display
- Fri3d Camp 2024 Badge
- Fri3d Camp 2026 Badge
- LilyGO T4 V1.3
- LilyGO T-Display S3
- LilyGO T-HMI
- LilyGO T-Watch S3 Plus
- M5Stack Core2
- M5Stack Fire
- Makerfabs MaTouch ESP32-S3 SPI IPS 2.8" with Camera OV3660
- Hardkernel ODROID-GO
- SQUiXL
- DFRobot UniHiker K10
- unPhone 9
- Waveshare ESP32-S3-Touch-LCD-2

Tuya/涂鸦智能相关展示规则：

- 可以放 Tuya/涂鸦智能 Logo 和 3 款带屏幕板卡的产品图，用于体现规划方向和潜在生态合作。
- 页面和视频必须标注：`规划适配`、`概念演示` 或 `重点适配方向`。
- 不能把 Tuya/涂鸦板卡写成当前已真实适配。
- 如果制作“P 出来的 APP 运行视频”，必须在画面角标和说明文字中写清楚：`概念演示，非真实适配录制`。
- 正式对外物料使用第三方 Logo 前，需要确认商标、授权和品牌使用规则。

### 26.5 仿真项目库功能

新增一个“发布仿真项目库”能力，让别人没有真实设备也能先体验作品。

用户完成 App 后，可以选择发布到两个地方：

- uPyStore：用于真实 MicroPythonOS App 分发。
- Blockless-Make-APP 仿真项目库：用于浏览器内体验、展示、复刻和继续修改。

仿真项目库需要支持：

- 项目标题、作者、简介、标签、适用场景。
- App 截图、短视频、Web preview 或 desktop preview 记录。
- 源码 artifact manifest、MPK、`MANIFEST.JSON`、版本号。
- `Run in Browser`：没有设备的用户也能先打开仿真。
- `Deploy to Device`：有设备的用户可以跟着流程安装 MicroPythonOS 并部署。
- `Remix / Continue Editing`：把别人的项目作为起点继续改。
- `Publish to uPyStore`：从仿真项目跳转到发布检查流程。
- 项目版本历史：`r1`、`r2`、`r3`。
- 举报/下架/审核机制，避免上传无效项目、侵权素材或不适合公开的内容。

推荐项目库首页分区：

- 新手可玩：倒计时器、打卡器、小游戏。
- STEM 课堂：传感器仪表盘、空气质量面板、数据记录器。
- 设备展示：适合不同板卡屏幕尺寸的 App。
- 热门复刻：被最多人运行、部署、Remix 的项目。
- 活动专区：`adventurex2026`、工作坊、学校社团作品。

需要强调的用户价值：

- 没有设备的人也能先体验作品，降低第一次尝试门槛。
- 有设备的人可以从仿真项目一键进入部署流程。
- 老师可以提前准备课堂项目库，学生直接选择一个主题开始改。
- 创客可以把作品从“文章和代码仓库”升级成“可运行、可复刻、可分发”的项目页面。

## 27. Blockless-Make-APP 推广执行计划

本章用于今晚准备和明天线下拉新。目标不是只拍一条宣传片，而是形成一套可复用的活动流程：现场让用户做出 App、装到设备、上传 uPyStore、发布小红书内容，再把真实体验反哺到产品和宣传素材中。

### 27.1 明天线下体验流程

现场至少两个人配合：

- 引导员：负责带用户操作，从描述想法到生成、修改、打包、安装到设备。
- 拍摄员：负责记录用户、电脑、设备和环境，确保有可剪辑素材。

建议现场流程：

1. 询问用户想做什么小屏幕 App，例如倒计时器、小游戏、打卡器、仪表盘。
2. 引导用户在 Blockless-Make-APP 里输入自然语言需求。
3. 展示生成过程和预览结果。
4. 让用户提出一次修改，例如改颜色、改按钮、加提示文案。
5. 打包 MPK。
6. 安装到本地真实设备中，让用户亲手看到设备跑起来。
7. 帮助用户准备 uPyStore 上传材料，并引导上传到 `upystore.io`。
8. 引导用户拍自己的作品短视频，发布小红书。
9. 收集用户一句话反馈、问题、失败截图和改进建议。

必须拍到的镜头：

- 设备近景：屏幕清楚显示用户生成的 App。
- 操作远景：用户、电脑、设备和引导员同框。
- 人物反应：第一次看到预览、第一次真机跑起来、成功修改后的反应。
- 手部操作：输入 prompt、点击预览、连接设备、触摸设备屏幕。
- 多设备同框：提前准备好的 100 个 App 或多个 Demo 在不同设备/模拟器上运行。
- 结尾展示：用户拿着设备或指着设备介绍自己的 App。

拍摄要求：

- 不要只录屏，必须有真实人物和真实设备。
- 不要只拍静态背景，尽量让画面里有点击、滚动、计时、动画、设备切换。
- 每个用户至少拍一段横屏素材和一段竖屏素材。
- 用户同意公开后，再录制可发布口播；未授权素材只做内部复盘。

### 27.2 用户发布小红书引导

用户完成自己的 App 后，现场工作人员帮助用户完成三件事：

- 把 App 上传到 uPyStore 或准备好发布材料。
- 把 App 安装到设备中，确保现场能跑。
- 引导用户发布小红书，记录“我做了一个自己的小屏幕 App”的体验。

小红书发布建议：

- 标题要像真实用户体验，不要像硬广。
- 图片至少包含：设备运行近景、用户操作远景、浏览器生成截图。
- 视频最好 15-45 秒，前 3 秒直接展示设备跑起来。
- 文案模板可以提前给用户，但用户应按自己的真实体验修改。
- 必带关键词：`blockless`、`Blockless-Make-APP`。
- 建议话题：`#adventurex2026`、`#blockless`、`#创客`、`#STEM教育`、`#MicroPython`。

小红书文案模板示例：

```text
今天现场试了 Blockless-Make-APP，我只描述了一下想做的功能，就生成了一个能在小屏幕设备上跑的 App。

最有意思的是，不是只看教程或代码，而是真的能先预览，再装到设备里。我做的是【这里写自己的 App 名称】，后面还想继续加【这里写想加的功能】。

#adventurex2026 #blockless #BlocklessMakeAPP #创客 #STEM教育 #MicroPython
```

### 27.3 今晚准备 100 个 App

目标：明天现场不从零开始等模型生成，先准备足够多的可展示 App，让用户一进来就能看到“很多作品已经跑起来”。

执行方式：

- 用 DeepSeek 批量生成 100 个 MicroPythonOS App prompt 和项目。
- 生成后必须走基础校验：MANIFEST、API、desktop smoke、MPK 打包。
- 用本机脚本安装到本地设备中，和 Codex/Claude Code 明确说明“使用本机脚本安装到设备，不修改 MicroPythonOS OS 层代码”。
- 每个 App 保留截图、MPK、生成日志、失败原因和最终版本。
- 对失败 App 不要强行展示，放入问题池，后续让 AI 根据报错逐步修。

100 个 App 建议分类：

- 20 个课堂工具：倒计时、随机点名、积分榜、活动提醒。
- 20 个小游戏：记忆翻牌、井字棋、反应速度、猜数字。
- 20 个 STEM 展示：传感器仪表盘、温湿度、空气质量、电量状态。
- 20 个生活工具：番茄钟、打卡、提醒、计数器。
- 20 个视觉展示：画板、色卡、图片查看、动画小组件。

安装到设备时需要记录：

- App fullname。
- 版本号和 `_rN.mpk` 文件名。
- 目标设备型号。
- 部署方式和脚本路径。
- 是否真机启动成功。
- 真机照片或短视频路径。
- 如果失败，记录错误信息和下一步修复建议。

### 27.4 今晚准备 500 个小红书模板

目标：给现场用户提供灵感，不是制造虚假评价。

执行方式：

- 提前准备 500 个小红书文案模板，围绕 `blockless`、`Blockless-Make-APP`、`adventurex2026`。
- 模板按人群和场景分类：学生、老师、创客、家长、社团、工作坊、硬件爱好者。
- 每条模板都预留用户自己的 App 名称、功能、体验感受和照片位置。
- 现场发布前必须让用户自己确认和修改，不能代替用户伪造真实体验。
- 同一批模板不要机械重复发布，避免平台判定低质量或营销刷屏。

模板结构建议：

```text
标题：【一句真实感受】我用 Blockless-Make-APP 做了一个【App 名称】

正文：
今天在【活动/现场】试了一下 Blockless-Make-APP。
我原本想做【想法】，以前以为要先装环境、看教程、写很多代码，结果这次是先在浏览器里描述需求，然后看到预览，再装到小屏幕设备上。
我的 App 可以【功能 1】、【功能 2】。
最有成就感的是【用户自己的感受】。

图片/视频：
1. 设备运行近景
2. 用户操作远景
3. 浏览器生成过程截图

话题：
#adventurex2026 #blockless #BlocklessMakeAPP #创客 #STEM教育
```

### 27.5 明天现场分工清单

引导员：

- 准备 3 个最稳 Demo：课堂倒计时器、传感器仪表盘、记忆小游戏。
- 帮用户把想法改成清楚 prompt。
- 遇到报错时，把错误信息复制给 AI 继续修，不要跳过失败。
- 帮用户确认 App 能预览、能打包、能装到设备。
- 帮用户准备 uPyStore 上传材料。

拍摄员：

- 每个用户拍设备近景、操作远景、人物反应。
- 每个成功 App 拍 10-20 秒设备运行视频。
- 每小时拍一次多设备作品墙。
- 收集一句话用户反馈。
- 记录授权状态，未授权素材不要公开。

后端/运维：

- 提前启动本地服务和模型接口。
- 准备点数后台和人工加点流程。
- 准备本地设备安装脚本和备用 USB 线。
- 保留 session、artifact、MPK、日志。
- 遇到服务中断时能恢复 session，不让用户从头开始。

### 27.6 活动后整理

当天活动结束后需要整理：

- 成功生成的 App 数量。
- 成功安装到设备的 App 数量。
- 上传 uPyStore 或准备上传的 App 数量。
- 用户发布小红书数量。
- 最常见的失败原因。
- 最受欢迎的 App 类型。
- 可公开使用的视频、照片和用户反馈。
- 需要产品立刻修的前三个问题。

第二天输出：

- 1 条 15 秒竖屏高光视频。
- 1 条 60 秒产品介绍视频。
- 1 条用户测评合集。
- 1 组设备运行照片墙。
- 1 份问题复盘和产品改进清单。

## 28. 外部链接总表

Ubuntu：

- https://ubuntu.com/download/desktop
- https://releases.ubuntu.com/24.04/
- https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso
- https://releases.ubuntu.com/24.04/SHA256SUMS

Windows / VMware：

- https://support.microsoft.com/zh-CN/Windows/Experience/enable-virtualization-on-windows
- https://support.broadcom.com/
- https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hype.html
- https://knowledge.broadcom.com/external/article/344595/downloading-vmware-workstation-pro.html
- https://knowledge.broadcom.com/external/article/397417/downloading-free-software-from-the-broad.html
- https://knowledge.broadcom.com/external/article/387947/installing-vmware-workstation-pro.html
- https://knowledge.broadcom.com/external/article?legacyId=1018415
- https://knowledge.broadcom.com/external/article/315363/install-vmware-tools-in-vmware-products.html
- https://knowledge.broadcom.com/external/article/313456/vmware-support-for-openvmtools.html
- https://knowledge.broadcom.com/external/article?legacyId=90112
- https://knowledge.broadcom.com/external/article/315436/supported-host-operating-systems-for-vmw.html

Claude Code / Skills：

- https://code.claude.com/docs/en/quickstart
- https://docs.anthropic.com/en/docs/claude-code/getting-started
- https://code.claude.com/docs/en/commands
- https://code.claude.com/docs/zh-CN/skills
- https://support.claude.com/en/articles/12512176-what-are-skills
- https://support.claude.com/en/articles/12512180-use-skills-in-claude
- https://www.npmjs.com/package/@anthropic-ai/claude-code

MicroPythonOS：

- https://micropythonos.com/
- https://docs.micropythonos.com/
- https://github.com/MicroPythonOS/MicroPythonOS
- https://docs.micropythonos.com/getting-started/running/
- https://docs.micropythonos.com/os-development/running-on-desktop/
- https://docs.micropythonos.com/web-port/using/
- https://docs.micropythonos.com/apps/
- https://docs.micropythonos.com/apps/appstore/
- https://docs.micropythonos.com/architecture/filesystem/
- https://install.micropythonos.com/
- https://web.micropythonos.com/
- https://micropythonos.github.io/MicroPythonOS/

uPyStore：

- https://upystore.io/
- https://upystore.io/developer

浏览器项目：

- https://github.com/erkou111/micropythonos-ai-app-builder

MicroPython / LVGL：

- https://www.micropython.org/download/
- https://docs.lvgl.io/master/integration/bindings/micropython.html
- https://github.com/lvgl/lv_binding_micropython

开发工具：

- https://git-scm.com/downloads
- https://git-scm.com/docs/git-submodule
- https://git-scm.com/docs/gitsubmodules.html
- https://nodejs.org/en/download
- https://docs.astral.sh/uv/
- https://platform.deepseek.com/
- https://ccswitch.io/
- https://github.com/farion1231/cc-switch

宣传 / PPT / 视频工具：

- https://obsproject.com/
- https://www.blackmagicdesign.com/products/davinciresolve
- https://www.capcut.com/
- https://www.audacityteam.org/
- https://www.screentogif.com/
- https://ffmpeg.org/
- https://www.canva.com/
- https://www.figma.com/
- https://www.microsoft.com/microsoft-365/powerpoint
- https://www.apple.com/keynote/
- https://www.google.com/slides/about/

社媒 / 品牌素材：

- https://www.xiaohongshu.com/
- https://www.tuya.com/
- https://www.tuya.com/partners/powered-by-tuya
- https://developer.tuya.com/en/docs/iot/online-product-catalog-user-guide?id=Ka27mdi0v8lyf

GitHub：

- https://github.com/
- https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository
- https://docs.github.com/en/get-started/using-git/getting-changes-from-a-remote-repository
- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository
- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests
- https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account
- https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys
- https://github.com/actions/checkout

## 29. 真人出镜视频脚本

本章的视频格式：**前面真人出镜建立信任 → 后面字幕+画面展示产品**。所有脚本面向小红书、抖音、B站、视频号等平台。核心原则：真人出镜不是为了"出镜而出镜"，而是让观众看到一个真实的人在使用产品的过程——表情、反应、手的操作、设备的亮屏——这些是纯录屏做不到的。

### 29.1 真人出镜视频的通用结构

每条真人出镜视频按以下结构组织：

```
[0:00-0:05] 真人出镜 Hook
    → 人物面对镜头，一句话制造好奇或共鸣
[0:05-0:15] 真人出镜 问题/背景
    → 人物继续面对镜头，讲痛点或场景
[0:15-0:45] 字幕+B-roll 产品演示
    → 画面切到屏幕录制/设备实拍，字幕+旁白推进
[0:45-0:55] 真人出镜 感受/结论
    → 人物回到镜头前，讲真实感受
[0:55-1:00] 字幕+Logo CTA
    → 产品名/口号/行动号召
```

### 29.2 拍摄真人出镜的基本要求

拍摄真人出镜部分时：

- **光线**：面光为主，避免顶光和背光。自然光窗边或环形灯均可。面部不能有阴影。
- **背景**：干净但不过于空白。建议背景出现工作台、书架、设备等"创客感"元素，但不要杂乱。
- **机位**：手机横屏拍摄，机位与眼睛平齐或略高。不要仰拍或俯拍。
- **眼神**：看镜头，不是看屏幕里的自己。把镜头当成一个朋友在听你说话。
- **声音**：安静环境，离麦克风不超过 50cm。如果用手机拍，确认收音清晰无回声。
- **服装**：休闲但有质感。纯色 T恤、卫衣、衬衫均可。避免大面积 logo 和细条纹（摩尔纹）。
- **时长控制**：真人出镜部分每个段落不超过 15 秒。超过 15 秒剪成两段，中间插入 B-roll。
- **竖屏 vs 横屏**：主拍横屏（16:9），同时拍一版竖屏（9:16）备用。竖屏时人物居中，上方留字幕空间。

### 29.3 30 秒真人出镜短视频脚本（抖音/小红书/视频号）

**定位**：让观众在 30 秒内理解"这是什么东西"并产生兴趣。

**视频结构**：

| 时间 | 画面 | 音频 |
|---|---|---|
| 0:00-0:03 | **真人出镜**。人物手持一块亮屏的 ESP32 设备，设备上跑着一个 App。人物面对镜头微笑。 | （现场原声）"你有没有想过，自己做一个小屏幕上的 App？" |
| 0:03-0:08 | **真人出镜**。人物把设备靠近镜头，让观众看清屏幕上在跑什么。然后放下设备，继续说。 | （现场原声）"我以前觉得这肯定要学很久。但今天我在浏览器里说了一句话，它就帮我生成了。" |
| 0:08-0:18 | **字幕+B-roll**。快速切换：①浏览器输入 prompt 的画面 ②时间线进度条跑动 ③桌面预览弹出 ④设备屏幕亮起（与开头同一块设备）。字幕叠加在画面下方。 | （旁白，语速稍快）"打开 Blockless-Make-APP，用自然语言描述你想做的 App。系统自动分析需求、生成代码、在模拟器里预览。满意了就打包成 MPK，装到设备上。" |
| 0:18-0:24 | **字幕+B-roll**。多设备分屏画面：4-6 块不同的板卡同时跑着不同的 App。字幕：`当前真实适配 15 个物理板卡`。 | （旁白）"不只是预览，是能在真实设备上跑起来的完整 App。支持 15 款板卡。" |
| 0:24-0:28 | **真人出镜**。人物回到镜头前，拿起设备，指着屏幕。自然微笑。 | （现场原声）"我觉得这才是创客该有的样子——先做出来，再慢慢学。" |
| 0:28-0:30 | **字幕+Logo**。黑底白字：`Blockless-Make-APP` + 口号：`让创客 App 先跑起来，再传播出去。` | （旁白）"Blockless-Make-APP。让创客 App 先跑起来，再传播出去。" |

**拍摄 Checklist**：
- [ ] 真人出镜 3 段，每段控制在 5 秒以内
- [ ] 设备屏幕清晰可见，无反光
- [ ] B-roll 至少包含：浏览器操作、模拟器预览、真机运行、多设备分屏
- [ ] 出镜时手上有设备，不是空手讲
- [ ] 同时拍横版和竖版

---

### 29.4 60 秒真人出镜产品介绍脚本（小红书/B站/视频号）

**定位**：让观众理解产品解决什么问题、怎么用、为什么不一样。

**视频结构**：

| 时间 | 画面 | 音频 |
|---|---|---|
| 0:00-0:05 | **真人出镜**。人物坐在工作台前，桌上有电脑和几块 ESP32 板卡。人物面对镜头。 | （现场原声）"你有没有遇到过这种情况——看到一个很酷的硬件项目，想复刻，但看了教程就放弃了？" |
| 0:05-0:12 | **真人出镜**。人物拿起一块板卡，翻转一下，表情有点无奈。然后放下。 | （现场原声）"因为要先学环境配置、再学 LVGL、再研究目录结构、再折腾串口……还没看到效果，兴趣就被消耗完了。" |
| 0:12-0:18 | **真人出镜→过渡**。人物转向电脑屏幕，手放到键盘上。画面自然过渡到录屏。 | （现场原声）"但今天我发现了一个完全不同的路径。" |
| 0:18-0:35 | **字幕+B-roll**。详细录屏：①打开 Blockless-Make-APP 浏览器工作台 ②输入 prompt"做一个课堂倒计时器" ③系统依次展示 analyze → generate → test → package 阶段 ④桌面预览弹出，倒计时器在跑 ⑤时间线推进，进度条清晰。 | （旁白）"这是 Blockless-Make-APP。你只需要在浏览器里用中文描述你想做的 App。它会自动完成需求分析、代码生成、LVGL API 校验、桌面预览。每一步你都能看到进度。你可以在预览里确认效果，不满意就继续改。" |
| 0:35-0:42 | **字幕+B-roll**。①切换到 WebSerial 连接设备的画面 ②设备屏幕亮起，倒计时器在跑 ③手指在设备屏幕上点击开始、暂停、重置。 | （旁白）"确认没问题之后，打包成 MPK，通过 WebSerial 直接装到 ESP32 设备上。刚才还在预览里的 App，现在就真的在你手上跑起来了。" |
| 0:42-0:50 | **字幕+B-roll**。①多设备分屏（4-6 块不同的板卡跑不同 App）②15 块板卡照片墙快闪 ③uPyStore 发布检查页。 | （旁白）"它目前已经适配了 15 款物理板卡。做完的 App 可以发布到 uPyStore，别人搜到就能装，不需要任何环境配置。" |
| 0:50-0:57 | **真人出镜**。人物回到镜头前，手里拿着设备，设备亮屏。表情真诚。 | （现场原声）"它不会把你变成大神，但它会让你先做出来一个真的 App。有了这个起点，后面学什么都更有动力。" |
| 0:57-1:00 | **字幕+Logo**。黑底白字：`Blockless-Make-APP` + 口号。 | （旁白）"Blockless-Make-APP。让创客 App 先跑起来，再传播出去。" |

**拍摄 Checklist**：
- [ ] 真人出镜 3 段：痛点共鸣(0-12s)、过渡(12-18s)、结论(50-57s)
- [ ] 所有设备屏幕画面清晰、对焦准确
- [ ] B-roll 录屏鼠标移动缓慢稳定，不要跳帧
- [ ] 真机手指操作要拍清楚
- [ ] 多设备分屏画面是"视频最有冲击力的瞬间"，必须拍好
- [ ] 15 板卡照片墙快闪时长不超过 2 秒

---

### 29.5 3 分钟真人出镜深度演示脚本（B站/YouTube）

**定位**：面向已经产生兴趣的观众，完整展示从 prompt 到真机到发布的全流程。适合放在官网、GitHub README、路演 PPT 中。

**真人出镜分段结构**：

```
[段落1 0:00-0:30]   真人出镜：背景和问题（全真人）
[段落2 0:30-0:50]   真人出镜：提出方案（真人→转场到录屏）
[段落3 0:50-1:30]   字幕+B-roll：完整生成流程
[段落4 1:30-1:50]   真人出镜：中间感受反馈（真人+设备）
[段落5 1:50-2:20]   字幕+B-roll：真机部署+多设备分屏
[段落6 2:20-2:40]   字幕+B-roll：uPyStore发布引导
[段落7 2:40-2:55]   真人出镜：总结+观点
[段落8 2:55-3:00]   字幕+Logo CTA
```

**详细脚本**：

---

**段落 1 — 0:00-0:30 — 真人出镜：背景和问题**

| 时间 | 画面 | 音频 |
|---|---|---|
| 0:00-0:08 | 真人出镜。中景，人物坐在工作台前。桌上有电脑、板卡、USB线。人物面对镜头，表情认真。 | （现场原声）"我玩硬件大概五年了。这五年里我做过的项目不少，但真正能被别人复刻的——几乎没有。" |
| 0:08-0:18 | 真人出镜。近景，人物拿起桌上一块板卡，翻转展示。然后目光回到镜头。 | （现场原声）"原因很简单。我做完一个项目后，别人想体验，得先看我的教程、装环境、配依赖、下载代码、连接设备、烧录系统……大部分人走到第二步就放弃了。" |
| 0:18-0:25 | 真人出镜。中景，人物放下板卡，双手摊开。 | （现场原声）"所以我一直在想：有没有一种方式，能让别人不用跨过这么多门槛，就能先体验到我的作品？" |
| 0:25-0:30 | 真人出镜。近景，人物稍微前倾，表情从无奈转为有答案。 | （现场原声）"然后我遇到了 Blockless-Make-APP。它做的事情很简单——但正好解决了这个问题。" |

---

**段落 2 — 0:30-0:50 — 真人出镜+转场**

| 时间 | 画面 | 音频 |
|---|---|---|
| 0:30-0:38 | 真人出镜。人物转向电脑，手指向屏幕。镜头跟随人物视线方向轻微转动，然后画面自然过渡到录屏。 | （现场原声）"我演示一下你就明白了。我只需要打开浏览器，用中文描述我想做的 App。比如——做一个课堂倒计时器。" |
| 0:38-0:50 | 录屏+字幕。浏览器中 Blockless-Make-APP 工作台首页。人物用键盘输入 prompt："做一个 MicroPythonOS 课堂倒计时器 App，支持设置 5、10、15 分钟，有开始暂停重置按钮，时间到了屏幕变红闪烁"。鼠标点击"开始生成"。 | （旁白）"我不需要写一行代码。不需要了解 LVGL 的 API。不需要知道 MicroPythonOS 的目录结构。我只需要把我想做的事情描述清楚。" |

---

**段落 3 — 0:50-1:30 — 字幕+B-roll：完整生成流程**

| 时间 | 画面 | 音频 |
|---|---|---|
| 0:50-1:00 | 录屏+字幕。系统开始执行。时间线展示：`Analyze → Prepare Dependencies → Generate → Test → Package`。每个阶段完成时有一个勾。当前正在"Analyze"阶段。 | （旁白）"系统开始工作。它先分析我的需求，提取出关键功能点。然后检查我的描述中有没有涉及 MicroPythonOS 不支持的能力。" |
| 1:00-1:10 | 录屏+字幕。切换到"Generate"阶段。代码文件列表在侧边栏逐渐出现：`MANIFEST.JSON`、`assets/main.py`、图标文件。 | （旁白）"确认需求后，它开始生成代码。你会看到文件一个个出现。每个 LVGL API 调用都会被交叉校验，确保不会生成在当前版本中不存在的函数。" |
| 1:10-1:20 | 录屏+字幕。切换到"Test"阶段。桌面模拟器弹窗，一个倒计时器界面出现。倒计时数字在跳动。 | （旁白）"代码生成完后，自动在桌面模拟器里跑一次——这叫 desktop smoke test。如果 App 能在这里正常启动和运行，基本就不会有大的结构问题。" |
| 1:20-1:30 | 录屏+字幕。模拟器画面放大，鼠标点击"开始"按钮，倒计时开始走动。点击"暂停"，暂停。点击"重置"，数字恢复。三个按钮都正常工作。 | （旁白）"我在模拟器里操作了一下：开始、暂停、重置，都没问题。如果哪里不满意，我可以直接告诉它'把按钮变大一点''时间到了改成红色'——它会在上一版基础上改，不会全部重建。" |

---

**段落 4 — 1:30-1:50 — 真人出镜：中间感受反馈**

| 时间 | 画面 | 音频 |
|---|---|---|
| 1:30-1:38 | 真人出镜。人物从电脑前转回镜头。手里拿起一块 ESP32 设备。表情是"挺满意"的那种微笑。 | （现场原声）"到这一步大概花了十几分钟。从想法到能在模拟器里正常跑的 App。如果是我自己手写，光是查 LVGL 的文档加写代码，至少半天。" |
| 1:38-1:50 | 真人出镜。人物把设备举到镜头旁，手指着屏幕。然后拿一根 USB 线连接设备。 | （现场原声）"但这只是预览。真正让我兴奋的是下一步——把这个 App 装到真实的设备上，看看它到底能不能跑。" |

---

**段落 5 — 1:50-2:20 — 字幕+B-roll：真机部署+多设备分屏**

| 时间 | 画面 | 音频 |
|---|---|---|
| 1:50-2:00 | 录屏+字幕。浏览器中点击"Deploy to Device"。弹出 WebSerial 设备选择框。选择一个 ESP32-S3 设备。进度条显示"正在传输文件"。 | （旁白）"Blockless-Make-APP 支持通过 WebSerial 直接部署到设备。选择串口设备，确认，文件就传过去了。不需要打开命令行，不需要手动敲 mpremote。" |
| 2:00-2:10 | **切到真机实拍**。ESP32 设备屏幕亮起，倒计时器 App 在跑。一只手入镜，在屏幕上点击"开始"。倒计时数字开始跳动。 | （旁白）"十几秒后，设备重启。刚才在电脑预览里看到的那个界面，现在真实地出现在这块小屏幕上。你用手指去点开始，它在走。你暂停，它就停。" |
| 2:10-2:20 | 多设备实拍。4-6 块不同的板卡并排在桌上，各自跑着不同的 App（倒计时器、传感器面板、小游戏、打卡器）。镜头从左到右平移。字幕在每个设备旁标注板卡型号。 | （旁白）"而且不只是这一块板卡。同一个 App，也可以部署到不同的设备上。目前支持 15 款物理板卡。不同形状、不同屏幕尺寸、不同厂牌——但 App 的体验是一致的。" |

---

**段落 6 — 2:20-2:40 — 字幕+B-roll：发布引导**

| 时间 | 画面 | 音频 |
|---|---|---|
| 2:20-2:30 | 录屏+字幕。展示 Package 阶段的结果页面。`com.example.countdown_r1.mpk` 文件高亮显示。`MANIFEST.JSON` 检查结果：publisher 必填 √、版本号格式正确 √、图标存在 √。 | （旁白）"当你对 App 满意后，可以打包成 MPK 文件。系统会自动检查 MANIFEST 是否完整、文件名是否符合规范、截图是否符合格式。" |
| 2:30-2:40 | 录屏+字幕。切换到 Publish 页面。展示 uPyStore 发布检查清单：MPK √、截图 √、release notes √。底部按钮"打开 uPyStore 开发者入口"。 | （旁白）"然后系统会引导你准备发布材料。做完检查清单后，你可以把 MPK 上传到 uPyStore。别人在 uPyStore 里搜到你的 App，下载、安装、运行——不需要任何环境配置。" |

---

**段落 7 — 2:40-2:55 — 真人出镜：总结**

| 时间 | 画面 | 音频 |
|---|---|---|
| 2:40-2:48 | 真人出镜。中景，人物回到镜头前。面前摆着几块正在跑 App 的板卡（画面里能看到它们亮着）。 | （现场原声）"这就是我为什么觉得 Blockless-Make-APP 不一样。它不是又一个 AI 代码工具。它在解决一个更根本的问题——怎么让创客作品能从'少数人能复刻的小圈子'走出来，变成更多人能真正体验的东西。" |
| 2:48-2:55 | 真人出镜。近景，人物正视镜头。 | （现场原声）"从想法到预览，从预览到真机，从真机到发布。每一步你都看得见。每一步都有人能跟得上。这才叫作品真的'传出去了'。" |

---

**段落 8 — 2:55-3:00 — CTA**

| 时间 | 画面 | 音频 |
|---|---|---|
| 2:55-3:00 | 黑底白字。Logo：`Blockless-Make-APP`。口号：`让创客 App 先跑起来，再传播出去。`GitHub 地址、官网地址以较小字号出现在下方。 | （旁白）"Blockless-Make-APP。在浏览器里，把你的想法变成一台设备上真实跑着的 App。" |

---

**3 分钟视频拍摄总 Checklist**：
- [ ] 真人出镜 4 段：开头问题(0-30s)、中间反馈(1:30-1:50)、总结(2:40-2:55)、每段之后接 B-roll
- [ ] B-roll 涵盖：浏览器操作、模拟器预览、真机实拍、多设备分屏、发布检查页
- [ ] 真机实拍至少 30 秒以上，让观众看到 App 确实在动
- [ ] 手指在设备上的操作要拍清楚（开始、暂停、重置）
- [ ] 多设备分屏是视频高潮，画面要有冲击力——至少 4 块板卡同框
- [ ] 所有设备屏幕不能过曝，快门调至 1/50 或 1/60
- [ ] 15 板卡照片墙出现在段落 5 或段落 8
- [ ] 旁白和真人出镜的语速自然，不要像读稿
- [ ] 横版 16:9 用于 B站/YouTube，同时剪一版竖版用于抖音/小红书

---

### 29.6 真人出镜用户证言视频脚本（UGC风格）

**定位**：模拟真实用户在活动现场第一次使用 Blockless-Make-APP 的体验。强调真实反应，不用专业演员，不用完美台词。

**视频结构**：

```
[0:00-0:08]   真人出镜：我是谁 + 来干嘛
[0:08-0:25]   字幕+B-roll：操作过程（录屏+设备）
[0:25-0:35]   真人出镜：第一次看到 App 跑起来的反应
[0:35-0:45]   字幕+B-roll：App 在设备上运行的画面+用户操作
[0:45-0:55]   真人出镜：感受 + 推荐
[0:55-1:00]   字幕+Logo
```

**详细脚本**：

| 时间 | 画面 | 音频 |
|---|---|---|
| 0:00-0:04 | **真人出镜**。用户站在 adventurex 现场，背景是展位和人群。面对镜头有点紧张但兴奋。 | （现场原声）"嗨，我是【姓名】，今天来 adventurex 逛展。他们说有个东西能'说句话就做 App'，我来试试。" |
| 0:04-0:08 | **真人出镜**。用户坐到电脑前，侧脸。手指向屏幕，然后开始打字。 | （现场原声）"我想做一个【App名称】。就是【简单描述功能】的那种。" |
| 0:08-0:18 | **录屏+字幕**。浏览器中输入 prompt。系统开始运行，时间线滚动。字幕：`输入需求 → AI自动生成 → 预览` | （旁白）"只需要在浏览器里描述你想做的 App。系统自动进行分析、生成、预览。" |
| 0:18-0:25 | **录屏+字幕**。桌面模拟器弹出，App 界面出现。 | （旁白）"几分钟后，预览就出来了。可以看到界面、交互、布局。" |
| 0:25-0:30 | **真人出镜**。用户从屏幕前抬起头，面对镜头。表情是惊讶+开心。 | （现场原声）"真的假的？！我说的那些它都做出来了！你看这个【功能1】，还有【功能2】——全都在。" |
| 0:30-0:35 | **真人出镜→设备**。用户手里拿起一块亮屏的 ESP32 设备，屏幕上跑着刚生成的 App。用户用手指点了几下屏幕，App 在响应。 | （现场原声）"而且他们说可以装到设备上——你看，已经装好了。这是真的在跑。" |
| 0:35-0:45 | **设备实拍+字幕**。设备近景，App 画面清晰可见。手指操作：点击、滑动。App 各个功能逐一展示。 | （旁白）"从描述需求到 App 在真实设备上运行，整个过程不到 20 分钟。不需要写代码，不需要配环境。" |
| 0:45-0:52 | **真人出镜**。用户面对镜头，手里拿着设备。表情真诚，不是在"念广告"。 | （现场原声）"说实话来之前我没抱太大期望。但做完了以后……我马上就想回去再做一个。我觉得学生、老师、喜欢折腾硬件的人都应该来试一下。" |
| 0:52-0:55 | **真人出镜**。用户举起设备靠近镜头，让观众看清屏幕。 | （现场原声）"这个东西叫 Blockless-Make-APP。先标记一下，等公开了给你们分享入口。" |
| 0:55-1:00 | **字幕+Logo**。黑底白字。`Blockless-Make-APP` + 口号。 | （旁白）"Blockless-Make-APP。让创客 App 先跑起来，再传播出去。" |

**拍摄要求**：
- [ ] 用户必须是真实体验，不能摆拍
- [ ] 用户反应要保留真实的惊讶、开心、不确定——不要要求用户"再来一条更夸张的"
- [ ] 设备屏幕清晰可见，用户手指操作要拍到
- [ ] 一句"真的假的"比十句"非常好用"有说服力
- [ ] 拍完后让用户自己确认能不能公开发布（未成年需监护人授权）
- [ ] 横版用于 B站/YouTube，竖版用于抖音/小红书

**不同用户类型的证言角度**：

| 用户类型 | 证言切入点 | 适合说的关键句 |
|---|---|---|
| 学生 | "我以前觉得做 App 是程序员的事" | "原来我也能做出来" |
| 老师 | "我在想下学期的课可以怎么用" | "学生第一节课就能带着作品回家" |
| 创客 | "我做的东西终于有办法让别人体验了" | "MPK 包发过去，对方就能装" |
| 家长 | "带孩子来体验的，结果我自己也做了一个" | "比编程班的效果直观太多了" |
| 硬件爱好者 | "本来以为又是给小白玩的，结果自己玩上头了" | "10 分钟出原型，这个效率太香了" |

---

### 29.7 真人出镜视频通用字幕规范

所有真人出镜视频中，B-roll 部分的字幕遵循以下规范：

**字体**：
- 中文：思源黑体 Medium / 阿里巴巴普惠体
- 英文/数字：Inter Medium / SF Pro Display
- 不使用宋体、楷体等衬线字体

**样式**：
- 字号：1080p 视频使用 48-56px（标题）、36-42px（正文）
- 颜色：白色 #FFFFFF，加 2px 黑色描边或 40% 黑色背景条
- 位置：竖屏视频字幕在画面下 1/3 处；横屏视频字幕居中偏下
- 每条字幕不超过 18 个中文字，超过则拆行
- 关键词（产品名、功能点、数据）用黄色 #FFD700 或品牌色高亮

**时机**：
- 字幕与人声完全同步出现和消失（帧级同步）
- 每条字幕停留不少于 1.5 秒，不超过 4 秒
- 两个连续字幕之间不留空白帧

**必须出现的固定字幕**（至少出现一次）：
- `当前真实适配 15 个物理板卡 + Linux/Web target`
- `不需要写代码，不需要配环境`
- `从浏览器预览 → 真机运行 → 发布到 uPyStore`
- `Blockless-Make-APP`

---

### 29.8 B-roll 素材库清单

以下是所有真人出镜视频共用的 B-roll 素材，需要提前拍好并分类存放：

**A 类 — 浏览器操作（录屏）**：

| 编号 | 内容 | 时长 | 用途 |
|---|---|---|---|
| A01 | 输入 prompt 并点击生成 | 8-10s | 所有视频 |
| A02 | 时间线滚动（完整 6 阶段） | 15-20s | 3分钟视频 |
| A03 | 时间线滚动（加速版 4x） | 3-5s | 短视频 |
| A04 | 桌面模拟器弹出+App 运行 | 10-15s | 所有视频 |
| A05 | 在模拟器中操作 App（点击按钮、滑动） | 8-10s | 3分钟视频 |
| A06 | 连续修改（输入修改指令→重新生成→预览变化） | 15-20s | 3分钟视频 |
| A07 | 打包完成页面（MPK 文件高亮） | 5s | 60s/3分钟视频 |
| A08 | WebSerial 设备选择+部署进度条 | 10s | 60s/3分钟视频 |
| A09 | uPyStore 发布检查页 | 5-8s | 3分钟视频 |
| A10 | 错误提示+retry 按钮+修复成功 | 10-15s | 教程视频 |

**B 类 — 设备实拍（相机/手机拍摄）**：

| 编号 | 内容 | 时长 | 用途 |
|---|---|---|---|
| B01 | 单块 ESP32 设备亮屏，App 正在运行（静态） | 10s | 所有视频 |
| B02 | 手指在设备屏幕上操作（点击、滑动） | 10-15s | 所有视频 |
| B03 | 多块设备并排（4-6块），每块跑不同 App | 15-20s | 所有视频 |
| B04 | 设备从电脑旁拿起，屏幕亮着 | 5s | 短视频 |
| B05 | USB 线连接设备与电脑 | 5s | 60s/3分钟视频 |
| B06 | 设备屏幕切换不同 App | 8-10s | 3分钟视频 |
| B07 | 15 块板卡照片墙（静态照片拼接或视频快闪） | 3-5s | 所有视频 |
| B08 | 单块板卡特写（板卡型号清晰可见） | 5s | 3分钟视频 |
| B09 | 用户手持设备面对镜头展示 | 5-8s | 证言视频 |
| B10 | 设备+工作台+咖啡/植物等 lifestyle 镜头 | 5s | 所有视频 |

**C 类 — 场景/氛围（相机/手机拍摄）**：

| 编号 | 内容 | 时长 | 用途 |
|---|---|---|---|
| C01 | 工作台全景（电脑+设备+线缆+笔记本） | 5s | 60s/3分钟视频 |
| C02 | 人物侧脸操作电脑（不露正脸也可以） | 5s | 60s/3分钟视频 |
| C03 | 人物手部特写（打字、拿设备、连 USB） | 3-5s | 所有视频 |
| C04 | 创客空间/教室/展会全景 | 5s | 60s视频 |
| C05 | 多人围坐各做各的 App | 5-8s | 3分钟视频 |
| C06 | 用户表情反应（惊喜、专注、满意） | 3-5s | 证言视频 |
| C07 | 设备屏幕在暗光环境中的发光效果 | 5s | 所有视频 |
| C08 | 成品设备+包装盒+MPK 文件的摆拍 | 5s | 发布视频 |

---

### 29.9 不同平台的剪辑版本差异

同一条真人出镜视频，需要根据不同平台剪出不同版本：

**抖音/小红书（竖版 9:16）**：
- 真人出镜部分裁剪为竖版，人物居中偏上
- 字幕放大到 56-64px
- 前 3 秒必须有真人+设备同框
- 总时长控制在 30-60 秒
- 视频描述区带话题标签 `#adventurex2026 #blockless #BlocklessMakeAPP`
- 封面选择真人出镜+设备亮屏的那一帧

**B站/YouTube（横版 16:9）**：
- 真人出镜部分保留完整构图
- 字幕使用 42-48px
- 可以在 3-5 秒处加入标题卡片
- 总时长 1-3 分钟均可
- 视频简介区放产品链接和 GitHub 地址
- 封面用多设备分屏画面+产品名标题字

**视频号（横竖均可）**：
- 优先使用竖版
- 字幕偏上，避免被视频号底部 UI 遮挡
- 前 5 秒不能用纯字幕，必须有动态画面
- 简介区放公众号文章链接

**朋友圈/微信群（竖版 9:16，15-30秒）**：
- 极速版：2 秒 Hook + 10 秒核心演示 + 3 秒 Logo
- 不需要真人出镜全程，保留开头 Hook 即可
- 字幕精简到每屏不超过 10 个字

---

### 29.10 真人出镜视频拍摄前准备清单

**拍摄前一天**：
- [ ] 确认拍摄设备：手机/相机 + 三脚架 + 补光灯 + 麦克风
- [ ] 确认拍摄场地：安静、光线可控、背景整洁
- [ ] 准备出镜道具：电脑（打开 Blockless-Make-APP）、2-4 块 ESP32 设备（已刷好 MicroPythonOS）、USB 线
- [ ] 确认设备上已提前装好几个可展示的 App（避免现场等生成）
- [ ] 准备好需要录屏的 B-roll 操作步骤（提前走一遍流程）
- [ ] 确认服装（提前试穿，避免条纹）
- [ ] 确认脚本（打印或放提词器，但不要照着读）

**拍摄当天**：
- [ ] 先拍所有 B-roll（录屏+设备实拍），再拍真人出镜部分
- [ ] 真人出镜部分按段落拍，每段不超过 15 秒
- [ ] 每段拍完立刻回看，确认眼神、声音、光线没问题
- [ ] 每个 B-roll 镜头拍 2-3 条备选
- [ ] 设备屏幕需要调低亮度或调整快门避免频闪（1/50 或 1/60）
- [ ] 拍完后现场备份素材，不要只存在一张卡里

**后期剪辑**：
- [ ] 先搭时间线骨架：真人段落 + B-roll 段落按脚本排好
- [ ] 再精修节奏：每个切镜不超过 5 秒，B-roll 不要拖
- [ ] 字幕与旁白帧级同步
- [ ] 背景音乐音量控制在 -20dB 到 -25dB，不能盖过人声
- [ ] 导出前全片过一遍，确认所有文字无错别字
- [ ] 导出横版和竖版两个版本

---

## 30. 跨设备硬件能力接入要求

浏览器产品不增加板卡选择器。用户描述需要的功能，后端把它解析成 `camera`、`audio.output`、`sensor.imu`、`input.keypad` 等抽象能力；设备连接并授权后，再由 MicroPythonOS manager 探测实际能力。

机器可读合同位于 `mpos-dev-web/reference/board_capabilities.json`。完整前后端字段、生成器门禁、错误分类、预览/真机测试和文件级修改清单放在浏览器项目仓库：

```text
micropythonos-ai-app-builder/docs/cross-device-capability-integration.md
```

必须遵守：

- `portable_api=true` 才允许自动生成板载硬件功能，并必须有运行时 fallback。
- `portable_api=false` 返回 `MPOS_CAPABILITY_API_MISSING`，不能让模型改成板卡私有代码。
- 普通 App 禁止 `mpos.board.*` 和直接 GPIO/I2C/SPI/UART/I2S/ADC/NeoPixel；后端必须运行 `mpos-gen-app/scripts/check_app_hardware_policy.py`。
- 只有用户明确提出外接模块、确认接线和资源冲突并授权后，才允许外接配件驱动例外。
- Web/桌面无真实硬件属于 partial/preview limitation；连接设备后缺少能力属于 `HARDWARE_CAPABILITY_UNAVAILABLE`，二者都不能触发无限 AI 修复。
- 前端只显示能力状态和权限提示，不要求用户先理解或选择具体开发板。
