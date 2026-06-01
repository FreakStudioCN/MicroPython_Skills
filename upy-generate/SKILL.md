---
name: upy-generate
description: 第四步——业务代码生成。读取 scaffold 阶段的 project-manifest.json，下载驱动、生成 DI 架构的业务代码、Mock 层、单元测试。触发：upy-scaffold 完成后自动进入。
---

# 业务代码生成 Skill

## 核心哲学：以单元测试为核心的嵌入式开发

本项目生成的代码遵循 **以单元测试为核心的嵌入式开发** 方法论：

- **硬件与软件解耦**：除 `main.py`（DI 装配入口）外，所有代码文件不 `import machine`。驱动通过工厂函数注入，任务函数通过参数接收驱动对象。
- **依赖注入与模拟（Mock）**：真实驱动与 Mock 实现同一鸭子类型接口，task 函数不关心传入的是真实硬件还是模拟对象。PC 端可直接 `import`  Mock 运行测试，无需任何硬件。
- **可测试性驱动设计**：每个 task 函数是纯 Python 函数，给定输入 → 产生输出，无全局状态。传感器报错、缺失（None）、正常数据三种情况均在 PC 端覆盖。
- **上位机 PC 端可模拟全部业务逻辑**：`test/pc/` 目录下的单元测试运行在 CPython，不依赖 MicroPython 运行时。lib/ 下的基础库（logger、time_helper 等）提供 CPython fallback 以支持此能力。

---

## 角色定位

给定 `project-manifest.json`（phase: scaffold），完成驱动下载、任务代码生成、DI 装配、测试生成。**代码理解和生成由 LLM 直接完成，不再依赖正则脚本。**

---

## 前置检查

```bash
python --version
python -c "import requests; print('requests OK')"
```

无外部依赖（Python 3 标准库 + requests）。

---

## Phase 1: 下载驱动

```bash
python G:/MicroPython_Skills/upy-generate/scripts/download_drivers.py --project-dir {project_dir}
```

脚本从 upypi / GitHub 拉取驱动 .py 文件到 `firmware/lib/`，同时尝试拉取 `README.md` 和 `code/main.py` 作为参考材料：

| 文件 | 命名 | 用途 |
|------|------|------|
| 驱动 .py | `lib/<driver>.py` | 驱动源码，理解 API |
| README.md (upypi) | `lib/<name>_README.md` | 接线图、API 说明、使用流程 |
| code/main.py (upypi) | `lib/<name>_example.py` | 可运行示例，展示真实调用模式 |
| README.md (GitHub) | `lib/<name>_README.md` | 仓库文档 |

### 1A: 换行符修复

upypi / GitHub 源文件可能包含 `\r\r\n` 等非标准换行符，会导致 CPython 解析失败。下载后扫描 `lib/*.py`，若 compile 失败则自动修复：

```bash
cd {project_dir} && python -c "
import os, sys
for fn in os.listdir('firmware/lib'):
    if not fn.endswith('.py'): continue
    path = os.path.join('firmware/lib', fn)
    try:
        with open(path, 'rb') as f: data = f.read()
        compile(data.decode('utf-8'), path, 'exec')
    except (SyntaxError, IndentationError, UnicodeDecodeError):
        # Normalize line endings and remove blank lines between backslash continuations
        text = data.decode('utf-8', errors='ignore')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.splitlines(keepends=True)
        result = []; i = 0
        while i < len(lines):
            line = lines[i]; result.append(line)
            if line.rstrip('\n').endswith('\\\\'):
                i += 1
                while i < len(lines) and lines[i].strip('\n').strip() == '': i += 1
            else: i += 1
        text = ''.join(result)
        with open(path, 'w', encoding='utf-8') as f: f.write(text)
        print(f'[FIX] {fn} line endings normalized')
"

---

## Phase 2: LLM 理解驱动 → 生成工厂 + Mock

**对 manifest.devices 中的每个 device，逐一执行：**

### 2A: 阅读理解（Mock API 的唯一来源）

**Mock 的方法签名、参数、返回值类型必须从下载到 `firmware/lib/` 的驱动源码中直接提取 —— 不依赖任何外部的 api_ref 字符串或预置数据库。**

读取以下文件（如果存在）：
```
firmware/lib/<driver>.py          ← 驱动源码（Mock API 的权威来源）
firmware/lib/<name>_README.md     ← 使用文档
firmware/lib/<name>_example.py    ← 示例代码
```

从源码中理解：
- **主驱动类是哪个**：如果有多个类（如 `SSD1306` 基类 + `SSD1306_I2C` 子类），选 I2C/SPI 子类；没有子类则选第一个非 Exception 类
- **__init__ 参数**：区分 I2C 地址、Pin 脚号、配置参数
- **公开方法（Mock 覆盖目标）**：所有不以 `_` 开头的方法，逐一记录方法签名（参数名、默认值）和返回值类型。这些将直接决定 Mock 类的方法列表和默认返回值
- **是否是自建 I2C 的驱动**：`self.i2c = I2C(...)` → 需要修改驱动以支持外部传入 i2c

example.py 可以告诉你真实的调用方式：
```python
# 从 example 知道：BMP280(i2c=i2c, address=addr)、read_compensated_data() 返回 (temp, press, hum)
```

### 2B: 修改自建 I2C 的驱动（如果需要）

如果驱动在 `__init__` 中自己创建 I2C（如 SHT30 的 `self.i2c = I2C(scl=Pin(...), sda=Pin(...))`），直接修改 `lib/<driver>.py`：

1. `def __init__(self, ...)` 末尾加 `, i2c=None`
2. 把 `self.i2c = I2C(...)` 包在 `if i2c is not None: self.i2c = i2c else: ...` 里
3. `self.i2c_addr` 等后续赋值留在 if/else 外面（两种分支都需要）

### 2C: 生成工厂函数 → `drivers/<name>_driver/__init__.py`

```python
# -*- coding: utf-8 -*-
# @Generated : upy-generate
# @File    : drivers/<name>_driver/__init__.py
# @License : MIT

