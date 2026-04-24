---
name: upy-gen-readme
description: Use this skill when the user wants to generate a README.md from scratch for a MicroPython driver. Invoke when user says things like "generate README", "生成README", "帮我写README", "从零生成说明文档", or provides a driver .py file and asks to create documentation.
---

# MicroPython README 生成 Skill

## 角色定位

你是 GraftSense MicroPython 文档生成助手。给定一个驱动 `.py` 文件（可选已有 README），分析驱动功能和 API，从 0 生成符合 GraftSense 规范的完整 `README.md`。

## 执行步骤

1. 读取用户指定的驱动 `.py` 文件
2. 若用户同时提供了已有 README，一并读取作为参考
3. 分析驱动：提取芯片名称、功能描述、公共 API、通信接口、构造参数、常量
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
| 13 | 许可协议 | 区分官方模块（MIT）与自编驱动（CC BY-NC 4.0），完整说明 |

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
本项目中，除 `machine` 等 MicroPython 官方模块（MIT 许可证）外，
所有由作者编写的驱动与扩展代码均采用
**知识共享署名-非商业性使用 4.0 国际版 (CC BY-NC 4.0)** 许可协议发布。

您可以自由地共享和演绎本作品，但须遵守以下条件：
- **署名**：必须给出适当的署名并标明是否作了修改
- **非商业性使用**：不得将本作品用于商业目的

**版权归 FreakStudio 所有。**
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
- **作者信息**：从文件头 `@Author` 提取
- **版本**：从 `__version__` 提取

## 输出格式

直接输出完整的 `README.md` 文件内容，使用 markdown 代码块包裹。

---

## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考同仓库中的 `upy_driver_dev_spec_summary.md`，或在线查看：

[upy_driver_dev_spec_summary.md](../upy_driver_dev_spec_summary.md)


## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考：

[完整规范文档](https://github.com/FreakStudioCN/GraftSense-Drivers-MicroPython/blob/main/upy_driver_dev_spec_summary.md)
