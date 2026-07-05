# MicroPython Skills for GraftSense

GraftSense MicroPython Skill 集合，包含 **25 个专用 Skill**，分为两大体系：

**A. 一句话造硬件 — AI 嵌入式代码生成流水线（10 个 skill）**：从自然语言需求出发，自动完成硬件选型、代码生成、PC 仿真、烧录部署、错误修复的完整闭环。

**B. 驱动开发规范化（15 个 skill）**：基于 [GraftSense-Drivers-MicroPython](https://github.com/FreakStudioCN/GraftSense-Drivers-MicroPython) 仓库的完整编写规范（22章、2200+ 行），覆盖驱动规范化、测试文件生成、README 生成、性能优化、内存优化、打包、设备部署。

> **当前 source of truth（2026-07）**：本仓库已经完成 VS Code 插件版 8 流程 Skill/plugin。若下游仓库的 submodule 只看到 6 个 plugin，说明下游 pinned commit 落后，应 bump/sync 到本仓库最新 commit，而不是认为 wiring/diagram 缺失。

---

## 当前 Skill / Plugin 全量导览

本仓库同时保留两类资产：

- **插件版 Skill/plugin**：面向 Blockless VS Code 插件和自动化 workflow host，目录名以 `-plugin` 结尾，并带 `.codex-plugin/plugin.json`。
- **Classic Skill**：面向 Claude Code / Skillfish 直接调用，目录名通常不带 `-plugin`，保留原有 `/upy-*` 命令式用法。

### 插件版 8 流程 Skill/plugin

| # | Skill/plugin | 类型 | 流程位置 | 说明 |
|---|---|---|---|---|
| 1 | `upy-analyze-plugin` | 主链必经 | analyze | 需求解析、器件识别、驱动资料搜索、输出 manifest_content |
| 2 | `upy-select-hw-plugin` | 主链必经 | select-hw | 官方板卡选择、本地 overlay 合并、pin plan、BOM、`board_unavailable` |
| 3 | `upy-flash-mpy-firmware-plugin` | 主链必经 | flash | MicroPython 固件解析、下载、烧录或 UF2/manual 指引 |
| 4 | `upy-scaffold-plugin` | 主链必经 | scaffold | 生成项目骨架、目录结构、模板、session/checkpoint/file_manifest |
| 5 | `upy-generate-plugin` | 主链必经 | generate | 业务代码、驱动适配、质量门禁、可选 wiring/diagram 入口 |
| 6 | `upy-deploy-plugin` | 主链必经 | deploy | mpremote 上传、运行、REPL 日志、marker、设备端验证 |
| 7 | `upy-wiring-plugin` | 可选产物流程 | wiring | 从 manifest/代码/pin plan 生成接线图和 artifact |
| 8 | `upy-diagram-plugin` | 可选产物流程 | diagram | 生成架构图、流程图、数据流图和 artifact |

### 缺失硬件驱动分支

| Skill/plugin | 类型 | 说明 |
|---|---|---|
| `upy-gen-driver-plugin` | 插件版缺失驱动分支 | 面向 VS Code 插件的缺失硬件驱动生成流程，支持 pipeline/standalone/fix、PDF/Arduino/GitHub/芯片型号/手工事实输入、硬件验证状态和 generate 前门禁 |
| `upy-gen-driver` | Classic Skill | 原始缺失驱动生成 Skill，保留直接调用和规则来源；插件化时不应覆盖该目录 |

### Classic 一句话造硬件流水线 Skill

| Skill | 说明 |
|---|---|
| `upy-analyze` | 自然语言需求解析、器件清单、驱动 API 参考 |
| `upy-select-hw` | MCU/板卡选型、引脚分配、BOM |
| `upy-scaffold` | 生成 firmware/ 项目骨架 |
| `upy-generate` | 下载驱动、生成 DI 架构业务代码、Mock 和 unittest |
| `upy-simulate` | PC 端 CLI/rich 全流程模拟，无需真实硬件 |
| `upy-deploy` | mpremote 上传、烧录、持久会话和 PASS/FAIL 初判 |
| `upy-autofix` | deploy 失败后的 triage、分级决策和上游 skill 委托修复 |
| `upy-wiring` | Classic 接线图生成 Skill |
| `upy-diagram` | Classic 架构图、流程图、数据流图生成 Skill |
| `upy-project` | 早期端到端项目生成入口，适合直接从项目描述生成代码和调试流程 |

### 驱动规范化、生成、优化和打包 Skill

| Skill | 说明 |
|---|---|
| `upy-norm-driver` | 将可用但不规范的 MicroPython 驱动改写为 GraftSense 规范格式 |
| `upy-norm-main` | 规范化 `main.py` 测试文件，不改变测试逻辑 |
| `upy-norm-pkg` | 驱动包全流程规范化 orchestrator |
| `upy-gen-main` | 根据驱动 `.py` 从 0 生成完整 `main.py` 测试文件 |
| `upy-gen-readme` | 根据驱动 `.py` 从 0 生成 README |
| `upy-gen-pkg` | 根据驱动目录或 `.py` 从 0 生成 `package.json` |
| `upy-opt-driver` | 按性能优化指南改写 MicroPython 代码 |
| `upy-slim-driver` | 按内存占用最小化指南降低 RAM 使用 |
| `upy-pack-driver` | 将驱动、main、README、package.json 组织为标准驱动包目录 |
| `upy-deploy-test` | 设备部署与验证 Skill，可用于驱动包验收 |

### 查询、审查和设备工具 Skill

| Skill | 说明 |
|---|---|
| `upy-pkg-guide` | 查询器件驱动包用法，整合 upypi、awesome-micropython、README/API 信息 |
| `fetch-doc` | 获取 URL / GitHub / upypi 页面内容，供其他 Skill 补充资料 |
| `review` | MicroPython 代码审查，基于历史 review 模式辅助检查 |
| `mpremote-device-interaction` | 设备连接、状态查询、固件版本、内存和文件信息 |
| `mpremote-file-transfer` | 本地与设备之间复制文件、管理设备文件系统 |
| `mpremote-live-session` | 长连接和输出监控，适合 asyncio/aiorepl 或长时间运行场景 |

### 支撑目录

| 目录 | 说明 |
|---|---|
| `shared-plugin-scripts` | 插件版共用脚本和设备/mpremote 工具 |
| `upy-project-gen-toolchain-spec` | 项目生成工具链、协议、manifest/schema 和插件接口参考 |
| `scripts` | 仓库维护脚本，例如文档同步和翻译工具 |

---

## 📚 仓库文档说明

本仓库包含以下核心文档，建议按需阅读：

| 文档 | 说明 | 适用场景 |
|---|---|---|
| [README.md](README.md) | 本文档，Skill 安装和使用指南 | 快速上手、安装 Skill |
| [upy_driver_dev_spec_summary.md](upy_driver_dev_spec_summary.md) | **GraftSense 驱动编写规范完整版**（22章、2200+ 行），涵盖文件结构、类设计、docstring、类型注解、参数校验、异常处理、ISR 规范等全部规则 | 深入理解规范细节、手动编写驱动时参考 |
| [MicroPython_Performance_Optimization_Guide.md](MicroPython_Performance_Optimization_Guide.md) | **MicroPython 性能优化指南**，详细讲解 `@viper`、`@native`、`const()`、预分配缓冲区、`memoryview`、指针访问等优化技术，含实测数据和代码示例 | 优化驱动执行速度、理解 `upy-opt-driver` 的优化原理 |
| [MicroPython_Memory_Footprint_Minimization_Guide.md](MicroPython_Memory_Footprint_Minimization_Guide.md) | **MicroPython 内存占用最小化指南**，详细讲解 frozen 模块、`.mpy` 文件、`const()`、缓冲区复用、`gc` 控制、`__slots__`、生成器等内存优化技术，含 REPL 测试代码 | 降低驱动 RAM 占用、理解 `upy-slim-driver` 的优化原理 |

**阅读建议**：
- 新手：先看本 README 安装 Skill，直接使用 `/upy-norm-driver` 等命令规范化代码
- 进阶：阅读 `upy_driver_dev_spec_summary.md` 理解规范细节，手动编写符合规范的驱动
- 优化：阅读性能/内存优化指南，理解 `upy-opt-driver` 和 `upy-slim-driver` 的优化原理

---

## 目录

- [当前 Skill / Plugin 全量导览](#当前-skill--plugin-全量导览)
- [安装方法](#安装方法)
- [一句话造硬件 — AI 嵌入式代码生成流水线](#一句话造硬件--ai-嵌入式代码生成流水线)
- [驱动开发规范化 Skill 列表](#skill-列表)
  - [upy-norm-driver](#upy-norm-driver--驱动文件规范化)
  - [upy-norm-main](#upy-norm-main--测试文件规范化)
  - [upy-gen-main](#upy-gen-main--从-0-生成测试文件)
  - [upy-gen-readme](#upy-gen-readme--从-0-生成-readme)
  - [upy-gen-pkg](#upy-gen-pkg--从-0-生成-packagejson)
  - [upy-norm-pkg](#upy-norm-pkg--驱动包全流程规范化)
  - [upy-deploy-test](#upy-deploy-test--设备部署与验证)
  - [upy-opt-driver](#upy-opt-driver--驱动性能优化)
  - [upy-slim-driver](#upy-slim-driver--驱动内存优化)
  - [upy-pack-driver](#upy-pack-driver--打包成标准目录结构)
  - [upy-pkg-guide](#upy-pkg-guide--器件驱动用法查询)
  - [fetch-doc](#fetch-doc--url-内容获取)
  - [upy-project](#upy-project--micropython-项目端到端生成)
  - [mpremote-device-interaction](#mpremote-device-interaction--设备连接与状态查询)
  - [mpremote-file-transfer](#mpremote-file-transfer--设备文件传输)
  - [mpremote-live-session](#mpremote-live-session--持久连接与输出监控)
- [工作原理](#工作原理)
- [规范文档](#规范文档)
- [版本记录](#版本记录)
- [许可协议](#许可协议)

---

## 安装方法

> **网络受限？** 推荐使用下方的「本地安装」方式，无需网络，直接克隆仓库后复制即可。

### 方式一：本地安装（推荐，无需网络）

**适用场景**：网络受限、离线环境，或已克隆本仓库到本地。

**第一步**：克隆本仓库（或直接下载 ZIP 解压）

```bash
git clone https://github.com/FreakStudioCN/MicroPython_Skills.git
```

**第二步**：将 skill 目录复制到 Claude Code 的 skills 目录

skills 目录固定为 `~/.claude/skills/`，根据操作系统展开如下：

| 系统 | 实际路径 |
|---|---|
| Windows | `C:\Users\<用户名>\.claude\skills\` |
| macOS | `/Users/<用户名>/.claude/skills/` |
| Linux | `/home/<用户名>/.claude/skills/` |

**macOS / Linux**：
```bash
# 安装单个 skill
cp -r MicroPython_Skills/upy-norm-driver ~/.claude/skills/

# 安装全部 skill（在克隆目录内执行）
cd MicroPython_Skills
for skill in upy-analyze upy-select-hw upy-scaffold upy-generate upy-simulate \
             upy-deploy upy-deploy-test upy-autofix upy-wiring upy-diagram upy-gen-driver \
             upy-norm-driver upy-norm-main upy-gen-main upy-gen-readme \
             upy-gen-pkg upy-norm-pkg upy-opt-driver upy-slim-driver upy-pack-driver \
             upy-pkg-guide fetch-doc upy-project review \
             mpremote-device-interaction mpremote-file-transfer mpremote-live-session; do
  cp -r $skill ~/.claude/skills/
done
```

**Windows（PowerShell）**：
```powershell
# 安装单个 skill
Copy-Item -Recurse MicroPython_Skills\upy-norm-driver $env:USERPROFILE\.claude\skills\

# 安装全部 skill（在克隆目录内执行）
cd MicroPython_Skills
$skills = @("upy-analyze","upy-select-hw","upy-scaffold","upy-generate","upy-simulate",
            "upy-deploy","upy-deploy-test","upy-autofix","upy-wiring","upy-diagram","upy-gen-driver",
            "upy-norm-driver","upy-norm-main","upy-gen-main","upy-gen-readme",
            "upy-gen-pkg","upy-norm-pkg","upy-opt-driver","upy-slim-driver","upy-pack-driver",
            "upy-pkg-guide","fetch-doc","upy-project","review",
            "mpremote-device-interaction","mpremote-file-transfer","mpremote-live-session")
foreach ($skill in $skills) {
  Copy-Item -Recurse $skill $env:USERPROFILE\.claude\skills\
}
```

**第三步**：重启 Claude Code，skills 即生效。

---

### 方式二：在线安装（需要网络 + Node.js）

```bash
npx skillfish add FreakStudioCN/MicroPython_Skills upy-norm-driver
npx skillfish add FreakStudioCN/MicroPython_Skills upy-norm-main
npx skillfish add FreakStudioCN/MicroPython_Skills upy-gen-main
npx skillfish add FreakStudioCN/MicroPython_Skills upy-gen-readme
npx skillfish add FreakStudioCN/MicroPython_Skills upy-gen-pkg
npx skillfish add FreakStudioCN/MicroPython_Skills upy-norm-pkg
npx skillfish add FreakStudioCN/MicroPython_Skills upy-opt-driver
npx skillfish add FreakStudioCN/MicroPython_Skills upy-slim-driver
npx skillfish add FreakStudioCN/MicroPython_Skills upy-pack-driver
```

或一键安装全部：

```bash
for skill in upy-norm-driver upy-norm-main upy-gen-main upy-gen-readme \
             upy-gen-pkg upy-norm-pkg upy-opt-driver upy-slim-driver upy-pack-driver; do
  npx skillfish add FreakStudioCN/MicroPython_Skills $skill
done
```

---

## 一句话造硬件 — AI 嵌入式代码生成流水线

用户只需用自然语言描述需求（"做一个温湿度监测仪，超过阈值蜂鸣器报警"），系统自动完成从选型、生成代码、PC仿真、烧录到错误修复的全流程。

### 流水线概览

```
用户说一句话
    ↓
Phase 1: upy-analyze    → 需求解析 + 驱动搜索
Phase 2: upy-select-hw  → MCU 选型 + 引脚分配 + BOM
Phase 3: upy-scaffold   → 项目骨架生成
Phase 4: upy-generate   → 业务代码生成
Phase 4.5: upy-simulate → PC 端全流程模拟（无需硬件）
Phase 5: upy-deploy     → 一键烧录运行
Phase 6: upy-autofix    → 错误分级决策 + 委托修复
Phase 7: upy-wiring     → 接线图生成
       upy-diagram      → 架构图 + 流程图
异常路径: upy-gen-driver → 冷门硬件驱动生成
```

### Skill 清单

| # | Skill | 阶段 | 状态 | 说明 |
|---|-------|------|------|------|
| 1 | `upy-analyze` | Phase 1 | 已落地 | 自然语言 → 器件清单 + 驱动 API 参考 |
| 2 | `upy-select-hw` | Phase 2 | 已落地 | MCU 选型 + 固件核验 + 引脚分配 + BOM |
| 3 | `upy-scaffold` | Phase 3 | 已落地 | 生成 firmware/ 完整骨架（Timer/asyncio/Thread） |
| 4 | `upy-generate` | Phase 4 | 已落地 | 驱动下载 + DI 架构业务代码 + Mock + unittest |
| 5 | `upy-simulate` | Phase 4.5 | 已落地 | PC 端 CLI+rich 全流程模拟（数据发生器 + 多场景） |
| 6 | `upy-deploy` | Phase 5 | 已落地 | mpremote 上传 + 烧录 + 持久会话 + 初判 PASS/FAIL |
| 7 | `upy-autofix` | Phase 6 | 已落地 | 编排协调层：triage.py 采集 → LLM 分级决策 → 委托上游 skill |
| 8 | `upy-wiring` | Phase 7 | 已落地 | 接线图生成（Mermaid .md + SVG + PNG + HTML） |
| 9 | `upy-diagram` | Phase 7 | 已落地 | 架构图 + 流程图 + 数据流图（Mermaid .md + SVG + PNG + HTML） |
| 10 | `upy-gen-driver` | 异常路径 | 已落地 | PDF/Arduino → 调试版驱动 → 硬件验证循环 → 规范化 MPY 驱动 |

**配套支撑：**
- `upy-project-gen-toolchain-spec` — 整体架构文档 + manifest/schema 定义
- `upy-pkg-guide` — 器件驱动用法查询（被 upy-analyze 调用）
- `fetch-doc` — URL 内容获取（被 upy-pkg-guide 调用）

### 各 Skill 简介

#### `/upy-analyze` — 需求解析 + 驱动搜索

输入用户自然语言描述，LLM 拆解意图 → 多关键词并行搜索 upypi + awesome-micropython → 提取驱动 API 参考 → 输出 `project-manifest.json`（phase: analyze）。

#### `/upy-select-hw` — MCU 选型 + 引脚分配

读取 manifest → 根据场景/功耗/网络需求推荐 MCU → I2C 地址冲突检测 → 生成引脚分配表（含电气类型枚举 + 物理引脚编号）→ 输出 BOM 物料清单。

#### `/upy-scaffold` — 项目骨架生成

读取 manifest → AskUserQuestion 选择调度模式（Timer/asyncio/_thread）和可选模块 → 调用 `init_scaffold.py` 生成完整 `firmware/` 骨架（board.py, conf.py, boot.py, main.py, drivers/*, tasks/*, lib/*, tools/*）。

#### `/upy-generate` — 业务代码生成

读取 firmware/ 骨架 + 驱动 API 参考 → 下载驱动 → upy-norm-driver 规范化 → 生成 DI 架构的 task 代码 + conf.py + main.py + Mock 层 + unittest → black + flake8 + pylint 校验。

#### `/upy-simulate` — PC 端全流程模拟

LLM 阅读 firmware/ 全部代码 → 自主设计：调度方案 + 数据发生器 `gen_xxx(tick)` + 可视化（CLI+rich 优先）+ 多场景覆盖 → 生成 `test/pc/sim_main.py` → flake8 + pylint 校验 → 运行。**无需真实硬件即可验证业务逻辑。**

#### `/upy-deploy` — 一键烧录运行

mpremote 上传 firmware/ → 校验文件完整性 → 软复位 + 重连等待 → 持久会话采集输出 → 设备端日志抓取 → 本地规则初判 PASS/FAIL。

#### `/upy-autofix` — 编排协调层

deploy 失败后自动进入。`triage.py` 采集结构化数据（错误解析 + I2C 硬件检测 + git 管理）→ LLM 读取 JSON + 原始日志 → 分级决策（P0~P3）→ 委托上游 skill 修复（generate/select-hw/analyze）→ 可选 PC 验证 → 重新部署。最多 3 次尝试。

#### `/upy-wiring` — 接线图生成

通读 firmware/ 全部 .py 源码提取实际引脚/地址/总线 → 与 manifest 交叉验证 → LLM 生成中间 JSON → 脚本渲染 Mermaid 接线图 .md + SVG + PNG + 自包含 HTML（双击浏览器即看）+ 引脚交叉引用表。

#### `/upy-diagram` — 架构图 + 流程图

扫描 firmware/ 代码结构 + manifest → LLM 生成中间 JSON → 脚本渲染 Mermaid 架构图 + 流程图 + 数据流图，各输出 .md + SVG + PNG + 自包含 HTML（Tabs 切换图表/源码，暗色模式自适应）。支持简单/中等/详细三档复杂度。

#### `/upy-gen-driver` — 驱动代码生成（异常路径）

upypi + GitHub 均无驱动时触发。从 PDF 数据手册或 Arduino 代码提取信息 → LLM 生成调试版单文件驱动（含全量自检逻辑）→ `mpremote resume run` 硬件验证循环（最多 10 轮）→ 脱调试 → `upy-norm-driver` 规范化。可被 `upy-analyze`、`upy-autofix` 或用户直接调用。

---

### `/upy-norm-driver` — 驱动文件规范化

**用途**：将一个能用但不规范的 MicroPython 驱动 `.py` 文件（非 `main.py`），按照 GraftSense 规范进行改写，输出完整规范化后的文件。

**输入**：已有驱动 `.py` 文件路径

**输出**：规范化后的完整 `.py` 文件 + 改写说明表

**覆盖规则**：P0 必改 38 项，P2 可选 7 项，包括：

| 类别 | 主要改写项 |
|---|---|
| 文件结构 | 文件头 7 行注释、4 个模块全局变量、6 个分区标注、分区内容规范 |
| 类设计 | 类结构布局、`__slots__` 优化、避免多重继承、显式依赖注入、常量规范 |
| docstring | 类级中英双语（含 Attributes/Methods/Notes）、方法级中英双语、ISR-safe 标注、副作用标注 |
| 类型注解 | `__init__` 参数注解、公共方法返回值注解、回调用 `callable` |
| 参数校验 | 三种模式：`isinstance`/`hasattr`/值范围，`__init__` 两步校验 |
| 异常处理 | 异常类型规范化、`OSError` 包装重抛（保留 `from e`）、重试机制 |
| ISR 规范 | 禁止内存分配/阻塞IO/抛异常、`micropython.schedule`、并发保护 |
| 函数设计 | 命名约定、返回值设计、`debug` 日志开关 |

**核心约束**：不修改对外 API 名称、方法签名语义、业务逻辑、硬件通信时序。

**使用示例**：
```
/upy-norm-driver sensors/bh1750_driver/code/bh_1750.py
```

---

### `/upy-norm-main` — 测试文件规范化

**用途**：将已有的 `main.py` 测试文件按规范改写，不改变测试逻辑。

**输入**：已有 `main.py` 文件路径

**输出**：规范化后的完整 `main.py`

**P0 必改项（10项）**：

| # | 改写项 |
|---|---|
| 1 | 文件头 7 行注释 |
| 2 | 6 个分区标注注释（顺序正确） |
| 3 | 初始化配置区必须有 `time.sleep(3)` |
| 4 | 初始化配置区必须有 `print("FreakStudio: ...")` |
| 5 | 全局变量区禁止实例化，移至初始化配置区 |
| 6 | `while` 循环只允许在主程序区 |
| 7 | `raise`/`print` 字符串全英文 |
| 8 | 主程序区用 `try/except KeyboardInterrupt/OSError/Exception/finally` 包裹 |
| 9 | `finally` 中调用 `close()`/`deinit()`、`del` 硬件对象、打印退出提示 |
| 10 | 行内注释改为中文 |

**P1 尽量改**：高频函数注释默认调用（供 REPL 手动调用）、三类测试场景覆盖检查。

**使用示例**：
```
/upy-norm-main sensors/bh1750_driver/main.py
```

---

### `/upy-gen-main` — 从 0 生成测试文件

**用途**：给定一个驱动 `.py` 文件，分析其所有公共 API，从 0 生成符合规范的完整 `main.py`。

**输入**：驱动 `.py` 文件路径

**输出**：完整的 `main.py` + API 覆盖说明

**全量覆盖原则**：

按芯片类型功能维度分类所有 API：

| 芯片类型 | 覆盖维度 |
|---|---|
| 传感器类 | 基础状态查询、核心数据采集、参数配置、模式切换、校准补偿 |
| 电机驱动类 | 硬件初始化、动作控制、状态读取、复位/休眠 |
| 通信模块类 | 网络/协议配置、数据收发、状态查询、功耗控制 |
| 存储芯片类 | 数据读写、地址配置、擦除/复位 |
| GPIO/总线扩展类 | 引脚配置、电平读写、中断配置 |

覆盖三类测试场景：正常参数、边界参数（硬件极限值）、异常参数（验证异常是否正确抛出）。

API 处理方式：低频 API 自动执行，高频/模式切换 API 注释调用（供 REPL 手动触发）。

**使用示例**：
```
/upy-gen-main sensors/bh1750_driver/code/bh_1750.py
```

---

### `/upy-gen-readme` — 从 0 生成 README

**用途**：给定一个驱动 `.py` 文件，分析其功能和 API，从 0 生成完整的 `README.md`。

**输入**：驱动 `.py` 文件路径（可选：已有 README 作为参考）

**输出**：完整的 `README.md`

**必须生成的 13 个章节**：

| # | 章节 | 内容 |
|---|---|---|
| 1 | 标题 | `# [芯片名] MicroPython 驱动` |
| 2 | 目录 | 所有章节锚点链接 |
| 3 | 简介 | 驱动作用、功能、适用场景 |
| 4 | 主要特性 | 功能亮点列表 |
| 5 | 硬件要求 | 推荐硬件 + 引脚说明表格 |
| 6 | 软件环境 | 固件版本、依赖库 |
| 7 | 文件结构 | 文件树（`├──` 格式） |
| 8 | 文件说明 | 按文件逐个解释用途 |
| 9 | 快速开始 | 分步说明 + 最小可运行代码示例 |
| 10 | 注意事项 | 工作条件、限制、兼容性 |
| 11 | 版本记录 | 表格：版本号/日期/作者/修改说明 |
| 12 | 联系方式 | 邮箱 + GitHub |
| 13 | 许可协议 | MIT License |

**使用示例**：
```
/upy-gen-readme sensors/bh1750_driver/code/bh_1750.py
```

---

### `/upy-norm-pkg` — 驱动包全流程规范化

**用途**：已有验证过的驱动文件，对整个驱动包目录执行全套规范化流程的 Orchestrator Skill。

**输入**：驱动包目录路径

**输出**：完整规范化的驱动包（所有驱动文件 + main.py + README.md + package.json + 标准目录结构）

**执行流程（6 步）**：

| 步骤 | 操作 |
|---|---|
| 0 | 扫描目录，分类驱动文件与 `main.py`；多驱动文件时列出并询问用户确认范围 |
| 1 | 对每个驱动文件依次执行 `/upy-norm-driver`，每个文件完成后暂停确认 |
| 2 | 执行 `/upy-norm-main`（有 `main.py`）或 `/upy-gen-main`（无 `main.py`） |
| 3 | 执行 `/upy-gen-readme` |
| 4 | 执行 `/upy-gen-pkg` |
| 5 | 执行 `/upy-pack-driver` |
| 6 | 执行 `/upy-deploy-test`（用户确认后上传设备并验证） |

**关键规则**：每步完成后显示 `[步骤 X/6 — skill名称: 文件名 完成]`，暂停等待用户确认再继续。

**使用示例**：
```
/upy-norm-pkg sensors/bh1750_driver/
```

---

### `/upy-deploy-test` — 设备部署与验证

**用途**：`upy-norm-pkg` 完成后，将规范化的驱动文件和 `main.py` 上传到 MicroPython 设备，运行并验证输出。

**输入**：规范化后的 `code/` 目录路径 + 用户确认的 COM 端口

**输出**：上传进度 + 验证报告（成功/失败 + 错误分析）

**执行流程（6 步）**：

| 步骤 | 操作 |
|---|---|
| 0 | 询问并确认 COM 端口（可执行 `mpremote connect list` 辅助） |
| 1 | 扫描待上传文件（`.py` 文件 + 子包目录） |
| 2 | 逐文件上传（`mpremote connect <COM> resume fs cp`） |
| 3 | 验证设备文件完整性（`fs ls`） |
| 4 | 运行 `main.py`（`mpremote resume run main.py`） |
| 5 | 分析输出，输出验证报告 |

**失败诊断**：`ImportError` → 文件缺失；`OSError -110` → I2C 接线；`RuntimeError: WiFi` → 检查凭证占位符是否已替换。

**mpremote 参考**：`/mpremote-device-interaction`、`/mpremote-file-transfer`、`/mpremote-live-session`、[官方文档](https://docs.micropython.org/en/latest/reference/mpremote.html)

**使用示例**：
```
/upy-deploy-test bh1750_driver/code/
```

---

### `/upy-opt-driver` — 性能优化

**用途**：对任意 MicroPython `.py` 文件（驱动文件、`main.py` 或其他文件），按 GraftSense 性能优化指南改写，聚焦**执行速度**提升。

**输入**：驱动 `.py` 文件路径或目录路径（支持多文件批量优化）

**输出**：优化后的完整 `.py` 文件 + 优化说明表

**优化优先级**：

| 优先级 | 项目 | 典型提速 |
|---|---|---|
| P0 | 预分配缓冲区 | 消除 GC 抖动 |
| P0 | `memoryview` 切片 | 零拷贝（> 32 字节） |
| P0 | 缓存对象引用 | 5–20%（循环 > 100 次） |
| P0 | `const()` 常量 | 零开销 |
| P1 | 手动 GC 控制 | 可控延迟 |
| P1 | `@native` 装饰器 | ~2 倍 |
| P1 | `@viper` 装饰器 | ~58 倍（整数运算） |
| P1 | 整数替代浮点 | ~57%（无 FPU 芯片） |
| P2 | `viper ptr8/ptr16/ptr32` | ~23 倍（大循环遍历） |
| P2 | SIO 寄存器直写 | ~48%（RP2040 专属） |
| P2 | `array` 替代 `list` | 连续内存 |

**核心约束**：`@viper` 改写必须标注整数溢出风险；`@native` 必须标注限制（无生成器/关键字参数）；SIO 寄存器必须标注"RP2040 专属"。

**使用示例**：
```
/upy-opt-driver sensors/bh1750_driver/code/bh_1750.py
/upy-opt-driver sensors/bh1750_driver/code/
```

---

### `/upy-slim-driver` — 内存优化

**用途**：对任意 MicroPython `.py` 文件（驱动文件、`main.py` 或其他文件），按 GraftSense 内存最小化指南改写，聚焦**RAM 占用**降低。

**输入**：驱动 `.py` 文件路径或目录路径（支持多文件批量优化）

**输出**：优化后的完整 `.py` 文件 + 优化说明表

**优化优先级**：

| 优先级 | 项目 | 典型节省 |
|---|---|---|
| P0 | 预分配缓冲区 | 消除峰值堆分配 |
| P0 | 私有 `_CONST` | ~40 字节/常量 |
| P0 | 避免循环字符串 `+` | 消除临时对象 |
| P0 | `bytes`/`bytearray` 替代 `list` | ~90%（寄存器表） |
| P1 | `gc.collect()` 前置 | 降低随机性 |
| P1 | `gc.disable()`/`gc.enable()` | 防止 GC 中途打断 |
| P1 | `struct.pack_into()` | 消除临时 bytes |
| P2 | `__slots__` | 50–200 字节/实例 |
| P2 | 生成器替代列表 | 峰值 RAM O(N)→O(1) |

**核心约束**：`_CONST` 改写仅适用于模块内部常量；`gc.disable()` 区间必须短且有界，禁止包含阻塞 I/O；与 `upy-opt-driver` 的 P0#1（预分配缓冲区）重叠，不重复执行。

**使用示例**：
```
/upy-slim-driver sensors/bh1750_driver/code/bh_1750.py
/upy-slim-driver sensors/bh1750_driver/code/
```

---

### `/upy-pack-driver` — 打包成标准目录结构

**用途**：在其他 Skill 执行完毕后，将驱动文件、`main.py`、`README.md`、`package.json` 组织成标准驱动包目录结构，并生成 `LICENSE` 文件。

**输入**：驱动 `.py` 文件路径（同目录下须已有 `main.py`、`README.md`、`package.json`）

**输出**：标准目录结构：
```
<chip>_driver/
├── code/
│   ├── <chip>.py
│   └── main.py
├── package.json
├── README.md
└── LICENSE
```

**核心约束**：不生成任何内容，只负责组织文件；缺失文件会提示先运行对应 Skill。

**使用示例**：
```
/upy-pack-driver bmp280.py
```

---

### `/upy-pkg-guide` — 器件驱动用法查询

**用途**：给定一个器件名称，从 upypi 自动获取对应驱动包的所有文件，综合分析后输出使用要点。

**输入**：器件/芯片名称（如 BMP280、DS18B20、MPR121）

**输出**：包信息、安装命令、初始化示例、核心 API 表格、注意事项

**执行流程**：curl 搜索 upypi → 获取 package.json → 并行下载驱动.py + main.py + README.md → 综合输出

**使用示例**：
```
/upy-pkg-guide BMP280
/upy-pkg-guide DS18B20
```

---

### `/fetch-doc` — URL 内容获取

**用途**：给定任意 URL，自动获取内容并提取关键信息。支持 GitHub 文件、upypi 包页面、普通网页。

**输入**：URL（GitHub blob 链接自动转换为 raw URL）

**输出**：根据内容类型提取关键信息（README 摘要、驱动 API 表格、package.json 字段等）

**依赖**：需要 Python + requests 库（`pip install requests`）

**使用示例**：
```
/fetch-doc https://github.com/FreakStudioCN/GraftSense-Drivers-MicroPython/blob/main/sensors/bmp280_driver/README.md
```

---

### `/review` — MicroPython 代码审查

**用途**：基于 MicroPython 维护者历史审查模式（~19.5K 条分类审查评论），对 MPY 驱动代码进行 AI 辅助审查。

**输入**：MicroPython 代码变更（分支、commit、diff、PR）

**输出**：语义搜索匹配的历史审查模式 + 审查上下文建议

**核心能力**：
- 语义搜索 ~19.5K 条分类审查评论，找到相关历史审查模式
- 支持 MCP server（`review_diff`、`search_reviews` 等工具）和 CLI 两种方式
- MCP server 保持 embedding model 预热，消除每次查询 2-3s 冷启动

**使用示例**：
```
/review 审查当前分支对 main 的 diff
/review 检查 sensors/bmp280_driver/code/bmp280.py
```

---

### `/upy-project` — MicroPython 项目端到端生成

**用途**：用户描述项目需求，自动完成从需求澄清、器件选型、代码生成到设备调试的全流程。

**输入**：项目描述（主控型号、传感器列表、功能需求、串口端口）

**输出**：完整项目代码（`xx_task.py` + `main.py`）+ mpremote 自动调试

**执行流程（5 阶段）**：

| 阶段 | 操作 |
|---|---|
| 前置检查 | 验证 mpremote 可用性 |
| 阶段0 | 解析用户输入中的 GitHub 链接（调用 fetch-doc skill） |
| 阶段1 | 一次性列出所有缺失信息，不多轮追问 |
| 阶段2 | 从 upypi 选型器件，调用 upy-pkg-guide 获取 API 用法 |
| 阶段3 | 生成 task 文件 + main.py（统一调度） |
| 阶段4 | mpremote 自动调试，最多 3 次，解析输出并修复 |

**代码结构**：
```
/lib/<driver>.py       ← 从 upypi 下载
<功能>_task.py         ← 单一功能模块（含 init() + run()）
main.py                ← 统一调度
```

**使用示例**：
```
/upy-project 用ESP32和BMP280做一个温度监控，每5秒打印一次，COM3口
```

---

### `/upy-gen-pkg` — 从 0 生成 package.json

**用途**：给定一个驱动目录或驱动文件，分析结构和依赖，从 0 生成符合规范的 `package.json`。

**输入**：驱动目录路径或驱动 `.py` 文件路径

**输出**：完整的 `package.json` + 三种安装方式命令

**依赖处理三步优先级**：

```
1. MicroPython 内置模块（machine、time、sys 等）→ 不写入 deps
2. micropython-lib 标准库 → 用 mip 标准格式
3. 其他第三方依赖 → 查询 https://upypi.net/api/search?q={依赖名}
   有结果 → 用 upypi URL 写入 deps
   无结果 → 用 github: 占位格式，标注 ⚠️ 需手动确认
```

**使用示例**：
```
/upy-gen-pkg sensors/bh1750_driver/
```

---

### `/mpremote-device-interaction` — 设备连接与状态查询

**用途**：通过 mpremote 连接 MicroPython 设备，执行代码，查询设备状态（内存、固件版本、文件列表等）。

**平台支持**：Windows（COMn）、macOS（/dev/tty.usbmodem*）、Linux（mpy-dev 或 /dev/serial/by-id/）

**核心原则**：连接运行中的设备必须使用 `resume`，否则触发软重置打断程序。

**覆盖场景**：

| 场景 | 命令示例 |
|---|---|
| 列出可用设备 | `mpremote connect list` |
| Windows 连接 | `mpremote c3 resume` / `mpremote connect COM3 resume` |
| macOS 连接 | `mpremote connect /dev/tty.usbmodem1101 resume` |
| Linux 连接 | `mpremote connect $(mpy-dev tty my-board) resume` |
| 查询固件版本 | `mpremote <device> resume exec "import sys; print(sys.version)"` |
| 查询空闲内存 | `mpremote <device> resume exec "import gc; gc.collect(); print(gc.mem_free())"` |
| 软重置 | `mpremote <device> soft-reset` |

**使用示例**：
```
/mpremote-device-interaction  连接 COM3，查看固件版本和空余内存
```

---

### `/mpremote-file-transfer` — 设备文件传输

**用途**：使用 mpremote 在本地与设备之间复制文件，管理设备文件系统（ls、mkdir、rm、tree）。

**平台支持**：Windows、macOS、Linux，各平台设备路径写法详见 Skill 内。

**关键规则**：文件操作必须加 `resume`，否则每次操作前都会软重置设备。

**覆盖场景**：

| 场景 | 命令示例 |
|---|---|
| 上传文件 | `mpremote <device> resume fs cp main.py :main.py` |
| 下载文件 | `mpremote <device> resume fs cp :main.py .` |
| 递归同步目录 | `mpremote <device> resume fs cp -r utils/ :utils/` |
| 更新驱动后重启 | `mpremote <device> resume fs cp driver.py :driver.py + soft-reset repl` |
| 列出文件 | `mpremote <device> resume fs ls :` |
| 查看存储空间 | `mpremote <device> resume exec "import os; print(os.statvfs('/'))"` |

**使用示例**：
```
/mpremote-file-transfer  把本地 utils/ 目录同步到设备，然后重启监控
```

---

### `/mpremote-live-session` — 持久连接与输出监控

**用途**：对设备建立持久连接，持续发送命令并捕获输出。适用于运行 asyncio 的设备、压力测试、长时间监控。

**平台支持**：Linux/macOS 使用 PTY 方案；Windows 使用 subprocess pipe 替代方案（有局限，见 Skill 内说明）。

**核心原则**：反复调用 `mpremote resume exec` 会对 asyncio 设备发送 Ctrl+C，杀死事件循环；必须用持久 session 替代。

**何时使用**：

| 场景 | 推荐方案 |
|---|---|
| 单次快速查询 | `mpremote <device> resume exec "..."` |
| 多命令序列 / 监控输出 | 本 Skill（持久 session） |
| 设备运行 asyncio/aiorepl | 本 Skill（必须） |
| 文件拷贝 | mpremote-file-transfer |

**使用示例**：
```
/mpremote-live-session  对 /dev/tty.usbmodem1101 建立持久连接，每秒查询一次内存并记录到文件
```

---

## 工作原理

每个 Skill 是一个 `SKILL.md` 文件，包含：

- **角色定位**：告诉 AI 扮演什么角色
- **核心约束**：明确不能修改什么
- **改写优先级表**：P0 必改 / P2 可选，每项对应规范文档具体章节
- **关键规范摘要**：内嵌最重要的代码模板，避免每次查阅完整规范文档

### 触发流程

```
用户输入 /upy-norm-driver xxx.py
    ↓
Claude 加载 SKILL.md 中的规范摘要和优先级表
    ↓
读取目标文件，分析结构（通信接口类型、类、方法、ISR 回调等）
    ↓
按 P0→P2 优先级逐项改写（不改变 API 和业务逻辑）
    ↓
输出完整规范化文件 + 改写说明表
```

### 为什么拆成多个 Skill

规范文档 22 章、2200+ 行，单个 Skill 内嵌全部规范会导致上下文过长、改写质量下降。按"改写对象"和"优化目标"拆分后，每个 Skill 只内嵌对应章节的规范摘要，上下文可控。

**Skill 分类**：
- **AI 代码生成流水线**（10 个）：`upy-analyze`、`upy-select-hw`、`upy-scaffold`、`upy-generate`、`upy-simulate`、`upy-deploy`、`upy-autofix`、`upy-wiring`、`upy-diagram`、`upy-gen-driver`
- **代码审查**：`review`（mpy-review，MPY 驱动代码审查）
- **规范化**：`upy-norm-driver`、`upy-norm-main`、`upy-norm-pkg`（Orchestrator）
- **生成**：`upy-gen-main`、`upy-gen-readme`、`upy-gen-pkg`
- **优化**：`upy-opt-driver`（性能）、`upy-slim-driver`（内存）
- **打包**：`upy-pack-driver`
- **项目生成**：`upy-project`（端到端）
- **工具**：`upy-pkg-guide`（器件用法）、`fetch-doc`（URL 内容获取）

---

## 规范文档

完整规范见：[upy_driver_dev_spec_summary.md](https://github.com/FreakStudioCN/GraftSense-Drivers-MicroPython/blob/main/upy_driver_dev_spec_summary.md)

---

## 版本记录

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| v1.0.0 | 2026-04-24 | leezisheng | 初始版本，包含 5 个 skill |
| v1.1.0 | 2026-04-26 | leezisheng | 新增 upy-pack-driver；upy-norm-driver 补充 16a/16b/16c；统一许可证为 MIT；I2C 扫描规范 |
| v1.2.0 | 2026-04-27 | leezisheng | 新增 upy-norm-pkg（Orchestrator）、upy-opt-driver（性能优化）、upy-slim-driver（内存优化）；完善多文件批量处理模式 |
| v1.3.0 | 2026-04-29 | leezisheng | 新增 upy-pkg-guide（器件用法查询）、fetch-doc（URL 内容获取）、upy-project（项目端到端生成）；upy-gen-pkg 查询逻辑改为 Bash curl 自动执行 |
| v1.4.0 | 2026-05-04 | leezisheng | 新增 mpremote-device-interaction、mpremote-file-transfer、mpremote-live-session；基于 andrewleech/claude-mpy-marketplace 架构，补充 Windows（COMn）和 macOS 平台支持 |
| v1.5.0 | 2026-05-14 | leezisheng | 新增 upy-deploy-test（设备部署与验证）；upy-norm-pkg 新增第6步调用 upy-deploy-test；各 skill 新增中间件库类型判断分支及敏感数据替换规则 |
| v1.6.0 | 2026-06-02 | leezisheng | 新增"一句话造硬件"AI 代码生成流水线（10 个 skill）：analyze/select-hw/scaffold/generate/simulate/deploy/autofix/wiring/diagram/cold-driver + 整体架构文档。upy-simulate 改为 CLI+rich 优先。upy-select-hw 增加引脚电气类型枚举 + 物理引脚规则。Skill 总数从 15 增至 25。 |
| v1.7.0 | 2026-06-03 | leezisheng | upy-cold-driver 重命名为 upy-gen-driver，定位为独立可调用 skill（非仅异常路径）。upy-gen-driver 流程落地：调试版驱动 → mpremote 硬件验证循环 → 脱调试 → 规范化。upy-wiring + upy-diagram 新增 HTML 输出（自包含浏览器页面，Mermaid.js CDN + Tab 切换），--format all 现在输出 md + svg + png + html 全部四种格式。全部 25 个 skill 补全 .skillfish.json。 |
| v1.7.1 | 2026-06-03 | leezisheng | README.md 安装脚本补充 upy-deploy-test + review skill。功能规划.md 修复：模块四可视化方案（Pillow→Mermaid）、模块七 gen-driver 流程补充硬件验证环、triage.py 行数修正、项目架构脚本名刷新、/cold-driver→/gen-driver。 |
| v1.8.0 | 2026-07-05 | leezisheng | README.md 新增当前 Skill / Plugin 全量导览，明确插件版 8 流程：`upy-analyze-plugin`、`upy-select-hw-plugin`、`upy-flash-mpy-firmware-plugin`、`upy-scaffold-plugin`、`upy-generate-plugin`、`upy-deploy-plugin`、`upy-wiring-plugin`、`upy-diagram-plugin`；补充 `upy-gen-driver-plugin` 为缺失硬件驱动分支，并区分插件版 Skill/plugin 与 Classic Skill。 |

---

## 许可协议

MIT License

Copyright (c) 2026 leezisheng

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
