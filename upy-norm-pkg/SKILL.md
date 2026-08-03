---
name: upy-norm-pkg
description: Use this skill when the user wants to normalize/standardize an existing validated MicroPython driver package (one or more driver .py files, optional main.py) according to the GraftSense coding spec. Invoke when user says things like "规范化驱动包", "norm pkg", "对整个驱动目录规范化", or provides a driver directory path and asks for full normalization.
---

# MicroPython 驱动包全流程规范化 Skill

## 角色定位

你是 GraftSense MicroPython 驱动包规范化助手。给定一个包含已验证驱动文件的目录，按固定流程对所有文件进行规范化，并生成缺失的配套文件，最终输出标准驱动包目录结构。

## 类型判断（第0步扫描完成后立即执行，后续所有步骤按类型走对应分支）

| 判断条件 | 类型 |
|---|---|
| 驱动位于 `middleware/` 子目录，或导入了 `network`/`urequests`/`AsyncWebsocketClient`/`asyncio` 且无 I2C/SPI/UART 硬件总线操作 | **中间件库** |
| 其他情况 | **硬件驱动** |

判断后输出：
```
包类型：中间件库（middleware） / 硬件驱动
分类建议（中间件库）：middleware/protocol 或 middleware/network 等
后续步骤将使用对应规则分支
```

**本 Skill 是以下 Skill 的 Orchestrator，不自行生成内容，只负责按顺序调用：**
- `/upy-norm-driver` — 驱动文件规范化
- `/upy-norm-main` 或 `/upy-gen-main` — 测试文件规范化或生成
- `/upy-gen-readme` — README 生成
- `/upy-gen-pkg` — package.json 生成
- `/upy-pack-driver` — 打包整理目录结构

## 执行步骤

### 第 0 步：扫描目录

1. 扫描用户指定目录下所有 `.py` 文件及子目录
2. 分类：
   - **驱动文件**：同级目录下的 `.py` 文件，排除 `main.py`
   - **子包依赖目录**：同级目录下含 `__init__.py` 的子目录（不作为驱动文件处理，将在 gen-pkg 步骤查询 upypi 并写入 `deps`）
   - **测试文件**：`main.py`（若存在）
   - **示例/临时测试文件**：`test_*.py`、`*_test.py`、`demo_*.py` 不得混在 `code/` 运行包中；必须移动到 `examples/`、合并进规范 `main.py`，或在发布策略中显式说明
3. 输出扫描结果：
   ```
   目录：G:/ens160_project/
   驱动文件（1个）：ens160sciosense.py
   子包依赖目录（1个）：sensor_pack_2/  ← 含 __init__.py，gen-pkg 步骤将查询 upypi
   测试文件：main.py ✓（已存在，将执行 norm-main）
   ```
3a. 判断包类型：
    扫描驱动文件 import，若符合中间件库特征（见 upy-norm-driver 类型判断规则），输出：
    ```
    包类型：中间件库（middleware）
    分类建议：middleware/protocol 或 middleware/network 等
    后续步骤将使用中间件库规则分支
    ```
    并在后续每步调用对应 skill 时传入类型标记（中间件库）。
   若无子包目录：
   ```
   目录：G:/bmp280/
   驱动文件（2个）：bmp280_float.py、bmp280_int.py
   子包依赖目录：无
   测试文件：main.py ✓（已存在，将执行 norm-main）
   ```
   若无 `main.py`：
   ```
   测试文件：未找到（将执行 gen-main，基于第一个驱动文件生成）
   ```
4. 若驱动文件多于 1 个，列出所有文件并询问：
   ```
   发现多个驱动文件，将依次对每个文件执行 norm-driver：
   1. bmp280_float.py
   2. bmp280_int.py
   确认全部执行，还是只选其中某个？
   ```
5. 用户确认后进入第 1 步

### 第 1 步：norm-driver（逐文件）

对每个驱动文件依次执行 `/upy-norm-driver`：
- 执行完成后暂停，显示：
  ```
  [步骤 1/5 — norm-driver: bmp280_float.py 完成]
  确认写入并继续下一个文件？还是需要修改？
  ```
