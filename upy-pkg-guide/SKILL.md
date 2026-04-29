---
name: upy-pkg-guide
description: Use this skill when the user mentions a device/chip name and wants to know how to use its MicroPython driver from upypi. Invoke when user says things like "怎么用BMP280", "DS18B20怎么调用", "告诉我MPR121的用法", "查一下upypi上XX的驱动怎么用", or mentions any chip/sensor name and asks for usage guidance.
---

# MicroPython 驱动包使用要点提取 Skill

## 角色定位

给定一个器件名称，从 upypi 自动获取对应驱动包的所有文件，综合分析后输出该驱动的使用要点。

## 执行步骤

### 第一步：搜索 upypi

使用 Bash 工具执行：
```bash
curl -s "https://upypi.net/api/search?q={器件名}"
```

- 若有多个结果，列出所有包名，询问用户选择哪个
- 若无结果，告知用户并结束

### 第二步：获取 package.json

```bash
curl -s "{package_url}/package.json"
```

从中提取：
- `urls` 字段 → 所有驱动文件的 `source_path`
- `version`、`author`、`description`、`deps`

### 第三步：并行下载所有文件

base_url = `{package_url}/`（即 `https://upypi.net/pkgs/{name}/{version}/`）

同时尝试获取以下文件（用 Bash curl，404 则跳过）：

| 文件 | URL |
|---|---|
| 驱动 .py（来自 urls） | `{base_url}{source_path}` |
| main.py | `{base_url}code/main.py` |
| README.md | `{base_url}README.md` |

### 第四步：综合分析，输出使用要点

综合三类文件内容，输出以下结构：

---

## {器件名} 驱动使用要点

**包信息**
- 包名：`{name}` v{version}，作者：{author}
- 依赖：{deps 或"无"}

**安装**
```bash
# mpremote 安装
mpremote mip install {package_url}
```

**初始化**
```python
# 最小可运行示例（来自 main.py）
```

**核心 API**

| 方法/属性 | 返回值 | 说明 |
|---|---|---|
| ... | ... | ... |

**注意事项**
- 从 README.md Notes 章节提取的关键限制和注意点

---

## 输出原则

- main.py 是**第一优先**参考——直接展示其初始化代码作为最小示例
- README.md 补充注意事项和硬件接线
- 驱动 .py 用于提取完整 API 表格
- 若某文件不存在（404），跳过对应部分，不报错
