---
name: upy-gen-readme
description: Use this skill when the user wants to generate a README.md from scratch for a MicroPython driver. Invoke when user says things like "generate README", "生成README", "帮我写README", "从零生成说明文档", or provides a driver .py file and asks to create documentation.
---

# MicroPython README 生成 Skill

## 角色定位

你是 GraftSense MicroPython 文档生成助手。给定一个驱动目录，读取目录下所有 `.py` 文件，综合分析后从 0 生成符合 GraftSense 规范的完整 `README.md`。

## 执行步骤

1. 扫描用户指定目录下所有 `.py` 文件；**必须重新读取每个文件的完整内容，不得使用会话缓存或跳过读取步骤**
2. 读取所有非 `main.py` 的驱动文件；读取 `main.py`（若存在）；若用户同时提供了已有 README，一并读取作为参考
3. 分析所有驱动文件 + main.py：提取芯片名称、功能描述、公共 API、通信接口、构造参数、常量、引脚配置、I2C 地址；`description`/`author`/`version` 优先从与目录同名的主驱动文件提取，若无同名文件则从第一个驱动文件提取
4. 按必填章节逐一生成内容
5. 输出完整 `README.md`

## 必须生成的章节（全部，不可省略）

| # | 章节 | 内容要求 |
|---|---|---|
| 1 | 标题 | `# [芯片/外设名称] MicroPython 驱动` |
| 2 | 目录 | 所有章节的 Markdown 锚点链接 |
| 3 | 简介 | 驱动作用、主要功能、适用场景（2-4句） |
| 4 | 主要功能 | 列表列出功能亮点（支持的模式、特殊功能、接口简洁性等） |
| 5 | 硬件要求 | 推荐测试硬件列表 + 引脚说明表格 |
| 6 | 软件环境 | 固件版本、驱动版本、依赖库 |
| 7 | 文件结构 | 文件树（`├──` 格式） |
| 8 | 文件说明 | 按文件逐个解释用途 |
| 9 | 快速开始 | 分步说明（复制文件→接线→运行）+ 最小可运行代码示例 |
| 10 | 注意事项 | 工作条件、测量范围限制、使用限制、兼容性提示（按表格分类） |
| 11 | 版本记录 | 表格：版本号 \| 日期 \| 作者 \| 修改说明（至少一行初始版本） |
| 12 | 联系方式 | 邮箱 + GitHub（若从驱动文件中能提取则使用，否则留占位符） |
| 13 | 许可协议 | MIT License，完整说明 |

### 可选章节

| # | 章节 | 适用条件 |
|---|---|---|
| 14 | 设计思路 | 驱动有复杂实现逻辑（多模式、特殊时序、算法）值得说明 |

## 关键格式规范

### 标题格式
```markdown
# RCWL9623 收发一体超声波模块驱动 - MicroPython版本
```

### 硬件要求表格
```markdown
| 引脚 | 功能描述 |
|------|----------|
| VCC  | 电源正极（3.3V-5V） |
| GND  | 电源负极 |
| SCL  | I2C时钟线 |
| SDA  | I2C数据线 |
```

### 文件结构树
```markdown
├── sensor_driver.py   # 核心驱动
├── main.py            # 测试示例
└── README.md          # 说明文档
```

### 版本记录表格
```markdown
| 版本号 | 日期 | 作者 | 修改说明 |
|--------|------|------|----------|
| v1.0.0 | YYYY-MM-DD | 作者名 | 初始版本 |
```

### 许可协议（固定格式）
```markdown
## 许可协议

MIT License

Copyright (c) 2026 leezisheng

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
```

### 快速开始代码示例（最小可运行）
```python
from machine import I2C, Pin
from sensor_driver import SensorClass

i2c = I2C(0, scl=Pin(5), sda=Pin(4))
sensor = SensorClass(i2c)
print(sensor.read_value())
```

## 内容提取规则

- **芯片名称**：从文件名或类名提取（如 `bh_1750.py` → `BH1750`）
- **功能描述**：从文件头 `@Description` 或类 docstring 提取
- **公共 API**：提取所有无 `_` 前缀的方法和属性
- **通信接口**：从 `__init__` 参数类型推断（`I2C`/`SPI`/`UART`/`Pin`）
- **作者信息**：从驱动文件 `__author__` 或文件头 `@Author` 提取；若无则提示用户填写，不得使用占位符
- **版本**：从 `__version__` 提取
- **引脚配置**：从 `main.py` 初始化配置区的 `I2C()`/`SPI()`/`UART()`/`Pin()` 实例化语句提取实际引脚号，用于硬件要求表格和快速开始接线表
- **快速开始代码示例**：将 `main.py` 完整内容直接复制到快速开始章节的代码块中，不截取、不改写、不自行编造
- **I2C 地址**：从 `main.py` 全局变量区的地址常量（如 `BMP280_ADDRS`）提取，用于注意事项表格

## 输出格式

1. 输出完整的 `README.md` 文件内容（markdown 代码块预览）。
2. 输出前自检：确认所有代码块均有配对的开闭 ` ``` ` 标记，不得遗漏任何一个。
3. 询问用户："确认写入同目录下的 `README.md` 吗？"，用户确认后将内容写入文件。


## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考：

[完整规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)

## 自省与进化

每次执行完成后，检查是否遇到以下情况：
- 规则未覆盖的边界情况
- 用户指出的输出错误或规则缺陷
- 新发现的约束需求

若有，立即执行：
1. 将新规则追加到本文件对应章节
2. 将相同修改同步写入 `G:/MicroPython_Skills/upy-gen-readme/SKILL.md`
3. 在 `G:/MicroPython_Skills/` 目录执行：
   `git add upy-gen-readme/SKILL.md && git commit -m "skill(upy-gen-readme): <规则描述>"`