- 用户确认写入后，若还有其他驱动文件，继续下一个
- 所有驱动文件完成后，进入第 2 步

### 第 2 步：norm-main 或 gen-main

- **有 `main.py`**：执行 `/upy-norm-main`
- **无 `main.py`**：执行 `/upy-gen-main`（基于目录中第一个驱动文件）

执行完成后暂停：
```
[步骤 2/5 — main.py 完成]
确认写入并继续？
```

### 第 3 步：gen-readme

执行 `/upy-gen-readme`（传入目录中第一个驱动文件路径）。

执行完成后暂停：
```
[步骤 3/5 — README.md 完成]
确认写入并继续？
```

### 第 4 步：gen-pkg

执行 `/upy-gen-pkg`（传入驱动目录路径）。

执行完成后暂停：
```
[步骤 4/5 — package.json 完成]
确认写入并继续？
```

### 第 5 步：pack-driver

执行 `/upy-pack-driver`（传入目录中第一个驱动文件路径）。

执行完成后输出：
```
[步骤 5/6 — 打包完成]
<chip>_driver/
├── code/
│   ├── <chip>.py        ✓
│   ├── main.py          ✓
│   └── <subpkg>/        ✓ (若存在子包)
├── package.json         ✓
├── README.md            ✓
└── LICENSE              ✓ (generated)
```

询问用户："是否继续进行设备部署与验证？"，用户确认后进入第 6 步。


### 第 5a 步：最终验收门禁（必须通过）

打包完成后立即执行最终验收；任一失败都必须回到对应步骤修复，不得输出“完成”或进入部署：
1. 运行仓库 `code_checker.py -r <driver_package>/code`，必须 0 fail。
2. AST/文本分区检查：所有 `.py` 文件 6 个分区标注必须缩进 0、顺序严格、无缺失、无重复；`main.py` 的 `主程序` 标记不得在 `def main()` 内。
3. 类型注解检查：`__init__` 所有参数和 `-> None`、公共方法参数/返回、property setter 参数、main.py helper 函数参数/返回均完整。
4. package.json 检查：`name` 与目录名一致；`urls` 无前导 `/` 或绝对路径；source 文件 exact-case 存在；运行时 `.py` 文件和本地 import 均被 urls/deps 覆盖。
5. README/package/license 检查：README 快速开始只引用已通过验收的 `main.py`；`author`/`license`/`LICENSE` 与来源一致；测试/demo 文件边界清晰。

### 第 6 步：deploy-test

执行 `/upy-deploy-test`（传入打包后的 `code/` 目录路径）。

执行完成后输出：
```
[步骤 6/6 — 设备验证完成]
```

## 中断与恢复

用户在任意步骤回复"修改"或"重做"时，重新执行当前步骤，不影响已完成步骤。

## 输出格式

每步开始前显示进度：`[步骤 X/6 — skill名称: 文件名]`
每步完成后暂停等待用户确认，再进入下一步。

## 上下文控制

**每步用户确认写入文件后，不得在对话中保留该文件的完整内容。** 仅保留一行摘要，格式：
```
已写入 <文件名>，共 <N> 行，<执行项简述>
```
例如：`已写入 bmp280.py，共 312 行，P0 全部执行，P2 执行 bytearray 复用缓冲区`

后续步骤不得引用或重新展开已写入文件的内容。

## 完整规范参考

[完整规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)

## 自省与进化

每次执行完成后，检查是否遇到以下情况：
- 规则未覆盖的边界情况
- 用户指出的输出错误或规则缺陷
- 新发现的约束需求

若有，立即执行：
1. 将新规则追加到本文件对应章节
2. 将相同修改同步写入 `G:/MicroPython_Skills/upy-norm-pkg/SKILL.md`
3. 在 `G:/MicroPython_Skills/` 目录执行：
   `git add upy-norm-pkg/SKILL.md && git commit -m "skill(upy-norm-pkg): <规则描述>"`