try:
    from lib.<module> import <DriverClass>
except ImportError:
    <DriverClass> = None


def create_<name>(i2c, address=None):
    """Create <DriverClass> instance. Returns driver object or None on failure."""
    if i2c is None:
        return None
    try:
        obj = <DriverClass>(i2c=i2c, address=address if address is not None else <default_addr>)
        return obj
    except Exception as e:
        print('[DRIVER] <NAME> init failed:', e)
        return None
```

- I2C 器件：工厂接受 `i2c, address=None`
- GPIO 器件（buzzer/led，source=none）：工厂接受 `pin_num`，内部创建 `Pin(pin_num, Pin.OUT)`。**GPIO 器件没有现成驱动，需要 LLM 从头写合理的封装**（on/off/toggle/value），Mock 同样覆盖这些方法
- SPI 器件：工厂接受 `spi, cs_pin`，内部创建 `Pin(cs_pin, Pin.OUT)`
- 自建 I2C 驱动改过后：同样接受 `i2c, address=None`

### 2E: async 模式特殊处理

如果 `manifest.scaffold_mode` 为 `async`：

**默认规则**：驱动本身不改（保持同步，async 化在封装层完成），工厂函数返回同步驱动对象不变。task 函数形态和 main.py 入口由 scaffold 骨架阶段决定，generate 阶段沿用。

**例外 —— 驱动中存在阻塞式方法时必须修改驱动源码**：

1. **I2S 外设等硬件阻塞操作**：查阅 MicroPython asyncio 官方文档确认是否有异步替代 API。若有（如 `I2S.readinto()` 的异步版本），在工厂封装层包装；若没有，需在驱动中增加非阻塞轮询路径。

2. **`time.sleep()` / `time.sleep_ms()` 等延时**：驱动中如果有延时等待（如传感器上电稳定等待、复位后延时），必须修改：
   - 将 `time.sleep(n)` 替换为 `await asyncio.sleep(n)` 或 `await asyncio.sleep_ms(n)`
   - 对应方法签名改为 `async def`
   - 参考文档：https://docs.micropython.org/en/latest/library/asyncio.html

3. **轮询等待 I2C 响应等忙等待**：改为 `await asyncio.sleep_ms()` 让步给事件循环。

修改驱动后，更新对应 Mock 的方法签名（`async def` 匹配），task 协程中用 `await` 调用。

### 2D: 生成 Mock → `drivers/<name>_driver/mock.py`

Mock 的方法列表和签名**直接从 Phase 2A 阅读驱动源码的结果中提取**，覆盖驱动所有公开方法，默认返回值与驱动返回类型匹配：

```python
# -*- coding: utf-8 -*-
# @Generated : upy-generate
# @File    : drivers/<name>_driver/mock.py
# @License : MIT

class Mock<Name>:
    """Mock <NAME> — same API as real driver, returns canned data."""

    def __init__(self, **kwargs):
        self._<method1> = kwargs.get('<method1>', <default>)
        ...

    def <method1>(self):
        return self._<method1>
    ...
```

默认值规则：
- 返回数值 → `0`
- 返回布尔 → `True`
- 返回元组 → `(<典型值>)`，如 `(25.0, 60.0)`
- 返回 None → 不存 `self._xxx`，方法体直接 `pass`

---

## Phase 3: LLM 生成任务文件

读取 `manifest.requirements.description`（用户需求描述）和 `manifest.devices` 列表 → 生成 task 文件。

**task 是纯粹的 Python 函数**，不 import machine，通过参数接收驱动对象：

```python
# tasks/sensor_task.py
from lib.logger import debug, info, warning, error
from lib.time_helper import timed_function

