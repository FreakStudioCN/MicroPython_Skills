# MicroPython Skills for GraftSense

GraftSense MicroPython 驱动开发规范化 Skill 集合，基于 [GraftSense-Drivers-MicroPython](https://github.com/FreakStudioCN/GraftSense-Drivers-MicroPython) 仓库的完整编写规范（22章、2200+ 行）构建。

提供 5 个专用 Skill，覆盖 MicroPython 驱动开发的完整工作流：驱动规范化、测试文件规范化/生成、README 生成、package.json 生成。

---

## 目录

- [安装方法](#安装方法)
- [Skill 列表](#skill-列表)
  - [upy-norm-driver](#upy-norm-driver--驱动文件规范化)
  - [upy-norm-main](#upy-norm-main--测试文件规范化)
  - [upy-gen-main](#upy-gen-main--从-0-生成测试文件)
  - [upy-gen-readme](#upy-gen-readme--从-0-生成-readme)
  - [upy-gen-pkg](#upy-gen-pkg--从-0-生成-packagejson)
- [工作原理](#工作原理)
- [规范文档](#规范文档)
- [版本记录](#版本记录)
- [许可协议](#许可协议)

---

## 安装方法

### 前置要求

- [Claude Code](https://claude.ai/code) 已安装
- Node.js 已安装（用于 npx）

### 安装单个 Skill

```bash
npx skillfish add leezisheng/MicroPython_Skills upy-norm-driver
npx skillfish add leezisheng/MicroPython_Skills upy-norm-main
npx skillfish add leezisheng/MicroPython_Skills upy-gen-main
npx skillfish add leezisheng/MicroPython_Skills upy-gen-readme
npx skillfish add leezisheng/MicroPython_Skills upy-gen-pkg
```

### 安装全部 Skill

```bash
for skill in upy-norm-driver upy-norm-main upy-gen-main upy-gen-readme upy-gen-pkg; do
  npx skillfish add leezisheng/MicroPython_Skills $skill
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
| 13 | 许可协议 | 区分官方模块（MIT）与自编驱动（CC BY-NC 4.0） |

**使用示例**：
```
/upy-gen-readme sensors/bh1750_driver/code/bh_1750.py
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

### 为什么拆成 5 个 Skill

规范文档 22 章、2200+ 行，单个 Skill 内嵌全部规范会导致上下文过长、改写质量下降。按"改写对象"拆分后，每个 Skill 只内嵌对应章节的规范摘要，上下文可控。

---

## 规范文档

完整规范见：[upy_driver_dev_spec_summary.md](https://github.com/FreakStudioCN/GraftSense-Drivers-MicroPython/blob/main/upy_driver_dev_spec_summary.md)

---

## 版本记录

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| v1.0.0 | 2026-04-24 | leezisheng | 初始版本，包含 5 个 skill |

---

## 许可协议

MIT License

Copyright (c) 2026 leezisheng

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
