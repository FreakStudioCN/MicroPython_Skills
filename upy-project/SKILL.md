---
name: upy-project
description: Use this skill when the user describes a MicroPython project — what it should do, what microcontroller and sensors to use. Invoke when user says things like "我想做一个MicroPython项目", "帮我写一个ESP32程序", "用BMP280和OLED做一个气象站", "帮我实现XX功能", or describes any embedded project with hardware components.
---

# MicroPython 项目端到端生成 Skill

## 角色定位

给定用户的项目描述，完成从需求澄清、器件选型、代码生成到设备调试的全流程，最终在用户设备上运行成功。

## 前置检查（第一步必做）

检查 `mpremote` 是否可用：

```bash
mpremote --version
```

- 可用 → 继续
- 不可用 → 提示用户：
  ```
  需要先安装 Python 和 mpremote：
  1. 安装 Python: https://python.org
  2. pip install mpremote requests
  ```
  等用户确认安装完成后再继续。

---

## 阶段0：解析用户输入中的链接

若用户输入中包含链接：

- **必须是 GitHub 链接**，否则提示：
  ```
  请先将相关文件上传到 GitHub，再提供链接。
  ```
- 调用 **fetch-doc skill** 获取链接内容
- 从内容中提取：硬件型号、引脚信息、功能描述
- 将提取信息合并到需求理解，减少后续追问

---

## 阶段1：需求澄清

**一次性列出所有缺失信息，不要多轮追问。**

必须确认的信息：

| 信息 | 若未说明 |
|---|---|
| 主控型号 | 询问：ESP32 / RP2040 / Pico W？ |
| 传感器/模块列表 | 询问：需要哪些硬件？ |
| 各模块引脚分配 | 见下方引脚处理规则 |
| 功能描述 | 询问：要实现什么效果？ |
| 设备串口端口 | 询问：COM 口或 /dev/ttyXXX？（可用 `mpremote devs` 列出） |

### 引脚处理规则

**第一步：识别板型，查内置引脚表**

| 板型 | 可用 GPIO（推荐） | 注意事项 |
|---|---|---|
| ESP32 | 4,5,12,13,14,15,16,17,18,19,21,22,23,25,26,27,32,33,34(只读),35(只读),36(只读),39(只读) | GPIO0/2/15 启动敏感，避免用；GPIO6-11 接内部 Flash，禁用 |
| ESP32-S3 | 1-21,35-45 | GPIO19/20 为 USB，避免用 |
| Pico / Pico W | GP0-GP28（物理引脚 1-40） | GP23/24/25/29 内部使用，避免用 |
| ESP8266 | D1(GPIO5),D2(GPIO4),D5(GPIO14),D6(GPIO12),D7(GPIO13) | GPIO0/2/15 启动敏感 |

**第二步：若板型不在上表，或用户使用定制板**

在需求澄清时追加询问：
```
您使用的是非标准开发板，请提供引脚图链接（GitHub 链接）或直接告知各模块接哪个 GPIO。
```
若用户提供 GitHub 链接 → 调用 **fetch-doc skill** 提取引脚信息。

**第三步：引脚分配原则**

- I2C 优先用板型默认 I2C 引脚（ESP32: SCL=22/SDA=21，Pico: SCL=GP5/SDA=GP4）
- SPI 优先用默认 SPI 引脚
- 避免使用启动敏感引脚
- 若用户已指定引脚，直接使用，不覆盖

---

## 阶段2：器件选型

**所有器件必须从 upypi 有驱动包的中选择，不得使用 upypi 上没有的驱动。**

对每个器件，**必须用多个关键词并行搜索**，合并去重结果后再判断：

```bash
# 示例：麦克风模块需同时搜索
curl -s "https://upypi.net/api/search?q=mic"
curl -s "https://upypi.net/api/search?q=microphone"
curl -s "https://upypi.net/api/search?q=audio"
curl -s "https://upypi.net/api/search?q=i2s"
```

