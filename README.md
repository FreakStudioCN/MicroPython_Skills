# MicroPython Skills for GraftSense

GraftSense MicroPython 驱动开发规范化 Skill 集合，基于 [GraftSense-Drivers-MicroPython](https://github.com/FreakStudioCN/GraftSense-Drivers-MicroPython) 仓库的完整编写规范（22章、2200+ 行）构建。

提供 8 个专用 Skill，覆盖 MicroPython 驱动开发的完整工作流：驱动规范化、测试文件规范化/生成、README 生成、package.json 生成、性能优化、内存优化、打包整理。

---

## 目录

- [安装方法](#安装方法)
- [Skill 列表](#skill-列表)
  - [upy-norm-driver](#upy-norm-driver--驱动文件规范化)
  - [upy-norm-main](#upy-norm-main--测试文件规范化)
  - [upy-gen-main](#upy-gen-main--从-0-生成测试文件)
  - [upy-gen-readme](#upy-gen-readme--从-0-生成-readme)
  - [upy-gen-pkg](#upy-gen-pkg--从-0-生成-packagejson)
  - [upy-norm-pkg](#upy-norm-pkg--驱动包全流程规范化)
  - [upy-opt-driver](#upy-opt-driver--驱动性能优化)
  - [upy-slim-driver](#upy-slim-driver--驱动内存优化)
  - [upy-pack-driver](#upy-pack-driver--打包成标准目录结构)
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
for skill in upy-norm-driver upy-norm-main upy-gen-main upy-gen-readme \
             upy-gen-pkg upy-norm-pkg upy-opt-driver upy-slim-driver upy-pack-driver; do
  cp -r $skill ~/.claude/skills/
done
```

**Windows（PowerShell）**：
```powershell
# 安装单个 skill
Copy-Item -Recurse MicroPython_Skills\upy-norm-driver $env:USERPROFILE\.claude\skills\

# 安装全部 skill（在克隆目录内执行）
cd MicroPython_Skills
$skills = @("upy-norm-driver","upy-norm-main","upy-gen-main","upy-gen-readme",
            "upy-gen-pkg","upy-norm-pkg","upy-opt-driver","upy-slim-driver","upy-pack-driver")
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

## Skill 列表

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

**执行流程（5 步）**：

| 步骤 | 操作 |
|---|---|
| 0 | 扫描目录，分类驱动文件与 `main.py`；多驱动文件时列出并询问用户确认范围 |
| 1 | 对每个驱动文件依次执行 `/upy-norm-driver`，每个文件完成后暂停确认 |
| 2 | 执行 `/upy-norm-main`（有 `main.py`）或 `/upy-gen-main`（无 `main.py`） |
| 3 | 执行 `/upy-gen-readme` |
| 4 | 执行 `/upy-gen-pkg` |
| 5 | 执行 `/upy-pack-driver` |

**关键规则**：每步完成后显示 `[步骤 X/5 — skill名称: 文件名 完成]`，暂停等待用户确认再继续。

**使用示例**：
```
/upy-norm-pkg sensors/bh1750_driver/
```

---

### `/upy-opt-driver` — 驱动性能优化

**用途**：已规范化的驱动文件，按 GraftSense 性能优化指南改写，聚焦**执行速度**提升。

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

### `/upy-slim-driver` — 驱动内存优化

**用途**：已规范化的驱动文件，按 GraftSense 内存最小化指南改写，聚焦**RAM 占用**降低。

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

### 为什么拆成 9 个 Skill

规范文档 22 章、2200+ 行，单个 Skill 内嵌全部规范会导致上下文过长、改写质量下降。按"改写对象"和"优化目标"拆分后，每个 Skill 只内嵌对应章节的规范摘要，上下文可控。

**Skill 分类**：
- **规范化**：`upy-norm-driver`、`upy-norm-main`、`upy-norm-pkg`（Orchestrator）
- **生成**：`upy-gen-main`、`upy-gen-readme`、`upy-gen-pkg`
- **优化**：`upy-opt-driver`（性能）、`upy-slim-driver`（内存）
- **打包**：`upy-pack-driver`

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

---

## 许可协议

MIT License

Copyright (c) 2026 leezisheng

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