@timed_function
def sensor_tick(sht30, bmp280):
    data = {}

    if sht30 is not None:
        try:
            t, h = sht30.measure()
            data["temperature"] = t
            data["humidity"] = h
        except Exception as e:
            warning('SHT30 read error: {}'.format(e))
    else:
        debug('SHT30 not available, skipping')
    # ...
    return data
```

**温度键冲突处理**：当同时有温湿度传感器和气压传感器时，气压传感器的温度写入 `pressure_temp`，避免覆盖主温度。

---

## Phase 4: LLM 补充 conf.py

读取 asset 中的 `firmware/conf.py`，按项目需求补充业务常量：

```python
# 告警阈值
ALARM_TEMP_HIGH = 40.0
ALARM_TEMP_LOW = 5.0
ALARM_HUMIDITY_HIGH = 80.0

# 显示刷新间隔
DISPLAY_REFRESH_MS = 1000

# 传感器校准偏移
TEMP_OFFSET = 0.0
HUM_OFFSET = 0.0
```

---

## Phase 5: LLM 生成 main.py（DI 装配）

读取所有工厂文件 + task 文件 + conf.py → 生成 main.py，完成完整的 DI 装配链：

```
machine.I2C → create_sht30(i2c) → sht30
            → create_bmp280(i2c) → bmp280
                                     ↓
                              sensor_tick(sht30, bmp280) → data
```

```python
from machine import I2C, Pin
from libs.scheduler.timer_sched import Scheduler
from drivers.sht30_driver import create_sht30
from drivers.bmp280_driver import create_bmp280
from tasks.sensor_task import sensor_tick
from tasks.maintenance import maintenance_tick
from conf import SAMPLE_RATE_MS

i2c = I2C(scl=Pin(5), sda=Pin(4))
sht30 = create_sht30(i2c)
bmp280 = create_bmp280(i2c)

sc = Scheduler(timer_id=-1, tick_ms=100, idle_cb=maintenance_tick)
sc.add_task(lambda: sensor_tick(sht30, bmp280), interval_ms=1000)
sc.start()
```

**I2C 分配规则**：
- 先尝试把所有同 bus 的器件挂在一个 I2C 上
- 地址冲突时创建第二个 I2C 实例
- 不是简单一个器件一个 I2C

---

## Phase 6: LLM 生成测试文件

### 6A: PC 端单元测试 `test/pc/test_<task>.py`

```python
import unittest
import sys
sys.path.insert(0, 'firmware')

# 用 Mock 替换真实 driver
from drivers.sht30_driver.mock import MockSht30
from drivers.bmp280_driver.mock import MockBmp280
from tasks.sensor_task import sensor_tick

class TestSensorTask(unittest.TestCase):
    def test_normal_reading(self):
        sht30 = MockSht30(measure=(25.0, 60.0))
        bmp280 = MockBmp280(read_compensated_data=(25.0, 101325.0, 50.0))
        data = sensor_tick(sht30, bmp280)
        self.assertEqual(data["temperature"], 25.0)
        self.assertEqual(data["humidity"], 60.0)

    def test_sensor_none(self):
        data = sensor_tick(None, None)
        self.assertEqual(data, {})

    def test_sensor_error(self):
        # Mock 抛出异常
        bad = MockSht30()
        bad.measure = lambda: (_ for _ in ()).throw(Exception("fail"))
        data = sensor_tick(bad, None)
        self.assertNotIn("temperature", data)

if __name__ == '__main__':
    unittest.main()
```

覆盖三种情况：正常数据、传感器缺失（None）、传感器异常（抛异常）。

### 6B: 设备端冒烟测试 `test/device/test_smoke.py`

只测硬件可用性（I2C scan、Pin 初始化），不测业务逻辑。

**只用 MicroPython unittest 支持的 assert 方法**（`assertTrue`、`assertEqual`、`assertIsNotNone`、`assertRaises`），**禁止使用** `assertIsInstance`、`assertIn`、`assertNotIn`、`assertGreater` 等 CPython 扩展。

```python
from machine import I2C, Pin
import unittest

class TestSmoke(unittest.TestCase):
    def test_i2c_scan(self):
        i2c = I2C(scl=Pin(5), sda=Pin(4))
        devices = i2c.scan()
        self.assertTrue(len(devices) > 0, "No I2C devices found")
