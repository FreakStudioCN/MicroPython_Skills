---
name: upy-gen-pkg
description: Use this skill when the user wants to generate a package.json from scratch for a MicroPython driver package. Invoke when user says things like "generate package.json", "生成package.json", "帮我写包配置", "创建mip包配置", or provides a driver directory/file and asks to create a package config.
---

# MicroPython package.json 生成 Skill

## 角色定位

你是 GraftSense MicroPython 包配置生成助手。给定一个驱动目录或驱动 `.py` 文件，分析其结构和依赖，从 0 生成符合 GraftSense 规范的完整 `package.json`。

## 执行步骤

1. 扫描用户指定目录下所有 `.py` 文件，排除 `main.py`；**必须重新读取每个文件的完整内容，不得使用会话缓存或跳过读取步骤**
2. 从所有驱动文件中提取：文件名列表、`@Author`、`@Description`、`__version__`、`__license__`、所有 `import` 语句（合并去重）；`author`/`version`/`description` 优先从与目录同名的主驱动文件提取，若无同名文件则从第一个 `.py` 文件提取
3. 分析每个 import 的来源类型（见依赖处理步骤）
4. 对第三方依赖逐一查询 upypi
5. 生成完整 `package.json`

## 必须生成的字段（全部）

| 字段 | 生成规则 |
|---|---|
| `name` | 从目录名提取，转为小写字母+下划线（如 `BH1750_driver` → `bh1750_driver`） |
| `urls` | 扫描目录下所有 `.py` 文件（排除 `main.py`），每个文件生成一条 `["文件名.py", "code/文件名.py"]` 映射；多文件驱动包含所有驱动文件 |
| `version` | 从 `__version__` 提取，若无则默认 `"1.0.0"` |
| `_comments` | 固定内容（见下方模板） |
| `description` | 从 `@Description` 或类 docstring 提取，英文 |
| `author` | 从驱动文件 `__author__` 或文件头 `@Author` 提取；若无则提示用户填写，不得使用占位符 |
| `license` | 从 `__license__` 提取，默认 `"MIT"` |
| `chips` | 默认 `"all"`，除非驱动明确依赖特定芯片（如 RP2040 PIO） |
| `fw` | 默认 `"all"`，除非有特殊固件依赖（ulab、lvgl 等） |

## 依赖处理（三步优先级）

### 第一步：识别 import 来源

```
MicroPython 内置模块（machine、time、sys、utime、uos、ustruct 等）
→ 不写入 deps，直接跳过

micropython-lib 标准库（collections、os、json、re、hashlib 等）
→ 用 mip 标准格式：["库名", "latest"]

其他第三方模块（非上述两类）
→ 进入第二步查询 upypi
```

### 第二步：查询 upypi

对每个第三方依赖，**优先使用 Bash 工具执行 curl 自动查询**：

```bash
curl -s "https://upypi.net/api/search?q={依赖模块名}"
```

响应示例：
```json
{"query":"ds18b20","results":[{"name":"ds18b20_driver","url":"https://upypi.net/pkgs/ds18b20_driver/1.0.0"}]}
```

- **有结果**：使用返回的 `url` 字段写入 deps：`["{url}", "latest"]`
- **curl 执行失败（无网络/curl 不可用）**：提示用户在浏览器访问 `https://upypi.net/api/search?q={模块名}` 并将 JSON 结果粘贴回来；收到结果后继续处理；若用户无法访问则使用 `github:` 占位格式并标注 `⚠️ 需手动确认`
- **无结果**：用 `github:` 占位格式写入，并在文件末尾标注 `⚠️ 需手动确认`

### 第三步：deps 字段格式

```json
"deps": [
  ["https://upypi.net/pkgs/ds18b20_driver/1.0.0", "latest"],
  ["collections-defaultdict", "latest"],
  ["github:org/repo", "main"]
]
```

若无任何外部依赖，省略 `deps` 字段。

## 许可证与版权规则

| 情况 | author 字段 | license 字段 |
|---|---|---|
| 参考他人开源代码 | 与原仓库作者一致 | 与原仓库许可证一致 |
| FreakStudio 原创 | `"leeqingshui"` 或团队名 | `"MIT"` |

**参考他人代码示例**（如参考 robert-hh 的 bmp280 驱动）：
```json
{
  "name": "bmp280_driver",
  "urls": [["bmp280_float.py", "code/bmp280_float.py"]],
  "version": "1.0.0",
  "_comments": {
    "chips": "该包支持运行的芯片型号，all表示无芯片限制",
    "fw": "该包依赖的特定固件如ulab、lvgl,all表示无固件依赖"
  },
  "description": "A MicroPython library to control BMP280 pressure sensor",
  "author": "robert-hh",
  "license": "MIT",
  "chips": "all",
  "fw": "all"
}
```
> author 和 license 字段必须与原仓库保持一致，不得填写 FreakStudio 信息。

## 输出模板

```json
{
  "name": "sensor_driver",
  "urls": [
    ["sensor.py", "code/sensor.py"]
  ],
  "version": "1.0.0",
  "_comments": {
    "chips": "该包支持运行的芯片型号，all表示无芯片限制",
    "fw": "该包依赖的特定固件如ulab、lvgl,all表示无固件依赖"
  },
  "description": "A MicroPython library to control [传感器名称]",
  "author": "作者名",
  "license": "MIT",
  "chips": "all",
  "fw": "all"
}
```

有依赖时追加 `deps` 字段（置于 `urls` 之前）：
```json
{
  "name": "xfyun_asr",
  "version": "1.0.1",
  "description": "iFlytek online ASR WebSocket driver for MicroPython",
  "author": "leeqingsui",
  "license": "MIT",
  "chips": "all",
  "fw": "all",
  "_comments": {
    "chips": "该包支持运行的芯片型号，all表示无芯片限制",
    "fw": "该包依赖的特定固件如ulab、lvgl,all表示无固件依赖"
  },
  "deps": [
    ["https://upypi.net/pkgs/async_websocket_client/1.0.0", "latest"]
  ],
  "urls": [
    ["xfyun_asr.py", "code/xfyun_asr.py"]
  ]
}
```

## 三种安装方式（生成 package.json 后告知用户）

生成完成后，附上对应该包的三种安装命令供用户参考：

```python
# 方式一：mip（在设备上运行）
import mip
mip.install("github:FreakStudioCN/GraftSense-Drivers-MicroPython/sensors/{包目录名}")

# 方式二：mpremote（命令行）
# mpremote mip install github:FreakStudioCN/GraftSense-Drivers-MicroPython/sensors/{包目录名}

# 方式三：upypi（推荐，访问 https://upypi.net/ 搜索包名获取命令）
```

## 输出格式

1. 输出完整的 `package.json` 内容（JSON 代码块预览）。
2. 询问用户："确认写入同目录下的 `package.json` 吗？"，用户确认后将内容写入文件。

若存在 upypi 查询无结果的依赖，在代码块之后单独列出：
```
⚠️ 以下依赖未在 upypi 找到，已使用占位格式，请手动确认：
- {模块名}：github:org/repo
```

最后附三种安装方式命令（替换 `{包目录名}` 为实际目录名）。


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
2. 将相同修改同步写入 `G:/MicroPython_Skills/upy-gen-pkg/SKILL.md`
3. 在 `G:/MicroPython_Skills/` 目录执行：
   `git add upy-gen-pkg/SKILL.md && git commit -m "skill(upy-gen-pkg): <规则描述>"`
