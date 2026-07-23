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

## 25. 外部链接总表

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

GitHub：

- https://github.com/
- https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository
- https://docs.github.com/en/get-started/using-git/getting-changes-from-a-remote-repository
- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository
- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests
- https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account
- https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys
- https://github.com/actions/checkout