**关键词扩展规则**：
- 用芯片型号（如 `inmp441`）+ 功能类别（如 `mic`、`microphone`、`audio`）+ 接口类型（如 `i2s`、`uart`、`i2c`）至少 3 个关键词
- 对语音/AI 类项目额外搜索：`asr`、`tts`、`speech`、`llm`、`ai`
- 合并所有搜索结果，去重后统一展示

- **有结果** → 列出包名，推荐最匹配的，说明理由，等用户确认
- **全部无结果** → 告知用户，搜索替代方案（同样多关键词查），推荐替代器件
- **多个结果** → 推荐最匹配的，列出其他选项

选型确认后，调用 **upy-pkg-guide skill** 获取每个器件的 API 用法，作为代码生成参考。

---

## 阶段3：代码生成

### 项目文件结构

```
（设备 /lib/ 目录）
/lib/
└── {driver}.py          ← 从 upypi 下载，mpremote 传入

（项目目录，上传到设备根目录）
{功能A}_task.py          ← 单一功能模块
{功能B}_task.py
main.py                  ← 统一调度
```

### task 文件规范

每个 `xx_task.py` 负责一个功能模块，必须：

```python
# 初始化函数，返回硬件对象或 None（失败时）
def init():
    try:
        print("[INIT] {模块名} initializing...")
        obj = DriverClass(...)
        print("[OK] {模块名} ready")
        return obj
    except Exception as e:
        print("[FAIL] {模块名} init:", e)
        return None

# 核心功能函数，独立 try/except
def run(obj):
    try:
        result = obj.read()
        print("[DATA] {模块名}:", result)
        return result
    except Exception as e:
        print("[ERROR] {模块名}:", e)
        return None
```

### main.py 规范

```python
# 文件头 7 行注释
import time
from {功能A}_task import *
from {功能B}_task import *

# I2C/SPI 扫描诊断（使用 I2C 时必须）
from machine import I2C, Pin
i2c = I2C(0, scl=Pin(X), sda=Pin(Y))
devices = i2c.scan()
print("[I2C] Found:", [hex(d) for d in devices])
if not devices:
    raise RuntimeError("No I2C device found")

time.sleep(3)
print("FreakStudio: {项目名} starting...")

# 初始化所有模块
obj_a = init_a()
obj_b = init_b()

try:
    while True:
        if obj_a:
            run_a(obj_a)
        if obj_b:
            run_b(obj_b)
        time.sleep_ms(100)
except KeyboardInterrupt:
    print("Stopped by user")
except Exception as e:
    print("[FATAL]", e)
finally:
    print("Cleanup done")
```

---

## 阶段4：mpremote 自动调试（最多3次）

### 每次调试流程

```bash
# 1. 复位设备
mpremote connect {port} reset

# 2. 创建 /lib 目录
mpremote connect {port} fs mkdir /lib

# 3. 上传驱动文件（依赖包一并上传）
mpremote connect {port} fs cp {driver}.py :/lib/{driver}.py

# 4. 上传 task 文件和 main.py
mpremote connect {port} fs cp {功能}_task.py :{功能}_task.py
mpremote connect {port} fs cp main.py :main.py

# 5. 运行并捕获输出
mpremote connect {port} run main.py
```

### 输出解析逻辑

| 输出特征 | 判断 | 修复方向 |
|---|---|---|
| 无 Traceback，无 `[FAIL]` | **成功** | 通知用户完成 |
| `ImportError` | 驱动未上传或路径错 | 补传对应文件 |
| `OSError` | 硬件未连接/引脚错 | 提示用户检查接线，不重试 |
| `ValueError` | 参数错误 | 修改代码参数后重试 |
| `[FAIL]` | 定位到具体 task | 修改对应 task 文件后重试 |
| `AttributeError` | API 调用错误 | 重新读驱动源码，修正调用方式 |

### 3次失败后

输出：
```
已尝试3次，当前卡点：{错误描述}
可能原因：{分析}
建议手动排查：{具体步骤}
```

---

## 不可自动解决的情况（直接告知用户）

- 硬件物理接线错误（软件无法检测，OSError 时提示检查接线）
- 驱动与当前固件版本不兼容
- 需要特殊固件（ulab、lvgl 等）
- 设备无法被 mpremote 识别（驱动/权限问题）