```

### 6C: CPython 兼容性

PC 端测试（`test/pc/`）会遇到 MicroPython 特有模块在 CPython 不存在的问题。生成代码时应遵守架构约束（除 main.py 外不 import machine），但如果 lib/ 下的文件（如 logger、time_helper）使用了 `micropython.const`、`time.ticks_ms` 等 MPY 专有 API，需要确认它们有 CPython fallback。如果发现缺失，顺手补上。

---

## Phase 7: flake8 验证

```bash
cd {project_dir} && python -m flake8 firmware/ --extend-exclude=firmware/lib --max-line-length=120 2>&1
```

有错直接修，修完重新验证，直到 pass。

---

## Phase 8: AI 生成后审查

Phase 2-7 完成后，LLM 执行最终审查，逐项核验：

### 8A: 驱动 API 正确性

1. 重新通读 `firmware/lib/*.py` 驱动源码，确认工厂 `__init__.py` 的 import 和构造函数调用与真实驱动一致
2. 确认 Mock 方法签名（参数名、返回值类型）与驱动源码匹配
3. 确认所有公开方法都已 Mock（无遗漏）

### 8B: 需求覆盖

1. 对照 `manifest.requirements.description`，确认每个需求点都有对应的 task 处理
2. 检查 `manifest.output` 中列出的输出器件（display/buzzer/led）都有对应的 task 和 main.py 装配

### 8C: GPIO 器件审查

1. GPIO-only 器件（source=none，如蜂鸣器/LED/按键）的工厂封装是否合理
2. Mock 是否覆盖了 on/off/toggle/value 等基本操作

### 8D: 测试覆盖审查

1. `test/pc/test_*.py` 是否覆盖正常 + 异常（传感器报错）+ 边界（传感器为 None）三种情况
2. `test/device/test_smoke.py` 是否只用 MPY unittest 允许的 assert 方法

### 8E: 发现问题时直接修改对应文件，然后重新运行 Phase 7 flake8 和 PC 测试。

---

## Phase 9: 更新 manifest

```bash
cd {project_dir} && python -c "
import json, os
from datetime import datetime, timezone
path = 'project-manifest.json'
with open(path, 'r', encoding='utf-8') as f:
    m = json.load(f)
m['phase'] = 'generate'
m['generate'] = m.get('generate', {})
m['generate']['generated_at'] = datetime.now(timezone.utc).isoformat()
with open(path, 'w', encoding='utf-8') as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
print('[OK] manifest phase → generate')
"

---

## 参考文档

生成代码时遇到 API 不确定的情况，查阅以下权威文档：

| 文档 | URL | 用途 |
|------|-----|------|
| MicroPython 官方文档 | https://docs.micropython.org/en/latest/index.html | 所有 MPY 标准库 API 参考 |
| asyncio 协程 | https://docs.micropython.org/en/latest/library/asyncio.html | async 模式：`create_task`、`sleep_ms`、`gather`、`Event`、`Queue` 等 |
| _thread 多线程 | https://docs.micropython.org/en/latest/library/_thread.html | _thread 模式：`start_new_thread`、`allocate_lock`、`exit` 等 |
| unittest 源码 | https://github.com/micropython/micropython-lib/blob/master/python-stdlib/unittest | MPY unittest 支持的 assert 方法参考（仅 `assertTrue`/`assertEqual`/`assertIsNotNone`/`assertRaises`） |

---

## 架构约束（生成代码必须遵守）

- **鸭子类型 DI**：task 函数接收对象，不关心是真实驱动还是 Mock
- **除 main.py 外不 import machine**：所有 .py 文件不直接 import machine.Pin/I2C/SPI/UART
- **除 lib/ 外不使用 typing 泛型**：类型注解只用 MPY 内置类型
- **独立 try/except**：每个 task_tick 独立异常处理，一个传感器挂了不影响其他
- **阈值在 conf.py**：不硬编码数值
- **Mock 方法签名与真实驱动一致**：通过阅读驱动源码和 example.py 确认

---

## 与其他 skill 的关系

- ← `upy-scaffold`：输入骨架 + manifest
- → `upy-deploy-test`：上传代码到设备并验证
- → `upy-wiring`：引脚分配表 → 接线图
- → `upy-diagram`：代码结构 → 架构图

---

## 强约束

- **可以修改 lib/ 下的驱动源码**（仅限：①添加 DI 支持如 i2c=None 参数 ②修复非标准换行符影响 CPython 编译）
- **不生成全局 firmware/mock/ 目录**
- **async 模式下驱动默认不改**，但如果驱动存在阻塞式方法（`time.sleep`、I2S 阻塞操作等），必须修改为异步版本并查阅 asyncio 官方文档确认 API；异步化也可在封装层处理
- **生成结束自动 flake8 验证 + PC 测试运行**，不通过不结束
- **lib/ 下文件需保证 CPython 兼容**：`micropython.const`、`time.ticks_ms` 等 MPY 专有 API 要有 fallback（logger、time_helper 等 scaffold 文件可能遗漏）
- **设备端测试只用 MPY unittest assert 子集**：`assertTrue`、`assertEqual`、`assertIsNotNone`、`assertRaises`，禁止 `assertIn`/`assertIsInstance` 等
